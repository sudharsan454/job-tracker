#!/usr/bin/env python3
# Job Application Driver · permanent runner · v1.0.2 · 13 Oct 2026 · v1.0.2: Gemini candidates pinged newest-first (30s each), thinking low, working model remembered in user_settings. v1.0.1: model auto-discovery
# Runs on GitHub Actions (free), no laptop needed. Python 3.11+, standard library only.
#
# Modes
#   run       every 15 min: Sourcer (Gmail IMAP) -> Fit (Gemini) -> Notifier (Telegram) -> Replies (Telegram buttons)
#   nightly   once a day:   Status Sync (rejection/interview mails) -> Sweeps (stale, ghost, debrief, overdue, lead health) -> digest
#   verify    one-off:      checks every secret and connection, sends a Telegram test message
#   --dry-run any mode:     fixtures instead of Gmail, fake LLM instead of Gemini, nothing written, nothing sent; prints the plan
#
# Secrets (GitHub Actions secrets -> env): GMAIL_USER, GMAIL_APP_PASSWORD, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN,
#   SUPABASE_URL, SUPABASE_SERVICE_KEY. Optional: GEMINI_MODEL (default auto = newest free Flash model), OWNER_ID.
# Design doc: PMOS/JobTracker/job-application-driver-design-v1.7.html (sections 8, 11, 12).

import argparse, email, email.policy, email.utils, hashlib, html, imaplib, json, os, re, sys, time, traceback, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone, date
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

VERSION = "1.0.2"
IST = ZoneInfo("Asia/Kolkata")
OWNER_ID = os.environ.get("OWNER_ID", "f0c721b5-e317-49c4-b02c-d7822411fa55")  # sudharsan454@gmail.com auth user
PM_STREAM = "11111111-1111-4111-8111-000000000001"
APP_URL = "https://sudharsan454.github.io/jobs/"
DEFAULT_SENDERS = ["linkedin.com", "naukri.com", "instahyre.com", "iimjobs.com", "hirist.com", "cutshort.io",
                   "wellfound.com", "indeed.com", "glassdoor.com", "foundit.in", "hiring.cafe", "ycombinator.com", "joblet.in"]
OPEN_STATUSES = ["applied", "screening", "round_1", "round_2", "round_3", "offer"]


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def today_ist():
    return datetime.now(IST).date()


def log(*a):
    print(datetime.now(IST).strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- HTTP helpers
def http(method, url, body=None, headers=None, timeout=60):
    data = None
    h = {"User-Agent": f"job-driver-runner/{VERSION}"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw[:500]}


# ---------------------------------------------------------------- Supabase (PostgREST, service key, owner_id set explicitly)
class Supabase:
    def __init__(self, url, key, dry=False):
        self.url = url.rstrip("/") + "/rest/v1/"
        self.h = {"apikey": key, "Authorization": "Bearer " + key}
        self.dry = dry
        self.planned = []

    def select(self, table, params):
        qs = urllib.parse.urlencode(params, safe="*,.()!:=")
        st, d = http("GET", self.url + table + "?" + qs, headers=self.h)
        if st >= 300:
            raise RuntimeError(f"supabase select {table}: {st} {d}")
        return d or []

    def insert(self, table, rows):
        rows = rows if isinstance(rows, list) else [rows]
        for r in rows:
            r.setdefault("owner_id", OWNER_ID)
        if self.dry:
            self.planned.append(("insert", table, rows))
            return [dict(r, id=r.get("id") or f"dry-{hashlib.md5(json.dumps(r, default=str).encode()).hexdigest()[:8]}") for r in rows]
        st, d = http("POST", self.url + table, rows, headers=dict(self.h, Prefer="return=representation"))
        if st >= 300:
            raise RuntimeError(f"supabase insert {table}: {st} {d}")
        return d

    def update(self, table, match, patch):
        if self.dry:
            self.planned.append(("update", table, match, patch))
            return []
        qs = urllib.parse.urlencode({k: "eq." + str(v) for k, v in match.items()})
        st, d = http("PATCH", self.url + table + "?" + qs, patch, headers=dict(self.h, Prefer="return=representation"))
        if st >= 300:
            raise RuntimeError(f"supabase update {table}: {st} {d}")
        return d

    def upsert_ignore(self, table, row, conflict):
        row.setdefault("owner_id", OWNER_ID)
        if self.dry:
            self.planned.append(("upsert", table, row))
            return
        st, d = http("POST", self.url + table + "?on_conflict=" + conflict, [row],
                     headers=dict(self.h, Prefer="resolution=ignore-duplicates,return=minimal"))
        if st >= 300:
            raise RuntimeError(f"supabase upsert {table}: {st} {d}")


# ---------------------------------------------------------------- Gemini (free tier) with a fake for dry runs
class Gemini:
    """Gemini via REST. Model 'auto' = newest Flash model that actually answers a 30s ping (free-tier models come and go)."""
    def __init__(self, key, model, dry=False, remember=None):
        self.key, self.model, self.dry = key, model, dry
        self.remember = remember  # callable(model_name) that persists the working model
        self.tokens_in = self.tokens_out = 0
        self.candidates = []

    def _url(self, model):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.key}"

    def list_candidates(self):
        st, d = http("GET", f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key={self.key}", timeout=60)
        if st != 200:
            raise RuntimeError(f"gemini list models {st}: {str(d)[:200]}")
        names = [m["name"].split("/", 1)[1] for m in d.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        def rank(n):
            m = re.match(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?(-preview.*|-\d+)?$", n)
            if not m:
                return None
            return (float(m.group(1)), 0 if m.group(2) else 1, 0 if (m.group(3) or "").startswith("-preview") else 1)
        ranked = sorted(((r, n) for n in names if (r := rank(n)) is not None), reverse=True)
        self.candidates = [n for _, n in ranked]
        if not self.candidates:
            raise RuntimeError("gemini: no flash model found in " + ", ".join(names[:20]))
        return self.candidates

    def discover(self):
        tried = []
        for m in self.list_candidates()[:6]:
            t0 = time.time()
            st, d = self._call(m, 'Return JSON {"ok":true}', "ping", 64, timeout=30)
            if st == 200:
                self.model = m
                log(f"gemini model -> {m} ({time.time()-t0:.1f}s)")
                if self.remember:
                    try:
                        self.remember(m)
                    except Exception:
                        pass
                return m
            tried.append(f"{m}:{st}")
            log(f"gemini candidate {m} failed ({st}); trying next")
        raise RuntimeError("gemini: no candidate answered: " + ", ".join(tried))

    def _call(self, model, system, user, max_tokens, timeout=120, thinking=True):
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}}
        if thinking:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        try:
            st, d = http("POST", self._url(model), body, timeout=timeout)
        except Exception as e:  # timeouts, resets
            return 599, {"error": str(e)[:200]}
        if st == 400 and thinking and "thinking" in str(d).lower():
            return self._call(model, system, user, max_tokens, timeout, thinking=False)
        return st, d

    def json(self, system, user, max_tokens=4096):
        if self.dry:
            return FakeLLM.answer(system, user)
        if self.model in ("", "auto", None):
            self.discover()
        for attempt in range(5):
            st, d = self._call(self.model, system, user, max_tokens)
            if st == 200:
                um = d.get("usageMetadata", {})
                self.tokens_in += um.get("promptTokenCount", 0)
                self.tokens_out += um.get("candidatesTokenCount", 0)
                try:
                    txt = d["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt)
                except Exception as e:
                    raise RuntimeError(f"gemini bad json: {e} {str(d)[:300]}")
            if st in (404, 599) and attempt == 0:
                log(f"gemini {self.model} {st}; re-discovering")
                self.discover()
                continue
            if st in (429, 500, 503):
                wait = 15 * (attempt + 1)
                log(f"gemini {st}, retry in {wait}s")
                time.sleep(wait)
                continue
            raise RuntimeError(f"gemini {st}: {str(d)[:300]}")
        raise RuntimeError("gemini: gave up after retries")


class FakeLLM:
    """Deterministic stand-in used by --dry-run. Pulls jobs with a regex over the fixture text."""
    @staticmethod
    def answer(system, user):
        if "EXTRACT_JOBS" in system:
            jobs = []
            for m in re.finditer(r"JOB:\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\S+)", user):
                jobs.append({"title": m.group(1), "company": m.group(2), "location": m.group(3), "url": m.group(4),
                             "easy_apply": "easy" in m.group(4), "posted_text": "1 day ago", "snippet": "fixture", "stream": "Product management"})
            return {"is_job_alert": bool(jobs), "jobs": jobs}
        if "SCORE_FIT" in system:
            n = user.count('"title"')
            return {"scores": [{"index": i, "fit_score": 72 - 9 * i, "fit_breakdown": {"basis": "fixture", "role_level": "PM", "domain": "SaaS",
                     "location": "Chennai", "must_haves": "unknown until the JD is read", "note": "dry run score"}} for i in range(n)]}
        if "CLASSIFY_STATUS" in system:
            return {"outcome": "rejected", "company": "Fixture Co", "verbatim": "Unfortunately we will not be moving forward.", "confidence": 0.9}
        return {}


# ---------------------------------------------------------------- Telegram
class Telegram:
    def __init__(self, token, dry=False):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.dry = dry
        self.sent = []

    dry_updates = []

    def call(self, method, body=None):
        if self.dry:
            if method == "getUpdates":
                u, self.dry_updates = self.dry_updates, []
                return {"ok": True, "result": u}
            self.sent.append((method, body))
            return {"ok": True, "result": {"message_id": 0, "username": "dry_bot"}}
        st, d = http("POST", self.base + method, body or {})
        if st != 200 or not d.get("ok"):
            raise RuntimeError(f"telegram {method}: {st} {str(d)[:300]}")
        return d

    def send(self, chat_id, text, buttons=None):
        body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            body["reply_markup"] = {"inline_keyboard": buttons}
        return self.call("sendMessage", body)["result"].get("message_id")


# ---------------------------------------------------------------- Gmail IMAP
class _Strip(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip, self.href = [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v and v.startswith("http"):
                    self.href = v
        if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "td"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip -= 1
        if tag == "a" and self.href:
            self.out.append(f" <{self.href}> ")
            self.href = None

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def html_to_text(s):
    p = _Strip()
    p.feed(s)
    t = html.unescape("".join(p.out))
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def mail_text(msg):
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    content = body.get_content()
    if body.get_content_type() == "text/html":
        content = html_to_text(content)
    return content


class Gmail:
    def __init__(self, user, app_password):
        self.user, self.pw = user, app_password
        self.m = None

    def connect(self):
        self.m = imaplib.IMAP4_SSL("imap.gmail.com")
        self.m.login(self.user, self.pw)
        self.m.select('"[Gmail]/All Mail"', readonly=True)
        return self

    def search_uids(self, criteria):
        typ, data = self.m.uid("search", None, *criteria)
        if typ != "OK":
            raise RuntimeError(f"imap search failed: {criteria}")
        return [int(x) for x in data[0].split()] if data and data[0] else []

    def gmail_raw(self, query):
        """Gmail's own search syntax over IMAP (X-GM-RAW)."""
        q = '"' + query.replace('\\', '').replace('"', '') + '"'
        typ, data = self.m.uid("search", None, "X-GM-RAW", q)
        if typ != "OK":
            raise RuntimeError("imap X-GM-RAW failed")
        return [int(x) for x in data[0].split()] if data and data[0] else []

    def fetch(self, uid):
        typ, data = self.m.uid("fetch", str(uid), "(RFC822)")
        if typ != "OK" or not data or data[0] is None:
            return None
        return email.message_from_bytes(data[0][1], policy=email.policy.default)

    def close(self):
        try:
            self.m.logout()
        except Exception:
            pass


# ---------------------------------------------------------------- shared state (user_settings.settings jsonb)
class Settings:
    def __init__(self, sb):
        self.sb = sb
        rows = sb.select("user_settings", {"owner_id": "eq." + OWNER_ID, "select": "settings"})
        self.s = (rows[0]["settings"] if rows else {}) or {}

    def get(self, k, default=None):
        return self.s.get(k, default)

    def set(self, **kv):
        self.s.update(kv)
        self.sb.update("user_settings", {"owner_id": OWNER_ID}, {"settings": self.s, "updated_at": iso(now_utc())})


def in_quiet_hours(settings):
    q = settings.get("quiet_hours") or {"from": "23:00", "to": "07:00"}
    t = datetime.now(IST).strftime("%H:%M")
    f, to = q.get("from", "23:00"), q.get("to", "07:00")
    return (t >= f or t < to) if f > to else (f <= t < to)


# ---------------------------------------------------------------- Agent run bookkeeping
class Run:
    def __init__(self, sb, agent, model):
        self.sb, self.agent, self.model = sb, agent, model
        self.started = now_utc()
        self.read = self.created = self.parked = 0
        self.errors, self.notes = [], []
        self.id = None

    def finish(self, llm=None, summary=None):
        row = {"agent": self.agent, "started_at": iso(self.started), "finished_at": iso(now_utc()), "items_read": self.read,
               "items_created": self.created, "items_parked": self.parked, "errors": self.errors or None,
               "summary": summary or "; ".join(self.notes)[:2000], "model": self.model}
        if llm:
            row["tokens_in"], row["tokens_out"] = llm.tokens_in, llm.tokens_out
        r = self.sb.insert("agent_runs", row)
        self.id = r[0]["id"] if r else None
        log(f"[{self.agent}] read={self.read} created={self.created} parked={self.parked} errors={len(self.errors)} :: {row['summary'][:160]}")
        return self.id


# ---------------------------------------------------------------- Prompts
EXTRACT_SYS = """EXTRACT_JOBS. You read one job-alert email and return JSON only.
Return {"is_job_alert": bool, "jobs": [{"title","company","location","url","easy_apply"(bool|null),"posted_text"(as written, e.g. "2 days ago", or null),"snippet"(<=200 chars),"stream"(one of the stream names given, or null)}]}.
Rules: one entry per distinct job in the mail; use the job's own link (not unsubscribe/profile links); if the mail is a newsletter, profile nag, course ad or recruiter marketing with no concrete openings, return is_job_alert=false and jobs=[].
Assign "stream" by matching the job against each stream's target titles and goal; null if neither fits."""

FIT_SYS = """SCORE_FIT. You are a strict recruiter screening jobs for one candidate. JSON only.
Input: the candidate's resume, the job stream goal, and a list of jobs (index, title, company, location, snippet). Usually only title/company/location are known, so say so in "basis".
Return {"scores":[{"index":int,"fit_score":0-100,"fit_breakdown":{"basis":str,"role_level":str,"domain":str,"location":str,"must_haves":str,"note":str}}]}.
Scoring: 80+ only when title, seniority and domain all match the stream; 60-79 plausible, worth a look; 40-59 stretch or domain shift; <40 wrong level, wrong function or clearly junior/senior-mismatch. Location outside the stream's cities and not remote: cap at 50. Keep every string under 120 chars."""

STATUS_SYS = """CLASSIFY_STATUS. You read one email about a job application and return JSON only.
Return {"outcome": one of ["rejected","interview_invite","offer","assessment","acknowledgement","other"], "company": str, "verbatim": the exact sentences that state the decision (copy, do not paraphrase; empty if none), "confidence": 0-1}.
"rejected" only when the mail clearly says the candidate is not moving forward for this application."""


# ---------------------------------------------------------------- Sourcer + Fit
def sender_domains(sb):
    doms = set(DEFAULT_SENDERS)
    for a in sb.select("alert_definitions", {"owner_id": "eq." + OWNER_ID, "select": "sender_pattern"}):
        p = (a.get("sender_pattern") or "").replace("from:", "").strip().lower()
        if p:
            doms.add(p.split("@")[-1])
    return doms


def load_context(sb):
    streams = sb.select("job_streams", {"owner_id": "eq." + OWNER_ID, "is_active": "eq.true", "select": "id,name,goal,target_titles,locations,generic_document_id"})
    docs = {d["id"]: d for d in sb.select("documents", {"owner_id": "eq." + OWNER_ID, "type": "eq.resume", "tag": "eq.generic", "select": "id,text,job_stream_id"})}
    boards = {b["name"].lower(): b["id"] for b in sb.select("job_boards", {"owner_id": "eq." + OWNER_ID, "kind": "eq.portal", "select": "id,name,kind"})}
    alerts = sb.select("alert_definitions", {"owner_id": "eq." + OWNER_ID, "select": "id,job_stream_id,sender_pattern,query_text"})
    criteria = sb.select("filter_criteria", {"owner_id": "eq." + OWNER_ID, "is_active": "eq.true", "select": "criterion_type,value,job_stream_id"})
    noise = {n["reason"]: n["id"] for n in sb.select("noise_reasons", {"owner_id": "eq." + OWNER_ID, "select": "id,reason"})}
    return streams, docs, boards, alerts, criteria, noise


def board_for(sender, url, boards):
    s = (sender + " " + (url or "")).lower()
    for name, bid in boards.items():
        key = name.split()[0].lower()
        if len(key) >= 4 and key in s:
            return bid, name
    return None, "manual"


def alert_for(sender, stream_id, alerts):
    for a in alerts:
        p = (a.get("sender_pattern") or "").replace("from:", "").lower()
        if p and p in sender.lower() and a["job_stream_id"] == stream_id:
            return a["id"]
    return None


def title_noise(title, location, stream_id, criteria):
    t, loc = (title or "").lower(), (location or "").lower()
    excl = [c["value"].lower() for c in criteria if c["criterion_type"] == "title_exclude" and c.get("job_stream_id") in (None, stream_id)]
    for x in excl:
        if re.search(r"\b" + re.escape(x) + r"\b", t):
            return "Title excluded"
    allow = [c["value"].lower() for c in criteria if c["criterion_type"] == "location_allow" and c.get("job_stream_id") in (None, stream_id)]
    if loc and allow and not any(a in loc for a in allow) and "remote" not in loc and "india" != loc.strip():
        return "Location not allowed"
    return None


def dedup_key(company, title, location):
    return "|".join(re.sub(r"\s+", " ", (x or "").strip().lower()) for x in (company, title, location))


def sourcer(sb, gmail, llm, settings, run, dry_fixtures=None):
    streams, docs, boards, alerts, criteria, noise = load_context(sb)
    stream_by_name = {s["name"].lower(): s for s in streams}
    stream_desc = "\n".join(f'- "{s["name"]}": goal={s.get("goal") or ""}; target titles={", ".join(s.get("target_titles") or [])}' for s in streams)
    existing = {l["dedup_key"] for l in sb.select("leads", {"owner_id": "eq." + OWNER_ID, "select": "dedup_key", "created_at": "gte." + iso(now_utc() - timedelta(days=45))})}
    existing_msg = {l["email_message_id"] for l in sb.select("leads", {"owner_id": "eq." + OWNER_ID, "select": "email_message_id", "created_at": "gte." + iso(now_utc() - timedelta(days=45))})}
    doms = sender_domains(sb)

    # 1) collect candidate mails
    mails = []
    if dry_fixtures is not None:
        for f in dry_fixtures:
            mails.append({"uid": 0, "msg_id": "<fixture-" + hashlib.md5(f.encode()).hexdigest()[:10] + ">", "from": "jobs-noreply@linkedin.com",
                          "subject": "fixture", "date": now_utc(), "text": f})
    else:
        last_uid = settings.get("imap_last_uid")
        if last_uid:
            uids = gmail.search_uids(["UID", f"{int(last_uid)+1}:*"])
            uids = [u for u in uids if u > int(last_uid)]
        else:
            since = (now_utc() - timedelta(days=2)).strftime("%d-%b-%Y")
            uids = gmail.search_uids(["SINCE", since])
        uids = sorted(uids)[-300:]
        max_uid = int(last_uid or 0)
        for u in uids:
            max_uid = max(max_uid, u)
            msg = gmail.fetch(u)
            if msg is None:
                continue
            frm = (msg.get("From") or "").lower()
            if not any(d in frm for d in doms):
                continue
            mid = msg.get("Message-ID") or f"<uid-{u}>"
            if mid in existing_msg:
                continue
            try:
                dt = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else now_utc()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = now_utc()
            mails.append({"uid": u, "msg_id": mid, "from": frm, "subject": msg.get("Subject") or "", "date": dt, "text": mail_text(msg)[:14000]})
        if max_uid and not sb.dry:
            settings.set(imap_last_uid=max_uid)
    run.read = len(mails)
    log(f"[sourcer] {len(mails)} alert mails to read")

    # 2) extract jobs per mail
    new_leads = []
    for m in mails:
        try:
            out = llm.json(EXTRACT_SYS + "\n\nStreams:\n" + stream_desc, f"From: {m['from']}\nSubject: {m['subject']}\nDate: {m['date']}\n\n{m['text']}")
        except Exception as e:
            run.errors.append({"mail": m["msg_id"], "stage": "extract", "error": str(e)[:300]})
            continue
        if not out.get("is_job_alert"):
            run.notes.append(f"not a job alert: {m['subject'][:60]}")
            continue
        for j in out.get("jobs") or []:
            if not j.get("title") or not j.get("company"):
                continue
            key = dedup_key(j["company"], j["title"], j.get("location"))
            if key in existing:
                run.parked += 1
                continue
            existing.add(key)
            st = stream_by_name.get((j.get("stream") or "").lower()) or streams[0]
            bid, bname = board_for(m["from"], j.get("url"), boards)
            posted = m["date"]
            basis = "email_received"
            pt = (j.get("posted_text") or "").lower()
            mm = re.search(r"(\d+)\s*(day|hour|week)", pt)
            if mm:
                n, unit = int(mm.group(1)), mm.group(2)
                posted = m["date"] - timedelta(**{unit + "s": n})
                basis = "posted_text"
            age = (now_utc() - posted).days
            lead = {"source_platform": bname.lower().split()[0], "title": j["title"][:200], "company": j["company"][:200], "location": (j.get("location") or "")[:120] or None,
                    "url": j.get("url"), "raw_snippet": (j.get("snippet") or "")[:400], "dedup_key": key, "status": "new", "job_board_id": bid,
                    "job_stream_id": st["id"], "alert_definition_id": alert_for(m["from"], st["id"], alerts), "posted_at": iso(posted), "posted_at_basis": basis,
                    "age_days": age, "easy_apply": j.get("easy_apply"), "jd_confidence": "snippet_only", "email_message_id": m["msg_id"]}
            reason = title_noise(lead["title"], lead["location"], st["id"], criteria)
            if age > int(settings.get("freshness_days", 14)):
                reason = "Older than 14 days"
            if reason:
                lead["status"], lead["noise_reason_id"], lead["matched_criterion"] = "parked", noise.get(reason), reason
                run.parked += 1
            new_leads.append(lead)

    # 3) fit scoring for live leads, per stream, batches of 8
    live = [l for l in new_leads if l["status"] == "new"]
    for s in streams:
        batch_all = [l for l in live if l["job_stream_id"] == s["id"]]
        resume = (docs.get(s.get("generic_document_id")) or {}).get("text") or next((d["text"] for d in docs.values() if d["job_stream_id"] == s["id"]), "")
        if not resume:
            run.notes.append(f"stream {s['name']}: no generic resume, leads left unscored")
            continue
        for i in range(0, len(batch_all), 8):
            batch = batch_all[i:i + 8]
            payload = {"stream_goal": s.get("goal"), "stream_locations": s.get("locations"), "resume": resume[:9000],
                       "jobs": [{"index": k, "title": l["title"], "company": l["company"], "location": l["location"], "snippet": l["raw_snippet"]} for k, l in enumerate(batch)]}
            try:
                out = llm.json(FIT_SYS, json.dumps(payload))
                for sc in out.get("scores") or []:
                    l = batch[int(sc["index"])]
                    l["fit_score"], l["fit_breakdown"], l["status"] = sc.get("fit_score"), sc.get("fit_breakdown"), "fit_checked"
            except Exception as e:
                run.errors.append({"stage": "fit", "stream": s["name"], "error": str(e)[:300]})

    # 4) write
    if new_leads:
        for l in new_leads:
            if l["status"] == "fit_checked" and (l.get("fit_score") or 0) < int(settings.get("fit_threshold", 60)) and l.get("fit_score") is not None:
                l["status"], l["noise_reason_id"], l["matched_criterion"] = "parked", noise.get("Fit below threshold"), "Fit below threshold"
                run.parked += 1
        rows = sb.insert("leads", new_leads)
        run.created = len(rows)
        for aid in {l["alert_definition_id"] for l in new_leads if l.get("alert_definition_id")}:
            sb.update("alert_definitions", {"id": aid}, {"last_lead_at": iso(now_utc())})
    return new_leads


# ---------------------------------------------------------------- Notifier
def fmt_lead(l):
    fb = l.get("fit_breakdown") or {}
    return (f"<b>{html.escape(l['title'])}</b> · {html.escape(l['company'])}\n"
            f"{html.escape(l.get('location') or '—')} · fit <b>{l.get('fit_score') if l.get('fit_score') is not None else '?'}</b> · {l.get('age_days', '?')}d old"
            f"{' · easy apply' if l.get('easy_apply') else ''}\n"
            f"{html.escape(str(fb.get('note') or fb.get('domain') or ''))[:160]}")


def buttons_for(l):
    lid = l["id"]
    row1 = [{"text": "Apply generic", "callback_data": f"ag|{lid}"}, {"text": "Tailor", "callback_data": f"tl|{lid}"}]
    row2 = [{"text": "Park", "callback_data": f"pk|{lid}"}, {"text": "Remind tonight", "callback_data": f"rm|{lid}"}]
    if l.get("url"):
        row2.append({"text": "Open", "url": l["url"]})
    return [row1, row2]


def notifier(sb, tg, settings, run):
    chat = settings.get("telegram_chat_id")
    if not chat:
        run.notes.append("no telegram_chat_id yet; send any message to the bot")
        return 0
    if in_quiet_hours(settings):
        run.notes.append("quiet hours; nothing sent")
        return 0
    cap = int(settings.get("daily_cap", 8))
    today_ist = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = len(sb.select("notifications", {"owner_id": "eq." + OWNER_ID, "kind": "eq.new_lead", "sent_at": "gte." + iso(today_ist), "select": "id"}))
    budget = max(0, cap - sent_today)
    if budget == 0:
        run.notes.append(f"daily cap {cap} reached")
        return 0
    notified = {n["lead_id"] for n in sb.select("notifications", {"owner_id": "eq." + OWNER_ID, "kind": "eq.new_lead", "select": "lead_id", "lead_id": "not.is.null"})}
    leads = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.fit_checked", "fit_score": "gte." + str(settings.get("fit_threshold", 60)),
                                "select": "id,title,company,location,url,fit_score,fit_breakdown,age_days,easy_apply,created_at", "order": "fit_score.desc,created_at.desc", "limit": "50"})
    leads = [l for l in leads if l["id"] not in notified][:budget]
    n = 0
    for l in leads:
        text = "🆕 New lead\n" + fmt_lead(l) + "\n\nHow do you want to proceed?"
        try:
            mid = tg.send(chat, text, buttons_for(l))
            sb.insert("notifications", {"channel": "telegram", "kind": "new_lead", "lead_id": l["id"], "message_text": text,
                                        "options_offered": ["apply_generic", "tailor", "park", "remind_tonight", "open"], "sent_at": iso(now_utc())})
            n += 1
        except Exception as e:
            run.errors.append({"stage": "notify", "lead": l["id"], "error": str(e)[:300]})
    run.created = n
    return n


# ---------------------------------------------------------------- Replies (Telegram buttons)
def handle_action(sb, action, lead_id, settings):
    leads = sb.select("leads", {"id": "eq." + lead_id, "select": "*"})
    if not leads:
        return "Lead not found."
    l = leads[0]
    streams = sb.select("job_streams", {"id": "eq." + l["job_stream_id"], "select": "id,generic_document_id"})
    st = streams[0] if streams else {"id": PM_STREAM}
    nowi = iso(now_utc())
    if action in ("ag", "tl"):
        if l.get("promoted_application_id"):
            return "Already an application."
        decision = "tailored" if action == "tl" else "generic"
        app = sb.insert("applications", {"lead_id": l["id"], "job_stream_id": st["id"], "title": l["title"], "company": l["company"], "location": l.get("location"), "url": l.get("url"),
                                         "job_board_id": l.get("job_board_id"), "source_platform": l.get("source_platform"), "status": "applied", "applied_date": today_ist().isoformat(),
                                         "apply_channel": "easy_apply" if l.get("easy_apply") else "website", "resume_decision": decision, "decision_reason": "telegram reply",
                                         "fit_score": l.get("fit_score"), "fit_breakdown": l.get("fit_breakdown"), "needs_tailored_resume": decision == "tailored", "final_status": "open",
                                         "next_action": "Submit on portal" if decision == "generic" else "Tailor resume, then submit", "next_action_due": today_ist().isoformat()})[0]
        sb.update("leads", {"id": l["id"]}, {"status": "promoted", "promoted_application_id": app["id"]})
        sb.insert("status_history", {"application_id": app["id"], "from_status": None, "to_status": "applied", "changed_at": nowi, "cause": "telegram", "message_text": f"Created from Telegram ({decision})"})
        gid = st.get("generic_document_id")
        if gid:
            if decision == "tailored":
                g = sb.select("documents", {"id": "eq." + gid, "select": "text"})
                d = sb.insert("documents", {"job_stream_id": st["id"], "type": "resume", "tag": "tailored", "tailored_for_company": l["company"], "derived_from_document_id": gid,
                                            "version_label": f"Tailored · {l['company']} · {today_ist().isoformat()}", "text": (g[0]["text"] if g else None), "status": "draft"})[0]
                sb.insert("application_documents", {"application_id": app["id"], "document_id": d["id"], "role": "resume", "sent_at": None})
                sb.insert("agent_questions", {"about_table": "applications", "about_id": app["id"], "status": "open",
                                              "question": f"Tailor the resume for {l['company']} – {l['title']}. Draft copy is in the library (status draft). Open Cowork to tailor it."})
            else:
                sb.insert("application_documents", {"application_id": app["id"], "document_id": gid, "role": "resume", "sent_at": nowi})
        link = f"{APP_URL}#app={app['id']}"
        if decision == "generic":
            return f"✅ Recorded: apply with the generic resume.\nNow submit it: {l.get('url') or '(no link)'}\nApplication: {link}"
        return f"✂️ Queued for tailoring. A draft copy is in the resume library; open it in Cowork to tailor, then submit.\nApplication: {link}"
    if action == "pk":
        noise = {n["reason"]: n["id"] for n in sb.select("noise_reasons", {"owner_id": "eq." + OWNER_ID, "select": "id,reason"})}
        sb.update("leads", {"id": l["id"]}, {"status": "parked", "noise_reason_id": noise.get("Parked by you"), "matched_criterion": "Parked by you"})
        return "🅿️ Parked."
    if action == "rm":
        due = datetime.now(IST).replace(hour=20, minute=30, second=0, microsecond=0)
        if due < datetime.now(IST):
            due += timedelta(days=1)
        sb.insert("notifications", {"channel": "telegram", "kind": "reminder", "lead_id": l["id"], "message_text": "Reminder: " + l["title"] + " · " + l["company"],
                                    "options_offered": ["apply_generic", "tailor", "park"], "sent_at": None, "reply_text": "due:" + iso(due)})
        return f"⏰ Will remind you at {due.strftime('%H:%M')} IST."
    return "Unknown action."


def replies(sb, tg, settings, run):
    offset = int(settings.get("telegram_update_offset") or 0)
    body = {"timeout": 0, "allowed_updates": ["message", "callback_query"]}
    if offset:
        body["offset"] = offset + 1
    d = tg.call("getUpdates", body)
    updates = d.get("result") or []
    chat = settings.get("telegram_chat_id")
    chat = int(chat) if chat else None
    last = offset
    for u in updates:
        last = max(last, u["update_id"])
        run.read += 1
        msg = u.get("message")
        cq = u.get("callback_query")
        if msg and not chat:
            chat = msg["chat"]["id"]
            settings.set(telegram_chat_id=chat)
            tg.send(chat, f"✅ Linked. This chat now receives your job leads.\nApp: {APP_URL}")
            run.notes.append(f"linked chat {chat}")
            continue
        if msg and chat and msg["chat"]["id"] == chat and (msg.get("text") or "").strip().lower() in ("/start", "/status", "status"):
            tg.send(chat, status_line(sb))
            continue
        if cq:
            if not chat or cq["message"]["chat"]["id"] != chat:
                tg.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Not your bot."})
                continue
            action, _, lead_id = (cq.get("data") or "").partition("|")
            try:
                reply = handle_action(sb, action, lead_id, settings)
                run.created += 1
            except Exception as e:
                reply = "Failed: " + str(e)[:150]
                run.errors.append({"stage": "reply", "lead": lead_id, "error": str(e)[:300]})
            tg.call("answerCallbackQuery", {"callback_query_id": cq["id"]})
            try:
                tg.call("editMessageReplyMarkup", {"chat_id": chat, "message_id": cq["message"]["message_id"], "reply_markup": {"inline_keyboard": []}})
            except Exception:
                pass
            tg.send(chat, reply)
            nots = sb.select("notifications", {"lead_id": "eq." + lead_id, "kind": "eq.new_lead", "select": "id,sent_at"})
            for n in nots:
                mins = None
                try:
                    mins = int((now_utc() - datetime.fromisoformat(n["sent_at"].replace("Z", "+00:00"))).total_seconds() // 60)
                except Exception:
                    pass
                sb.update("notifications", {"id": n["id"]}, {"replied_at": iso(now_utc()), "action_taken": action, "minutes_to_reply": mins})
    if last != offset and not sb.dry:
        settings.set(telegram_update_offset=last)
    # due reminders
    if chat and not in_quiet_hours(settings):
        for n in sb.select("notifications", {"owner_id": "eq." + OWNER_ID, "kind": "eq.reminder", "sent_at": "is.null", "select": "id,lead_id,reply_text,message_text"}):
            due = (n.get("reply_text") or "")[4:]
            try:
                if datetime.fromisoformat(due) > now_utc():
                    continue
            except Exception:
                pass
            l = sb.select("leads", {"id": "eq." + n["lead_id"], "select": "id,title,company,location,url,fit_score,fit_breakdown,age_days,easy_apply"})
            if l:
                tg.send(chat, "⏰ Reminder\n" + fmt_lead(l[0]), buttons_for(l[0]))
            sb.update("notifications", {"id": n["id"]}, {"sent_at": iso(now_utc())})
    return len(updates)


def status_line(sb):
    apps = sb.select("applications", {"owner_id": "eq." + OWNER_ID, "select": "status", "final_status": "eq.open"})
    leads = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.fit_checked", "select": "id"})
    by = {}
    for a in apps:
        by[a["status"]] = by.get(a["status"], 0) + 1
    return "📊 Open applications: " + (", ".join(f"{k} {v}" for k, v in sorted(by.items())) or "none") + f"\nLeads waiting: {len(leads)}\n{APP_URL}"


# ---------------------------------------------------------------- Nightly: status sync + sweeps + digest
def status_sync(sb, gmail, llm, settings, run):
    apps = sb.select("applications", {"owner_id": "eq." + OWNER_ID, "final_status": "eq.open", "select": "id,company,title,status,rejection_email_id"})
    run.read = len(apps)
    seen_ids = {a.get("rejection_email_id") for a in apps}
    for a in apps:
        comp = (a["company"] or "").strip()
        if len(comp) < 3:
            continue
        try:
            uids = gmail.gmail_raw(f'newer_than:3d -from:me {comp}')
        except Exception as e:
            run.errors.append({"stage": "status_search", "company": comp, "error": str(e)[:200]})
            continue
        for u in uids[-5:]:
            msg = gmail.fetch(u)
            if msg is None:
                continue
            mid = msg.get("Message-ID") or f"<uid-{u}>"
            if mid in seen_ids:
                continue
            frm = (msg.get("From") or "").lower()
            if any(d in frm for d in DEFAULT_SENDERS) and "linkedin" in frm and "jobs-noreply" in frm:
                continue  # alert mails, not status mails
            text = mail_text(msg)[:8000]
            if comp.lower() not in (text + (msg.get("Subject") or "")).lower():
                continue
            try:
                out = llm.json(STATUS_SYS, f"Application: {a['title']} at {comp}\nFrom: {frm}\nSubject: {msg.get('Subject')}\n\n{text}")
            except Exception as e:
                run.errors.append({"stage": "status_classify", "company": comp, "error": str(e)[:200]})
                continue
            oc, conf = out.get("outcome"), float(out.get("confidence") or 0)
            if conf < 0.7 or oc in ("other", "acknowledgement"):
                continue
            nowi = iso(now_utc())
            if oc == "rejected" and a["status"] != "rejected":
                sb.update("applications", {"id": a["id"]}, {"status": "rejected", "final_status": "rejected", "closed_at": nowi, "rejection_message": out.get("verbatim") or text[:2000],
                                                             "rejection_received_at": nowi, "rejection_email_id": mid, "updated_at": nowi})
                sb.insert("status_history", {"application_id": a["id"], "from_status": a["status"], "to_status": "rejected", "changed_at": nowi, "cause": "email", "source_ref": mid, "message_text": out.get("verbatim")})
                sb.upsert_ignore("post_mortems", {"application_id": a["id"], "final_status": "rejected", "written_by": "runner"}, "application_id")
                run.created += 1
                run.notes.append(f"rejected: {comp}")
                seen_ids.add(mid)
            elif oc in ("interview_invite", "assessment", "offer"):
                sb.insert("agent_questions", {"about_table": "applications", "about_id": a["id"], "status": "open",
                                              "question": f"Mail from {comp} looks like {oc.replace('_', ' ')}: \"{(out.get('verbatim') or '')[:200]}\". Update the round and add the interview?"})
                sb.update("applications", {"id": a["id"]}, {"rejection_email_id": mid})  # marks the mail as seen without changing status
                run.created += 1
                run.notes.append(f"{oc}: {comp}")
                seen_ids.add(mid)


def sweeps(sb, settings, run):
    lines = []
    today = today_ist()
    stale_d, ghost_d = int(settings.get("stale_days", 10)), int(settings.get("ghost_days", 30))
    apps = sb.select("applications", {"owner_id": "eq." + OWNER_ID, "final_status": "eq.open", "select": "id,company,title,status,updated_at,next_action,next_action_due,applied_date"})
    for a in apps:
        try:
            upd = datetime.fromisoformat(a["updated_at"].replace("Z", "+00:00"))
        except Exception:
            upd = now_utc()
        idle = (now_utc() - upd).days
        if a["status"] == "applied" and idle >= ghost_d:
            sb.update("applications", {"id": a["id"]}, {"status": "ghosted", "final_status": "ghosted", "closed_at": iso(now_utc()), "updated_at": iso(now_utc())})
            sb.insert("status_history", {"application_id": a["id"], "from_status": "applied", "to_status": "ghosted", "changed_at": iso(now_utc()), "cause": "sweep", "message_text": f"No movement for {idle} days"})
            lines.append(f"👻 Ghosted after {idle}d: {a['company']} · {a['title']}")
        elif a["status"] in ("applied", "screening") and idle >= stale_d:
            lines.append(f"🕰 Stale {idle}d: {a['company']} · {a['title']} — follow up?")
        if a.get("next_action_due") and a["next_action_due"] < today.isoformat():
            lines.append(f"⚠️ Overdue: {a['company']} · {a.get('next_action')} (due {a['next_action_due']})")
    for iv in sb.select("interviews", {"owner_id": "eq." + OWNER_ID, "debriefed_at": "is.null", "interview_date": "lte." + today.isoformat(), "select": "id,application_id,round_number,interview_date"}):
        app = next((a for a in apps if a["id"] == iv["application_id"]), None)
        if app:
            lines.append(f"🎙 Debrief pending: {app['company']} round {iv['round_number']} ({iv['interview_date']})")
    cutoff = iso(now_utc() - timedelta(days=7))
    for al in sb.select("alert_definitions", {"owner_id": "eq." + OWNER_ID, "select": "id,query_text,last_lead_at,sender_pattern"}):
        if not al.get("last_lead_at") or al["last_lead_at"] < cutoff:
            lines.append(f"📭 No leads 7d: {al.get('sender_pattern') or ''} · {al['query_text'][:50]}")
    # park old, never-notified leads
    fresh = int(settings.get("freshness_days", 14))
    old = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.fit_checked", "created_at": "lt." + iso(now_utc() - timedelta(days=fresh)), "select": "id"})
    if old:
        noise = {n["reason"]: n["id"] for n in sb.select("noise_reasons", {"owner_id": "eq." + OWNER_ID, "select": "id,reason"})}
        for l in old:
            sb.update("leads", {"id": l["id"]}, {"status": "parked", "noise_reason_id": noise.get("Older than 14 days"), "matched_criterion": "Older than 14 days"})
        run.parked = len(old)
        lines.append(f"🗄 Parked {len(old)} leads older than {fresh}d")
    waiting = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.fit_checked", "select": "id"})
    run.created = len(lines)
    return lines, len(waiting)


# ---------------------------------------------------------------- verify
def verify(env):
    ok = True
    def chk(name, fn):
        nonlocal ok
        try:
            r = fn()
            log(f"OK   {name}: {r}")
        except Exception as e:
            ok = False
            log(f"FAIL {name}: {e}")
    chk("supabase", lambda: f"{len(Supabase(env['SUPABASE_URL'], env['SUPABASE_SERVICE_KEY']).select('job_streams', {'select': 'id', 'owner_id': 'eq.' + OWNER_ID}))} streams")
    chk("gmail imap", lambda: (lambda g: (g.close(), "login ok")[1])(Gmail(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"]).connect()))
    sb = Supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_KEY"])
    settings = Settings(sb)
    g = Gemini(env["GEMINI_API_KEY"], env.get("GEMINI_MODEL") or "auto", remember=lambda m: settings.set(gemini_model=m))
    chk("gemini", lambda: (g.json("Return JSON {\"ok\":true}", "ping"), g.model)[1])
    tg = Telegram(env["TELEGRAM_BOT_TOKEN"])
    chk("telegram", lambda: tg.call("getMe")["result"]["username"])
    run = Run(sb, "verify", "-")
    chk("telegram link", lambda: f"{replies(sb, tg, settings, run)} updates; chat_id={settings.get('telegram_chat_id')}")
    if settings.get("telegram_chat_id"):
        chk("telegram test message", lambda: tg.send(settings.get("telegram_chat_id"), f"✅ Job Driver runner v{VERSION} is live. " + status_line(sb)))
    else:
        log("INFO telegram: open your bot in Telegram, press Start, send 'hi', then run verify again")
    return ok


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "nightly", "verify"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    env = {k: os.environ.get(k, "") for k in ["GMAIL_USER", "GMAIL_APP_PASSWORD", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GEMINI_MODEL"]}
    missing = [k for k in ["GMAIL_USER", "GMAIL_APP_PASSWORD", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"] if not env[k]]
    dry = args.dry_run or bool(missing)
    if missing:
        log(f"missing secrets {missing} -> dry run")
    if args.mode == "verify":
        if missing:
            log("verify needs every secret; aborting")
            sys.exit(2)
        sys.exit(0 if verify(env) else 1)

    model = env.get("GEMINI_MODEL") or "auto"
    if dry:
        sb = DrySupabase()
        llm = Gemini("", model, dry=True)
        tg = Telegram("dry", dry=True)
        tg.dry_updates = [{"update_id": 101, "callback_query": {"id": "cq1", "data": "ag|lead-old", "message": {"message_id": 7, "chat": {"id": 1}}}},
                          {"update_id": 102, "callback_query": {"id": "cq2", "data": "tl|lead-old", "message": {"message_id": 8, "chat": {"id": 1}}}},
                          {"update_id": 103, "message": {"chat": {"id": 1}, "text": "status"}}]
        settings = Settings(sb)
        gmail = None
        fixtures = [open(os.path.join(os.path.dirname(__file__), "fixtures", f)).read() for f in sorted(os.listdir(os.path.join(os.path.dirname(__file__), "fixtures"))) if f.endswith(".txt")]
    else:
        sb = Supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_KEY"])
        settings = Settings(sb)
        llm = Gemini(env["GEMINI_API_KEY"], model if model != "auto" else (settings.get("gemini_model") or "auto"),
                     remember=lambda m: settings.set(gemini_model=m))
        tg = Telegram(env["TELEGRAM_BOT_TOKEN"])
        gmail = Gmail(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"]).connect()
        fixtures = None

    failures = 0
    try:
        if args.mode == "run":
            r = Run(sb, "sourcer+fit", model)
            try:
                sourcer(sb, gmail, llm, settings, r, dry_fixtures=fixtures)
            except Exception as e:
                r.errors.append({"stage": "sourcer", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]}); failures += 1
            r.finish(llm)
            r = Run(sb, "notifier", "-")
            try:
                notifier(sb, tg, settings, r)
            except Exception as e:
                r.errors.append({"stage": "notifier", "error": str(e)[:300]}); failures += 1
            r.finish()
            r = Run(sb, "replies", "-")
            try:
                replies(sb, tg, settings, r)
            except Exception as e:
                r.errors.append({"stage": "replies", "error": str(e)[:300]}); failures += 1
            r.finish()
        else:
            r = Run(sb, "status_sync", model)
            try:
                if gmail:
                    status_sync(sb, gmail, llm, settings, r)
                else:
                    r.notes.append("dry run: status sync skipped (needs Gmail)")
            except Exception as e:
                r.errors.append({"stage": "status_sync", "error": str(e)[:300]}); failures += 1
            r.finish(llm)
            r = Run(sb, "sweeps", "-")
            lines, waiting = [], 0
            try:
                lines, waiting = sweeps(sb, settings, r)
            except Exception as e:
                r.errors.append({"stage": "sweeps", "error": str(e)[:300]}); failures += 1
            r.finish()
            chat = settings.get("telegram_chat_id")
            if chat:
                digest = "🌙 Nightly\n" + ("\n".join(lines) if lines else "Nothing overdue, nothing stale.") + f"\nLeads waiting in Inbox: {waiting}\n{APP_URL}"
                tg.send(chat, digest)
    finally:
        if gmail:
            gmail.close()
    if dry:
        print("\n===== DRY RUN PLAN =====")
        for p in sb.planned:
            print(json.dumps(p, default=str)[:600])
        for s in tg.sent:
            print("TELEGRAM", json.dumps(s, default=str)[:400])
        print(f"planned writes: {len(sb.planned)}, telegram messages: {len(tg.sent)}")
    sys.exit(1 if failures else 0)


class DrySupabase(Supabase):
    """In-memory stand-in: serves the fixture context, records every write."""
    def __init__(self):
        super().__init__("https://dry.invalid", "dry", dry=True)
        self.tables = {
            "user_settings": [{"settings": {"channel": "telegram", "daily_cap": 8, "quiet_hours": {"from": "23:00", "to": "07:00"}, "fit_threshold": 60, "freshness_days": 14, "stale_days": 10, "ghost_days": 30, "telegram_chat_id": 1}}],
            "job_streams": [{"id": PM_STREAM, "is_active": True, "name": "Product management", "goal": "AI / senior PM role", "target_titles": ["Product Manager", "Senior Product Manager"], "locations": ["Chennai", "Remote"], "generic_document_id": "doc1"},
                            {"id": "11111111-1111-4111-8111-000000000002", "is_active": True, "name": "Defence market entry", "goal": "programme manager / pre-sales in defence", "target_titles": ["Programme Manager", "Pre-sales"], "locations": ["Chennai"], "generic_document_id": None}],
            "documents": [{"id": "doc1", "type": "resume", "tag": "generic", "text": "SUDHARSAN R · AI Product Manager · 9 years B2B SaaS", "job_stream_id": PM_STREAM}],
            "job_boards": [{"id": "b-li", "name": "LinkedIn", "kind": "portal"}, {"id": "b-nk", "name": "Naukri", "kind": "portal"}],
            "alert_definitions": [{"id": "al1", "job_stream_id": PM_STREAM, "sender_pattern": "from:jobs-noreply@linkedin.com", "query_text": "Product Manager", "last_lead_at": None}],
            "filter_criteria": [{"criterion_type": "title_exclude", "value": "Project Manager", "job_stream_id": None}, {"criterion_type": "location_allow", "value": "Chennai", "job_stream_id": None}, {"criterion_type": "location_allow", "value": "Remote", "job_stream_id": None}],
            "noise_reasons": [{"id": "n1", "reason": "Title excluded"}, {"id": "n2", "reason": "Location not allowed"}, {"id": "n3", "reason": "Fit below threshold"}, {"id": "n4", "reason": "Older than 14 days"}, {"id": "n5", "reason": "Parked by you"}],
            "leads": [{"dedup_key": "existing co|product manager|chennai", "email_message_id": "<old>", "status": "fit_checked", "job_stream_id": PM_STREAM, "job_board_id": "b-li", "source_platform": "linkedin", "fit_score": 70, "id": "lead-old", "title": "Product Manager", "company": "Existing Co", "location": "Chennai", "url": "https://x/1", "fit_breakdown": {"note": "old"}, "age_days": 3, "easy_apply": True, "created_at": iso(now_utc())}],
            "notifications": [], "applications": [], "interviews": [],
        }

    def select(self, table, params):
        rows = self.tables.get(table, [])
        out = []
        for r in rows:
            keep = True
            for k, v in params.items():
                if k in ("select", "order", "limit", "owner_id"):
                    continue
                op, _, val = v.partition(".")
                if k not in r:
                    continue  # fixture rows omit columns that only matter in the real database
                rv = r.get(k)
                if op == "eq" and str(rv) != val and not (val == "true" and rv is True):
                    keep = False
                if op == "is" and val == "null" and rv is not None:
                    keep = False
                if op == "not" and rv is None:
                    keep = False
            if keep:
                out.append(dict(r))
        return out

    def insert(self, table, rows):
        res = super().insert(table, rows)
        self.tables.setdefault(table, []).extend(res)
        return res

    def update(self, table, match, patch):
        for r in self.tables.get(table, []):
            if all(str(r.get(k)) == str(v) for k, v in match.items()):
                r.update(patch)
        return super().update(table, match, patch)


if __name__ == "__main__":
    main()
