#!/usr/bin/env python3
# Job Application Driver · permanent runner · v1.0.18 · 27 Oct 2026 · v1.0.18: "My calls" check: every job you label (fit band or Generic/Tailored) is scored by Gemini and Jev on the active rubric, gates included, into agent_evals.ai_results (6 per pass, never touches leads). v1.0.17 · 27 Oct 2026 · v1.0.17: mandatory gates per stream (rubric.gates: location, years asked, product role, or any yes/no question) checked BEFORE weighted fit; a failed gate parks the lead with the reason, a gate the job does not state lets it through with a flag; experience graded by rule from the years the JD asks for; Jev questions ask about the job only (rubric param 'ask', plain levels); gate sweep re-checks and re-scores live leads on the active rubric; career notes synthesised daily from the portfolio (settings.career_notes_auto) plus your Extra notes. v1.0.16 · 25 Oct 2026 · v1.0.16: (a) the nightly digest no longer reports alerts that brought no leads ("No leads 7d" lines are gone), and on a night with nothing to act on (nothing ghosted, stale, overdue or debrief pending; parking old leads alone does not count) no digest is sent at all; (b) every failed or crashed agent run sends a Telegram message: one message per failure streak per agent (not one every pass), a one-line "working again" when it recovers, and failures during quiet hours are reported after quiet hours end. The old "3 failures in a row" and "setup error twice" alerts are folded into this; missed-slot alerts are unchanged. v1.0.15: Jev called DIRECTLY on TypeSafe (POST https://api.typesafe.ai/v1/systemone, model jev-latest, secret TYPESAFE_API_KEY or TYPEFACE_API_KEY or JEV_API_KEY); yes/no questions sent as "noul" and read back into the same shape; Vercel AI Gateway (AI_GATEWAY_API_KEY) only when no direct key is set; Jev cost estimated from tokens. v1.0.14: the JD backlog (filling job descriptions for earlier leads and open applications) is off by default; only new leads get a JD. Switch back on with user_settings.settings.jd_backlog = true. v1.0.13: agent run log. Every agent run writes its agent_runs row when it STARTS (status running) and fills it in at the end with status (success / partial / failed / skipped), error kinds (ai_busy, ai_limit, setup, format, network, gmail, jd_fetch, other), AI calls made, whether the Groq backup was used, and a link to the GitHub run. A row still 'running' after 40 minutes is marked crashed at the start of the next pass. Leads created by the sourcer carry agent_run_id. Telegram alert, at most once a day per agent and never in quiet hours, when an agent fails or crashes 3 runs in a row, hits a setup error twice in a row, or misses its slot (nightly agents after 30 h, every-N-hours agents after 1.5x N + 2 h). v1.0.12: Resume Decider no longer spends a lead's 3 tries on outages (Jev 402/403 no credits, Gemini/Groq 429/503, no model left); it stops for the run, leaves the lead "not yet run" with the reason, and retries next pass. After the first Jev "no credits" reply, Jev is skipped for the rest of the run. v1.0.11: Jev (TypeSafe, via Vercel AI Gateway, secret AI_GATEWAY_API_KEY) as the judge for the new Resume Decider (picklist generic / tailored / not_run / failed on leads; per-stream criteria from the Agents screen; Jev scores each criterion, code applies weights and threshold; Gemini/Groq as backup; low-confidence flag; Failed after 3 tries) and as a shadow fit scorer (leads.fit_shadow, never used for decisions until it passes the eval gate). v1.0.10: fit replies are normalised before the format check (a bare list of scores, a single score object, or scores under "results"/"jobs" are accepted), and a reply that still fails is logged with its first 200 characters. v1.0.9: JD Fetcher (v1.0.8) merged with the agents config. Reads the Agents screen (public.agents) on every pass: on/off, schedule (every pass / every N hours / nightly), model order and per-agent model names, max items, guardrails (max AI calls, rules-first, min confidence, basis required), the active prompt version, and the per-stream fitment rubric (the AI scores each parameter, this code does the weighted total, if-unknown rule and hard caps); processes eval runs queued in the app (never writes leads); records last run per agent. The JD Fetcher has its own agent row (on/off, max pages per run); JD re-scoring uses the rubric; fit batch defaults to 4. Falls back to built-in behaviour if the agents table cannot be read. v1.0.8: JD Fetcher. Every live lead gets its full job description (LinkedIn public job page, no login; else the company's own apply/careers page via JSON-LD or page text) saved in leads.jd_text before Fit runs, and Fit now scores against the JD (batches of 4). Earlier leads and open applications without a JD are filled in later runs (max 3 tries each, then jd_confidence=fetch_failed). Leads already scored get re-scored once their JD lands. v1.0.7: a missed nightly is caught up only after quiet hours (no digest at 2-3 am). v1.0.6: Groq (free tier, secret GROQ_API_KEY) as automatic backup when Gemini is over its limit or fails; runs every 2 hours (workflow), so nightly work now also catches up after midnight if the 21:36 slot was missed. v1.0.5: after a Gemini 429 the runner pauses Gemini for 60 min (no wasted calls every 15 min); the limit warning waits for the end of quiet hours instead of pinging at night. v1.0.4: retry list (a mail that fails at Gemini or misses the time budget is retried up to 3 runs, never silently lost), LinkedIn alert mails read by fixed rules (Gemini only for unknown formats), daily Gemini call counter + one Telegram warning per day on a 429, nightly work also runs inside any run after 21:36 IST if not yet done today (schedule-proof). v1.0.3: max 25 mails per run, 5-min extraction budget, cursor saved only for processed mails, Gemini timeout 75s and a mail is skipped after one timeout. v1.0.2: Gemini candidates pinged newest-first (30s each), thinking low, working model remembered in user_settings. v1.0.1: model auto-discovery
# Runs on GitHub Actions (free), no laptop needed. Python 3.11+, standard library only.
#
# Modes
#   run       every 15 min: Sourcer (Gmail IMAP) -> Fit (Gemini) -> Notifier (Telegram) -> Replies (Telegram buttons)
#   nightly   once a day:   Status Sync (rejection/interview mails) -> Sweeps (stale, ghost, debrief, overdue, lead health) -> digest
#   verify    one-off:      checks every secret and connection, sends a Telegram test message
#   --dry-run any mode:     fixtures instead of Gmail, fake LLM instead of Gemini, nothing written, nothing sent; prints the plan
#
# Secrets (GitHub Actions secrets -> env): GMAIL_USER, GMAIL_APP_PASSWORD, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN,
#   SUPABASE_URL, SUPABASE_SERVICE_KEY. Optional: GEMINI_MODEL (default auto = newest free Flash model), OWNER_ID,
#   AI_GATEWAY_API_KEY (Vercel AI Gateway, for Jev), JEV_MODEL (default typesafe-ai/jev).
# Design doc: PMOS/JobTracker/job-application-driver-design-v1.7.html (sections 8, 11, 12).

import argparse, math, email, email.policy, email.utils, hashlib, html, imaplib, json, os, re, sys, time, traceback, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone, date
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

VERSION = "1.0.13"
IST = ZoneInfo("Asia/Kolkata")
OWNER_ID = os.environ.get("OWNER_ID", "f0c721b5-e317-49c4-b02c-d7822411fa55")  # sudharsan454@gmail.com auth user
PM_STREAM = "11111111-1111-4111-8111-000000000001"
APP_URL = "https://sudharsan454.github.io/jobs/"
DEFAULT_SENDERS = ["linkedin.com", "naukri.com", "instahyre.com", "iimjobs.com", "hirist.com", "cutshort.io",
                   "wellfound.com", "indeed.com", "glassdoor.com", "foundit.in", "hiring.cafe", "ycombinator.com", "joblet.in"]
OPEN_STATUSES = ["applied", "screening", "round_1", "round_2", "round_3", "offer"]
MAX_MAILS_PER_RUN = 25       # Gemini free tier is rate-limited; the rest carry over to the next run
EXTRACT_BUDGET_S = 300       # stop reading mails after 5 min so push + replies always run inside the job
MAX_MAIL_TRIES = 3           # a mail that keeps failing is dropped after 3 runs (logged with its message id)
JD_MAX_PER_RUN = 20          # job pages fetched per run (new leads + backlog)
JD_BUDGET_S = 180            # time budget for JD fetching per run
JD_PAUSE_S = 4               # pause between LinkedIn page fetches
JD_MAX_TRIES = 3             # a JD that keeps failing is marked fetch_failed after 3 runs
JD_STORE_MAX = 30000         # max chars stored per JD
JD_FOR_FIT = 3500            # JD chars sent to the fit model per job
FIT_BATCH = 4                # jobs per fit call (smaller now that full JDs go in)
NIGHTLY_AT = "21:36"         # IST; nightly work runs in the first run at or after this time each day


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
        self.calls = 0          # HTTP generateContent calls this run (pings included)
        self.n429 = 0           # 429 answers this run
        self.gave_up_429 = False

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

    def _call(self, model, system, user, max_tokens, timeout=75, thinking=True):
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}}
        if thinking:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        self.calls += 1
        try:
            st, d = http("POST", self._url(model), body, timeout=timeout)
        except Exception as e:  # timeouts, resets
            return 599, {"error": str(e)[:200]}
        if st == 429:
            self.n429 += 1
        if st == 400 and thinking and "thinking" in str(d).lower():
            return self._call(model, system, user, max_tokens, timeout, thinking=False)
        return st, d

    def json(self, system, user, max_tokens=4096, model=None, timeout=75):
        if self.dry:
            return FakeLLM.answer(system, user)
        if self.gave_up_429:
            raise RuntimeError("gemini 429 (limit): paused, not calling again this run")
        if not model and self.model in ("", "auto", None):
            self.discover()
        for attempt in range(3):
            use = model or self.model
            st, d = self._call(use, system, user, max_tokens, timeout=timeout or 75)
            if st == 200:
                um = d.get("usageMetadata", {})
                self.tokens_in += um.get("promptTokenCount", 0)
                self.tokens_out += um.get("candidatesTokenCount", 0)
                try:
                    txt = d["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt)
                except Exception as e:
                    raise RuntimeError(f"gemini bad json: {e} {str(d)[:300]}")
            if st == 404 and attempt == 0:
                if model:
                    log(f"gemini {model} (set in the app) 404; using the auto-picked model")
                    model = None
                    if self.model in ("", "auto", None):
                        self.discover()
                    continue
                log(f"gemini {self.model} 404; re-discovering")
                self.discover()
                continue
            if st == 599:
                raise RuntimeError(f"gemini timeout on {use}: {str(d)[:120]}")
            if st in (429, 500, 503) and attempt < 2:
                wait = 20 * (attempt + 1)
                log(f"gemini {st}, retry in {wait}s")
                time.sleep(wait)
                continue
            if st == 429:
                self.gave_up_429 = True
                raise RuntimeError("gemini 429 (limit): gave up after retries")
            raise RuntimeError(f"gemini {st}: {str(d)[:300]}")
        raise RuntimeError("gemini: gave up after retries")


class Groq:
    """Groq free tier via its OpenAI-style API. Backup brain when Gemini is over its limit or failing."""
    PREFER = ["gpt-oss-120b", "gpt-oss-20b", "llama-3.3-70b", "qwen"]

    def __init__(self, key, model=""):
        self.key, self.model = key, model
        self.h = {"Authorization": "Bearer " + key}
        self.calls = self.n429 = self.tokens_in = self.tokens_out = 0
        self.gave_up_429 = False

    def pick_model(self):
        st, d = http("GET", "https://api.groq.com/openai/v1/models", headers=self.h, timeout=30)
        if st != 200:
            raise RuntimeError(f"groq models {st}: {str(d)[:200]}")
        ids = [m["id"] for m in d.get("data", []) if m.get("active", True)]
        for pref in self.PREFER:
            hit = next((i for i in ids if pref in i), None)
            if hit:
                self.model = hit
                return hit
        raise RuntimeError("groq: no preferred model in " + ", ".join(ids[:15]))

    def json(self, system, user, max_tokens=4096, model=None, timeout=75):
        if self.gave_up_429:
            raise RuntimeError("groq 429 (limit): paused this run")
        if not model and not self.model:
            self.pick_model()
        body = {"model": model or self.model, "temperature": 0.1, "max_completion_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system + "\nReply with one JSON object only."}, {"role": "user", "content": user[:24000]}]}
        if "gpt-oss" in body["model"]:
            body["reasoning_effort"] = "low"
        for attempt in range(2):
            self.calls += 1
            try:
                st, d = http("POST", "https://api.groq.com/openai/v1/chat/completions", body, headers=self.h, timeout=timeout or 75)
            except Exception as e:
                raise RuntimeError(f"groq timeout: {str(e)[:120]}")
            if st == 400 and "reasoning_effort" in body:
                body.pop("reasoning_effort")
                continue
            if st == 200:
                u = d.get("usage") or {}
                self.tokens_in += u.get("prompt_tokens", 0)
                self.tokens_out += u.get("completion_tokens", 0)
                try:
                    return json.loads(d["choices"][0]["message"]["content"])
                except Exception as e:
                    raise RuntimeError(f"groq bad json: {e}")
            if st == 429:
                self.n429 += 1
                if attempt == 0:
                    time.sleep(15)
                    continue
                self.gave_up_429 = True
                raise RuntimeError("groq 429 (limit): gave up")
            raise RuntimeError(f"groq {st}: {str(d)[:300]}")
        raise RuntimeError("groq: gave up")


class LLM:
    """Gemini first; Groq when Gemini is paused, over its limit or failing. Same .json() interface as Gemini."""
    def __init__(self, gem, groq=None):
        self.gem, self.groq = gem, groq
        self.used_groq = 0

    @property
    def gave_up_429(self):
        return self.gem.gave_up_429 and (self.groq is None or self.groq.gave_up_429)

    @property
    def tokens_in(self):
        return self.gem.tokens_in + (self.groq.tokens_in if self.groq else 0)

    @property
    def tokens_out(self):
        return self.gem.tokens_out + (self.groq.tokens_out if self.groq else 0)

    def json(self, system, user, max_tokens=4096, **kw):
        err = None
        if not self.gem.gave_up_429:
            try:
                return self.gem.json(system, user, max_tokens)
            except Exception as e:
                err = e
                if self.groq is None:
                    raise
                log(f"gemini failed ({str(e)[:80]}); using groq")
        if self.groq is None:
            raise err or RuntimeError("gemini 429 (limit): paused, not calling again this run")
        out = self.groq.json(system, user, max_tokens)
        self.used_groq += 1
        return out


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
        if "SCORE_FIT" in system and re.search(r'\(key "[a-z0-9_]+"', system):
            n = user.count('"title"')
            keys = re.findall(r'\(key "([a-z0-9_]+)"', system)
            return {"scores": [{"index": i, "params": {k: {"score": (None if k == "must_haves" else max(5, 88 - 14 * i - 3 * j)), "why": "fixture"} for j, k in enumerate(keys)},
                                "basis": "title_only", "note": "dry run score"} for i in range(n)]}
        if "SCORE_FIT" in system:
            n = user.count('"title"')
            return {"scores": [{"index": i, "fit_score": 72 - 9 * i, "fit_breakdown": {"basis": "fixture", "role_level": "PM", "domain": "SaaS",
                     "location": "Chennai", "must_haves": "unknown until the JD is read", "note": "dry run score"}} for i in range(n)]}
        if "DECIDE_RESUME" in system:
            keys = re.findall(r'\(key "([a-z0-9_]+)"', system)
            return {"params": {k: {"score": 40 + 5 * j, "why": "fixture"} for j, k in enumerate(keys)}, "direct": "generic"}
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


# ---------------------------------------------------------------- JD Fetcher (v1.0.8)
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
JD_WORDS = re.compile(r"responsib|requirement|qualification|experience|what you|about the role|you will|skills", re.I)


def http_text(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml",
                                               "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
            return r.status, body, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:
        return 0, str(e)[:200], url


def jsonld_jobposting(body):
    """Most ATS pages (Greenhouse, Lever, Workday, Ashby, SmartRecruiters) embed a schema.org JobPosting."""
    for blob in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', body, re.S | re.I):
        try:
            data = json.loads(blob.strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if (t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t)) and d.get("description"):
                    return d
                stack.extend(v for v in d.values() if isinstance(v, (list, dict)))
    return None


def generic_jd(url):
    st, body, final = http_text(url)
    if st != 200 or not body:
        return {"error": f"page HTTP {st}"}
    jp = jsonld_jobposting(body)
    if jp:
        txt = html_to_text(jp["description"]) if "<" in jp["description"] else html.unescape(jp["description"])
        head = [f"Source: {final}"]
        if jp.get("title"):
            head.append(f"Title: {jp['title']}")
        if jp.get("employmentType"):
            head.append(f"Employment type: {jp['employmentType']}")
        if len(txt) >= 300:
            return {"text": "\n".join(head) + "\n\n" + txt, "source_url": final, "confidence": "full" if len(txt) >= 800 else "partial"}
    body = re.sub(r"<(nav|header|footer|aside|form)\b.*?</\1>", " ", body, flags=re.S | re.I)
    txt = html_to_text(body)
    if len(txt) >= 800 and len(JD_WORDS.findall(txt)) >= 2:
        return {"text": f"Source: {final}\n(page text, not a structured job description)\n\n" + txt[:15000], "source_url": final, "confidence": "partial"}
    return {"error": "no job description found on page"}


def li_job_id(url):
    m = re.search(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*?-)?(\d{6,})", url or "") or re.search(r"currentJobId=(\d{6,})", url or "")
    return m.group(1) if m else None


def linkedin_jd(jid, state):
    if state.get("li_blocked", 0) >= 2:
        return {"error": "linkedin blocked this run"}
    st, body, _ = http_text(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")
    time.sleep(JD_PAUSE_S)
    if st in (429, 999, 403):
        state["li_blocked"] = state.get("li_blocked", 0) + 1
        return {"error": f"linkedin HTTP {st} (blocked/rate limited)"}
    if st != 200 or not body:
        return {"error": f"linkedin HTTP {st}"}
    m = re.search(r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>\s*(?:<button|</section>)', body, re.S) \
        or re.search(r'class="description__text[^"]*"[^>]*>(.*?)</section>', body, re.S)
    desc = html_to_text(m.group(1)) if m else ""
    head = [f"Source: LinkedIn job {jid}"]
    for k, v in re.findall(r'description__job-criteria-subheader[^>]*>\s*(.*?)\s*</h3>\s*<span[^>]*>\s*(.*?)\s*</span>', body, re.S):
        head.append(f"{html.unescape(k).strip()}: {html.unescape(v).strip()}")
    if re.search(r"No longer accepting applications", body, re.I):
        head.append("Posting status: no longer accepting applications")
    offsite = None
    a = re.search(r'<code id="applyUrl"[^>]*><!--"(.*?)"--></code>', body, re.S)
    if a:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(a.group(1))).query)
        offsite = (q.get("url") or [None])[0]
    if offsite:
        head.append(f"Company apply link: {offsite}")
    return {"desc": desc, "head": head, "offsite": offsite}


def fetch_jd(url, state):
    """Returns {"text","source_url","confidence"} or {"error"}. LinkedIn public page first, then the company page."""
    if not url:
        return {"error": "no url"}
    jid = li_job_id(url)
    if not jid:
        return generic_jd(url)
    li = linkedin_jd(jid, state)
    if li.get("error"):
        return li
    li_url = f"https://www.linkedin.com/jobs/view/{jid}/"
    if len(li["desc"]) >= 600:
        return {"text": "\n".join(li["head"]) + "\n\n" + li["desc"], "source_url": li_url, "confidence": "full"}
    if li.get("offsite"):
        g = generic_jd(li["offsite"])
        if not g.get("error") and len(g["text"]) > len(li["desc"]):
            g["text"] = "\n".join(li["head"]) + "\n\n" + g["text"]
            return g
    if li["desc"]:
        return {"text": "\n".join(li["head"]) + "\n\n" + li["desc"], "source_url": li_url, "confidence": "partial"}
    return {"error": "linkedin page had no description"}


class JDBudget:
    def __init__(self, dry=False, limit=JD_MAX_PER_RUN):
        self.start, self.n, self.dry, self.state = time.time(), 0, dry, {}
        self.limit = limit
        self.ok = self.failed = 0

    def left(self):
        return self.n < self.limit and time.time() - self.start < JD_BUDGET_S

    def fetch(self, url, title=""):
        self.n += 1
        if self.dry:
            r = {"text": f"Source: dry run\n\nAbout the role: {title}. Responsibilities: own the roadmap. Requirements: 6+ years PM experience.",
                 "source_url": url, "confidence": "full"}
        else:
            try:
                r = fetch_jd(url, self.state)
            except Exception as e:
                r = {"error": f"fetch crashed: {str(e)[:150]}"}
        if r.get("error"):
            self.failed += 1
        else:
            self.ok += 1
            r["text"] = r["text"][:JD_STORE_MAX]
        return r


def jd_payload(l):
    jd = (l.get("jd_text") or "").strip()
    job = {"title": l["title"], "company": l["company"], "location": l.get("location"), "snippet": l.get("raw_snippet")}
    if jd:
        job["jd"] = jd[:JD_FOR_FIT]
    return job


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
PROVIDERS = {}   # set in main(): {"gemini": Gemini, "groq": Groq|None, "jev": Jev|None}; Run uses call-count deltas
ERROR_KINDS = [  # same order and patterns as public.job_driver_error_kind() in Supabase and errKind() in the app
    ("setup", r"\b40[123]\b|free tier users|insufficient|no AI_GATEWAY|missing secret|api key|unauthori|forbidden|credits"),
    ("ai_limit", r"\b429\b|rate limit|quota|limit hit|max AI calls|no AI model available"),
    ("ai_busy", r"\b503\b|high demand|overloaded|unavailable"),
    ("format", r"format|json|parse|did not match"),
    ("gmail", r"imap|\bUID\b|gmail|socket error: EOF"),
    ("network", r"network|urlopen|timed? ?out|connection|socket|unreachable|reset by peer"),
    ("jd_fetch", r"linkedin HTTP|page HTTP|job description"),
]
DID_WORK_RE = re.compile(r"(filled|scored|decided|fetched|created|sent|pushed|parked|moved|marked)\D{0,3}[1-9]|\b[1-9][0-9]* (lead|application|mail|job)", re.I)
CRASH_AFTER_MIN = 40


def error_kind(text):
    for k, rx in ERROR_KINDS:
        if re.search(rx, text or "", re.I):
            return k
    return "other"


def error_kinds(errors):
    return sorted({error_kind(str(e.get("error") if isinstance(e, dict) and e.get("error") else e)) for e in (errors or [])}) or None


def provider_calls():
    out = {}
    for k, prov in PROVIDERS.items():
        out[k] = int(getattr(prov, "calls", 0) or 0) if prov else 0
    return out


def github_run_url():
    rid = os.environ.get("GITHUB_RUN_ID")
    if not rid:
        return None
    return f'{os.environ.get("GITHUB_SERVER_URL", "https://github.com")}/{os.environ.get("GITHUB_REPOSITORY", "sudharsan454/job-tracker")}/actions/runs/{rid}'


class Run:
    """One agent_runs row. Written at the start (status running) so a crash leaves a trace; filled in by finish()."""
    def __init__(self, sb, agent, model):
        self.sb, self.agent, self.model = sb, agent, model
        self.started = now_utc()
        self.read = self.created = self.parked = 0
        self.done = 0            # optional: units of real work done (lets a run with errors count as partial)
        self.skipped = False     # set when the agent was deliberately not run (off / not due)
        self.errors, self.notes = [], []
        self.id = None
        self._calls0 = provider_calls()
        try:
            r = sb.insert("agent_runs", {"agent": agent, "started_at": iso(self.started), "status": "running", "model": model,
                                         "github_run_url": github_run_url()})
            self.id = r[0]["id"] if r else None
        except Exception as e:
            log(f"[{agent}] start row not written ({str(e)[:120]}); it will be written at the end")

    def status(self, summary):
        if not self.errors:
            return "skipped" if self.skipped and not (self.read or self.created or self.parked) else "success"
        if self.done or self.created or self.parked or DID_WORK_RE.search(summary or ""):
            return "partial"
        return "failed"

    def finish(self, llm=None, summary=None):
        summ = summary or "; ".join(self.notes)[:2000]
        c1 = provider_calls()
        delta = {k: c1.get(k, 0) - self._calls0.get(k, 0) for k in c1}
        row = {"agent": self.agent, "started_at": iso(self.started), "finished_at": iso(now_utc()), "items_read": self.read,
               "items_created": self.created, "items_parked": self.parked, "errors": self.errors or None,
               "summary": summ, "model": self.model, "status": self.status(summ), "error_kinds": error_kinds(self.errors),
               "ai_calls": sum(delta.values()), "backup_used": delta.get("groq", 0) > 0, "github_run_url": github_run_url()}
        if llm:
            row["tokens_in"], row["tokens_out"] = llm.tokens_in, llm.tokens_out
        r = None
        if self.id and not str(self.id).startswith("dry-"):
            try:
                r = self.sb.update("agent_runs", {"id": self.id}, row)
            except Exception as e:
                log(f"[{self.agent}] could not finish row {self.id} ({str(e)[:120]}); inserting a new one")
        elif self.id and self.sb.dry:
            r = self.sb.update("agent_runs", {"id": self.id}, row) or [{"id": self.id}]
        if not r:
            r = self.sb.insert("agent_runs", row)
            self.id = r[0]["id"] if r else self.id
        log(f"[{self.agent}] {row['status']} read={self.read} created={self.created} parked={self.parked} errors={len(self.errors)} ai_calls={row['ai_calls']} :: {summ[:160]}")
        return self.id


def mark_crashed(sb):
    """Rows still 'running' long after they started belong to a run that died (timeout, kill, crash)."""
    if sb.dry:
        return 0
    cutoff = iso(now_utc() - timedelta(minutes=CRASH_AFTER_MIN))
    qs = urllib.parse.urlencode({"owner_id": "eq." + OWNER_ID, "status": "eq.running", "started_at": "lt." + cutoff})
    st, d = http("PATCH", sb.url + "agent_runs?" + qs,
                 {"status": "crashed", "error_kinds": ["other"],
                  "errors": [{"stage": "runner", "error": f"run never finished (still running after {CRASH_AFTER_MIN} min): killed, timed out or crashed"}]},
                 headers=dict(sb.h, Prefer="return=representation"))
    n = len(d) if st < 300 and isinstance(d, list) else 0
    if n:
        log(f"marked {n} unfinished run(s) as crashed")
    return n


def health_alerts(sb, tg, settings, agents):
    """Telegram, at most once a day per agent and reason, never in quiet hours (the next run after quiet hours sends it)."""
    chat = settings.get("telegram_chat_id")
    if not chat:
        return []
    since = iso(now_utc() - timedelta(days=3))
    rows = sb.select("agent_runs", {"owner_id": "eq." + OWNER_ID, "started_at": "gte." + since,
                                    "select": "agent,status,error_kinds,errors,started_at", "order": "started_at.desc", "limit": "400"})
    by = {}
    for r in rows:
        if r.get("status") in ("running", None):
            continue
        by.setdefault(r["agent"], []).append(r)
    alerts = []
    # missed slots, from the Agents screen schedule (the runner itself running proves every-pass agents are not missed)
    run_name = {"status_sync": "status_sync", "sweeps": "sweeps", "resume_decider": "resume_decider", "jd_fetcher": "sourcer+fit",
                "sourcer": "sourcer+fit", "fit": "sourcer+fit", "notifier": "notifier"}
    for key, cfg in (agents or {}).items():
        if not cfg.get("enabled") or cfg.get("built_status") == "not_built":
            continue
        sch = cfg.get("schedule") or {}
        mode = sch.get("mode", "every_run")
        limit_h = 30 if mode == "nightly" else (1.5 * float(sch.get("hours") or 4) + 2 if mode == "every_n_hours" else None)
        if not limit_h:
            continue
        last = cfg.get("last_run_at")
        name = run_name.get(key, key)
        if not last:
            continue
        try:
            age_h = (now_utc() - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() / 3600
        except Exception:
            continue
        if age_h > limit_h:
            alerts.append((name, "missed", f"⏰ <b>{html.escape(cfg.get('name') or key)}</b> missed its slot: last ran {age_h:.0f} h ago (expected within {limit_h:.0f} h)."))
    if in_quiet_hours(settings):
        log("agent alerts held for quiet hours")
        return []
    out = failure_alerts(sb, tg, settings, chat)
    if not alerts:
        return out
    sent_map = dict(settings.get("agent_alerts") or {})
    day = today_ist().isoformat()
    for ag, why, text in alerts:
        k = f"{ag}|{why}"
        if sent_map.get(k) == day:
            continue
        tg.send(chat, text + f"\n{APP_URL}#runs")
        sent_map[k] = day
        out.append(k)
    if out and not sb.dry:
        settings.set(agent_alerts=sent_map)
    return out


def failure_alerts(sb, tg, settings, chat):
    """v1.0.16: one Telegram message per failure streak per agent, a 'working again' line when it recovers.
    State in settings.agent_fail_state = {agent: {"open": bool, "seen": <started_at of the last run looked at>}}.
    Called only outside quiet hours, so failures in quiet hours are reported in the morning (state is not advanced at night)."""
    state = dict(settings.get("agent_fail_state") or {})
    first = not state
    since = iso(now_utc() - timedelta(hours=6 if first else 72))
    rows = sb.select("agent_runs", {"owner_id": "eq." + OWNER_ID, "started_at": "gte." + since,
                                    "select": "agent,status,error_kinds,errors,started_at", "order": "started_at.asc", "limit": "1000"})
    msgs, changed = [], False
    by = {}
    for r in rows:
        if r.get("status") in ("running", "skipped", None):
            continue
        by.setdefault(r["agent"], []).append(r)
    for ag, rs in by.items():
        st = dict(state.get(ag) or {"open": False, "seen": ""})
        new = [r for r in rs if (r.get("started_at") or "") > st["seen"]]
        if not new:
            continue
        fails, last_fail, recovered = 0, None, False
        was_open = st["open"]
        for r in new:
            if r.get("status") in ("failed", "crashed"):
                if not st["open"]:
                    fails += 1
                st["open"] = True
                last_fail = r
            else:
                if st["open"]:
                    recovered = True
                st["open"] = False
            st["seen"] = r["started_at"]
        if last_fail is not None and (fails or not was_open):
            e = (last_fail.get("errors") or [{}])[0]
            txt = str(e.get("error") if isinstance(e, dict) else e)[:180]
            kinds = last_fail.get("error_kinds") or ["other"]
            when = datetime.fromisoformat(last_fail["started_at"].replace("Z", "+00:00")).astimezone(IST).strftime("%d %b %H:%M")
            need = "\nNeeds you: a key, credits or access. Waiting will not fix it." if "setup" in kinds else ""
            tail = " It has recovered since." if not st["open"] else ""
            msgs.append(f"⚠️ <b>{html.escape(ag)}</b> {last_fail.get('status')} at {when} IST ({html.escape(', '.join(kinds))}).{tail}\n{html.escape(txt)}{need}")
        elif recovered and was_open:
            msgs.append(f"✅ <b>{html.escape(ag)}</b> is working again.")
        state[ag] = st
        changed = True
    if msgs and chat:
        tg.send(chat, "\n\n".join(msgs) + f"\n{APP_URL}#runs")
    if changed and not sb.dry:
        settings.set(agent_fail_state=state)
    return msgs


# ---------------------------------------------------------------- Prompts
EXTRACT_SYS = """EXTRACT_JOBS. You read one job-alert email and return JSON only.
Return {"is_job_alert": bool, "jobs": [{"title","company","location","url","easy_apply"(bool|null),"posted_text"(as written, e.g. "2 days ago", or null),"snippet"(<=200 chars),"stream"(one of the stream names given, or null)}]}.
Rules: one entry per distinct job in the mail; use the job's own link (not unsubscribe/profile links); if the mail is a newsletter, profile nag, course ad or recruiter marketing with no concrete openings, return is_job_alert=false and jobs=[].
Assign "stream" by matching the job against each stream's target titles and goal; null if neither fits."""

FIT_SYS = """SCORE_FIT. You are a strict recruiter screening jobs for one candidate. JSON only.
Input: the candidate's resume, the job stream goal, and a list of jobs (index, title, company, location, snippet, and "jd" = the full job description when we have it). When "jd" is present, score against its real must-haves (years, domain, skills, level) and start "basis" with "full JD"; when it is missing, start "basis" with "title only".
Return {"scores":[{"index":int,"fit_score":0-100,"fit_breakdown":{"basis":str,"role_level":str,"domain":str,"location":str,"must_haves":str,"note":str}}]}.
Scoring: 80+ only when title, seniority and domain all match the stream; 60-79 plausible, worth a look; 40-59 stretch or domain shift; <40 wrong level, wrong function or clearly junior/senior-mismatch. Location outside the stream's cities and not remote: cap at 50. Keep every string under 120 chars."""

STATUS_SYS = """CLASSIFY_STATUS. You read one email about a job application and return JSON only.
Return {"outcome": one of ["rejected","interview_invite","offer","assessment","acknowledgement","other"], "company": str, "verbatim": the exact sentences that state the decision (copy, do not paraphrase; empty if none), "confidence": 0-1}.
"rejected" only when the mail clearly says the candidate is not moving forward for this application."""


# ---------------------------------------------------------------- Agents config (v1.0.9; merged with the JD Fetcher): read from public.agents on every pass
# The web app's Agents screen writes these rows. render_rubric / render_system / compute_fit MUST stay identical
# to agRubricText / agRenderSystem / agComputeFit in jobs/index.html (app v1.0.5+), so the preview there is what is sent here.
DEFAULT_PHASE = {"sourcer": "cycle", "fit": "cycle", "jd_fetcher": "cycle", "notifier": "cycle", "status_sync": "nightly", "sweeps": "nightly"}
MARK = {"fit": "SCORE_FIT.", "sourcer": "EXTRACT_JOBS.", "status_sync": "CLASSIFY_STATUS."}
OUT_FORMAT = {
    "fit": 'Output format (fixed by the system): JSON only, no prose.\n{"scores":[{"index":<int>,"params":{"<parameter key>":{"score":<0-100 or null>,"why":"<under 120 chars>"}},"basis":"title_only | snippet | jd","note":"<under 120 chars>"}]}\nOne entry per job. Include every parameter key listed above.',
    "sourcer": 'Output format (fixed by the system): JSON only.\n{"is_job_alert": true|false, "jobs": [{"title","company","location","url","easy_apply": true|false|null,"posted_text": "as written, e.g. 2 days ago, or null","snippet": "<=200 chars","stream": "one of the stream names, or null"}]}',
    "status_sync": 'Output format (fixed by the system): JSON only.\n{"outcome": "rejected|interview_invite|offer|assessment|acknowledgement|other", "company": "<name>", "verbatim": "<exact sentences, or empty>", "confidence": <0-1>}',
}
DEFAULT_TEMPLATE = {  # used only when the agents table cannot be read (same text as prompt v1 in the database)
    "sourcer": ("You read one job-alert email and pull out every concrete job opening in it.\n"
                "Rules: one entry per distinct job in the mail; use the job's own link (not unsubscribe or profile links); if the mail is a newsletter, profile nag, course ad or recruiter marketing with no concrete openings, set is_job_alert to false and return no jobs.\n"
                "Assign \"stream\" by matching the job against each stream's target titles and goal; null if neither fits.\nStreams:\n{{streams}}"),
    "status_sync": ("You read one email about a job application and decide what it says about that application.\n"
                    "\"rejected\" only when the mail clearly says the candidate is not moving forward for this application.\n"
                    "For \"verbatim\", copy the exact sentences that state the decision; do not paraphrase. Leave it empty if there are none."),
}
BANDS = {"strong": (80, 100, True), "plausible": (60, 79, True), "stretch": (40, 59, False), "no": (0, 39, False)}


def render_rubric(rub):
    lines = []
    for p in (rub or {}).get("params") or []:
        if p.get("enabled") is False:
            continue
        a = p.get("anchors") or {}
        lines.append(f'- {p.get("name")} (key "{p.get("key")}", weight {p.get("weight")}): {p.get("description") or ""}')
        lines.append(f'    about 90: {a.get("high") or ""}')
        lines.append(f'    about 50: {a.get("mid") or ""}')
        lines.append(f'    about 10: {a.get("low") or ""}')
        cap = p.get("cap")
        if cap and cap.get("below") is not None and cap.get("max") is not None:
            lines.append(f'    Hard cap: if this is below {fmt_num(cap["below"])}, the total cannot be above {fmt_num(cap["max"])} (applied by the system).')
        lines.append("    If you cannot judge it: return null." + (" It is then left out of the total." if p.get("if_unknown") == "skip" else " It is then scored 50."))
    return "\n".join(lines)


def fmt_num(v):
    """Print numbers the way JavaScript's String() does (30 not 30.0), so the prompt matches the app preview."""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(f)
    except Exception:
        return str(v)


def streams_desc(streams):
    return "\n".join(f'- "{s["name"]}": goal={s.get("goal") or ""}; target titles={", ".join(s.get("target_titles") or [])}' for s in streams)


def render_system(key, template, rubric=None, streams=None):
    body = template or ""
    if key == "fit":
        body = body.replace("{{rubric}}", render_rubric(rubric)).replace("{{threshold}}", fmt_num((rubric or {}).get("threshold", 60)))
    if key == "sourcer":
        body = body.replace("{{streams}}", streams_desc(streams or []))
    return (MARK[key] + "\n" if key in MARK else "") + body + ("\n\n" + OUT_FORMAT[key] if key in OUT_FORMAT else "")


def _score(v):
    if isinstance(v, dict):
        v = v.get("score")
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return max(0.0, min(100.0, float(v)))
    except Exception:
        return None


def compute_fit(rub, params):
    """Weighted mean of the parameter scores; null -> 50 (neutral) or left out (skip); then hard caps. Round half up like JS Math.round."""
    tot = w = 0.0
    caps = []
    ps = [p for p in (rub or {}).get("params") or [] if p.get("enabled") is not False]
    for p in ps:
        s = _score((params or {}).get(p["key"]))
        if s is None:
            if p.get("if_unknown") == "skip":
                continue
            s = 50.0
        tot += float(p.get("weight") or 0) * s
        w += float(p.get("weight") or 0)
    total = int(math.floor(tot / w + 0.5)) if w else None
    for p in ps:
        cap = p.get("cap")
        if not cap or cap.get("below") is None or cap.get("max") is None:
            continue
        s = _score((params or {}).get(p["key"]))
        if s is not None and s < float(cap["below"]) and total is not None and total > float(cap["max"]):
            total = int(float(cap["max"]))
            caps.append(p["key"])
    return total, caps


def guard(cfg, key):
    for g in (cfg or {}).get("guardrails") or []:
        if g.get("key") == key:
            return g
    return None


def guard_on(cfg, key, default=True):
    g = guard(cfg, key)
    if g is None:
        return default
    return bool(g.get("locked") or g.get("on", True))


def guard_value(cfg, key, default=None):
    g = guard(cfg, key)
    if g is None:
        return default
    if not (g.get("locked") or g.get("on", True)):
        return None  # switched off in the app: no limit
    return g.get("value", default)


def load_agents(sb):
    """{key: agents row + 'prompt' (active version row)}; {} when the table is missing or unreadable (then v1.0.7 behaviour)."""
    try:
        rows = sb.select("agents", {"owner_id": "eq." + OWNER_ID, "select": "*"})
    except Exception as e:
        log(f"agents config not readable ({str(e)[:120]}); using built-in settings")
        return {}
    ids = [r["active_prompt_version_id"] for r in rows if r.get("active_prompt_version_id")]
    pvs = {}
    if ids:
        try:
            pvs = {p["id"]: p for p in sb.select("agent_prompt_versions", {"id": "in.(" + ",".join(ids) + ")", "select": "id,version,system_template"})}
        except Exception as e:
            log(f"prompt versions not readable ({str(e)[:120]}); using built-in prompts")
    out = {}
    for r in rows:
        r["prompt"] = pvs.get(r.get("active_prompt_version_id"))
        out[r["key"]] = r
    if out:
        log("agents config: " + ", ".join(f'{k}={"on" if r.get("enabled") else "off"}/{(r.get("schedule") or {}).get("mode", "every_run")}'
                                          f'{"/p" + str(r["prompt"]["version"]) if r.get("prompt") else ""}' for k, r in sorted(out.items())))
    return out


def load_rubrics(sb, streams, ids=None):
    """{stream_id: {"id", "version", "rubric"}} for the active (or the given) fitment versions."""
    want = ids or [s.get("fit_rubric_version_id") for s in streams if s.get("fit_rubric_version_id")]
    want = [i for i in want if i]
    if not want:
        return {}
    try:
        rows = sb.select("fit_rubric_versions", {"id": "in.(" + ",".join(want) + ")", "select": "id,version,job_stream_id,rubric"})
    except Exception as e:
        log(f"fitment rubrics not readable ({str(e)[:120]}); using the legacy fit prompt")
        return {}
    return {r["job_stream_id"]: r for r in rows if r.get("id") in want}


def template_for(agents, key):
    p = (agents.get(key) or {}).get("prompt")
    return p["system_template"] if p and p.get("system_template") else DEFAULT_TEMPLATE.get(key, "")


def due(agents, key, phase):
    """Should this agent run in this phase ('cycle' = every runner pass, 'nightly')? No row = built-in default."""
    cfg = agents.get(key)
    if not cfg:
        return phase == DEFAULT_PHASE.get(key, "cycle"), "built-in default"
    if cfg.get("built_status") == "not_built":
        return False, "not built"
    if not cfg.get("enabled"):
        return False, "off"
    sch = cfg.get("schedule") or {}
    mode = sch.get("mode", "every_run")
    if phase == "nightly":
        return mode == "nightly", ("nightly" if mode == "nightly" else "not a nightly agent")
    if mode == "every_run":
        return True, "every pass"
    if mode == "every_n_hours":
        hrs = float(sch.get("hours") or 4)
        last = cfg.get("last_run_at")
        if not last:
            return True, f"every {hrs:g} h (first run)"
        try:
            age_h = (now_utc() - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() / 3600
        except Exception:
            return True, f"every {hrs:g} h"
        # the runner wakes about every 2 h, so allow 30 min of drift
        return (age_h >= hrs - 0.5), f"every {hrs:g} h (last {age_h:.1f} h ago)"
    return False, "nightly only"


def mark(sb, agents, key, ran, status):
    cfg = agents.get(key)
    if not cfg or sb.dry:
        return
    patch = {"last_run_status": f"{status} · {datetime.now(IST).strftime('%d %b %H:%M')} IST"}
    if ran:
        patch["last_run_at"] = iso(now_utc())
    try:
        sb.update("agents", {"id": cfg["id"]}, patch)
    except Exception as e:
        log(f"could not update agents.{key}: {str(e)[:120]}")


class AgentLLM:
    """One agent's view of the shared Gemini/Groq clients: model order from its row, its max-calls guardrail, its own token count.
    The daily quota and the 429 pauses stay shared, because they belong to the account, not the agent."""
    def __init__(self, base, cfg=None, max_calls_default=None):
        self.base = base
        m = (cfg or {}).get("model") or {}
        self.order, self.skipped = [], []
        for p in (m.get("primary") or "gemini", m.get("fallback") or "groq"):
            if p in (None, "none") or p in self.order:
                continue
            if p == "ollama":
                self.skipped.append("ollama (not reachable from GitHub)")
                continue
            if p in ("gemini", "groq"):
                self.order.append(p)
        if not self.order:
            self.order = ["gemini", "groq"]
        mc = guard_value(cfg, "max_calls", max_calls_default) if cfg else max_calls_default
        self.max_calls = int(mc) if mc is not None else None
        self.max_tokens = int(m.get("max_tokens") or 4096)
        self.timeout = int(m.get("timeout_s") or 75)
        self.overrides = {"gemini": m.get("gemini_model") or None, "groq": m.get("groq_model") or None}
        self.calls = 0
        self.tokens_in = self.tokens_out = 0
        self.used = []

    def _prov(self, p):
        return self.base.gem if p == "gemini" else self.base.groq

    @property
    def capped(self):
        return self.max_calls is not None and self.calls >= self.max_calls

    @property
    def gave_up_429(self):
        return self.capped or all(self._prov(p) is None or self._prov(p).gave_up_429 for p in self.order)

    @property
    def label(self):
        return ",".join(dict.fromkeys(self.used)) or "-"

    def json(self, system, user, max_tokens=None):
        if self.capped:
            raise RuntimeError(f"max AI calls per run reached ({self.max_calls})")
        err = None
        for p in self.order:
            prov = self._prov(p)
            if prov is None or prov.gave_up_429:
                continue
            ti, to = prov.tokens_in, prov.tokens_out
            self.calls += 1
            try:
                out = prov.json(system, user, max_tokens or self.max_tokens, model=self.overrides.get(p), timeout=self.timeout)
            except Exception as e:
                err = e
                log(f"{p} failed ({str(e)[:80]}); trying the next model")
                continue
            finally:
                self.tokens_in += prov.tokens_in - ti
                self.tokens_out += prov.tokens_out - to
            if p == "groq":
                self.base.used_groq += 1
            self.used.append(p)
            return out
        raise err or RuntimeError("no AI model available this run (limits hit or none set)")


class TokenSum:
    def __init__(self, *llms):
        self.tokens_in = sum(l.tokens_in for l in llms)
        self.tokens_out = sum(l.tokens_out for l in llms)


def llm_json_checked(llm, system, user, ok, norm=None):
    """Guardrail 'Fixed output format': normalise known near-misses, then one retry when the reply still has the wrong shape."""
    out = llm.json(system, user)
    out = norm(out) if norm else out
    if ok(out):
        return out
    log(f"reply did not match the output format; retrying once: {str(out)[:200]}")
    out = llm.json(system, user)
    out = norm(out) if norm else out
    if ok(out):
        return out
    raise RuntimeError("reply did not match the output format twice; last reply: " + str(out)[:200])


def fit_norm(o):
    if isinstance(o, list):
        return {"scores": o}
    if isinstance(o, dict) and not isinstance(o.get("scores"), list):
        for k in ("results", "jobs", "items", "data"):
            if isinstance(o.get(k), list):
                return {"scores": o[k]}
        if "index" in o and ("params" in o or "fit_score" in o):
            return {"scores": [o]}
        if isinstance(o.get("scores"), dict):
            return {"scores": [o["scores"]]}
    return o


def fit_ok(out):
    return isinstance(out, dict) and isinstance(out.get("scores"), list)


def fit_results(out, rubric, n, meta):
    """{index: (fit_score, fit_breakdown)}. With a rubric the model only scores parameters; the total and caps are computed here."""
    res = {}
    for sc in (out or {}).get("scores") or []:
        try:
            i = int(sc.get("index"))
        except Exception:
            continue
        if not 0 <= i < n:
            continue
        if rubric:
            raw = sc.get("params") or {}
            clean = {}
            for p in rubric.get("params") or []:
                if p.get("enabled") is False:
                    continue
                v = raw.get(p["key"])
                why = v.get("why") if isinstance(v, dict) else ""
                s = _score(v)
                clean[p["key"]] = {"score": (int(round(s)) if s is not None else None), "why": str(why or "")[:160]}
            total, caps = compute_fit(rubric, clean)
            res[i] = (total, {"basis": str(sc.get("basis") or "")[:40], "note": str(sc.get("note") or "")[:200], "params": clean, "caps_applied": caps, **meta})
        else:
            res[i] = (sc.get("fit_score"), sc.get("fit_breakdown"))
    return res


def fit_payload(stream, resume, items):
    return {"stream_goal": stream.get("goal"), "stream_locations": stream.get("locations"), "resume": (resume or "")[:9000],
            "jobs": [{"index": k, "title": x.get("title"), "company": x.get("company"), "location": x.get("location"), "snippet": x.get("snippet") or x.get("raw_snippet"),
                      "jd": ((x.get("jd_text") or "")[:JD_FOR_FIT] or None)} for k, x in enumerate(items)]}


def fit_system(agents, rubric):
    """System prompt for one stream: rubric prompt when the stream has an active rubric, else the v1.0.7 prompt."""
    if rubric:
        return render_system("fit", template_for(agents, "fit") or "{{rubric}}", rubric=rubric)
    return FIT_SYS


def stream_threshold(rubrics, settings, sid):
    r = rubrics.get(sid)
    if r and (r.get("rubric") or {}).get("threshold") is not None:
        return float(r["rubric"]["threshold"])
    return float(settings.get("fit_threshold", 60))


def resume_for(stream, docs):
    return (docs.get(stream.get("generic_document_id")) or {}).get("text") or next((d["text"] for d in docs.values() if d["job_stream_id"] == stream["id"]), "")


def score_items(llm, agents, stream, resume, items, rubric, run, stage):
    """Score a list of dicts (leads or eval inputs) for one stream in batches. Returns {position: (score, breakdown)}."""
    cfg = agents.get("fit")
    batch_n = max(1, int((cfg or {}).get("max_items") or FIT_BATCH))
    meta = {"prompt_version": ((cfg or {}).get("prompt") or {}).get("version"), "rubric_version": (rubric or {}).get("version")}
    rub = (rubric or {}).get("rubric")
    system = fit_system(agents, rub)
    out_all = {}
    for i in range(0, len(items), batch_n):
        batch = items[i:i + batch_n]
        if llm.gave_up_429:
            run.notes.append(f"{stage} {stream['name']}: {'max AI calls reached' if getattr(llm, 'capped', False) else 'AI limit hit'}, {len(items) - i} left for later")
            break
        try:
            out = llm_json_checked(llm, system, json.dumps(fit_payload(stream, resume, batch)), fit_ok, fit_norm)
        except Exception as e:
            run.errors.append({"stage": stage, "stream": stream["name"], "error": str(e)[:300]})
            continue
        res = fit_results(out, rub, len(batch), {**meta, "model": llm.label if hasattr(llm, "label") else None})
        if rub:
            for k in list(res):
                score, fb = res[k]
                if isinstance(fb, dict) and isinstance(fb.get("params"), dict):
                    score, caps = apply_rule_params(rub, batch[k], fb["params"])
                    fb["caps_applied"] = caps
                    res[k] = (score, fb)
        for k, (score, fb) in res.items():
            if rub and guard_on(cfg, "require_basis", True) and not (fb or {}).get("basis"):
                run.errors.append({"stage": stage, "guardrail": "require_basis", "title": batch[k].get("title"), "error": "score came back without a basis"})
                fb["basis"] = "not given"
            out_all[i + k] = (score, fb)
    return out_all


# runner_gates_module_v1.0.py · v1.0 · 27 Oct 2026 · inserted into runner v1.0.17
# Mandatory gates (pass / fail / not_stated) checked before weighted fit; rule-based experience grade; career notes from the portfolio.

GATE_FAIL_P = 0.2          # an AI-checked gate fails only when P(yes) < 0.2, i.e. at least 80% sure it is a mismatch
FOREIGN_WORDS = ("united states", "usa", " us", "u.s.", "united kingdom", " uk", "europe", "emea", "canada", "australia", "singapore",
                 "germany", "dubai", "uae", "london", "new york", "san francisco", "berlin", "amsterdam", "philippines", "apac", "americas")
ROLE_PASS_RE = re.compile(r"product\s+(manager|management|owner|lead|leader|head)|\b(a?pm|gpm|spm)\b|head\s+of\s+product|director\s+of\s+product|"
                          r"\bvp,?\s+(of\s+)?product|chief\s+product|group\s+product|principal\s+product|product\s+director", re.I)
ROLE_FAIL_RE = re.compile(r"product\s+marketing|engineer|developer|architect|scientist|designer|analyst|project\s+manager|program(me)?\s+manager|scrum|"
                          r"delivery\s+manager|sales|account\s+(executive|manager)|marketing|customer\s+success|support|recruit|tester|\bqa\b|devops|consultant", re.I)
YEARS_RANGE_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)
YEARS_MIN_RE = re.compile(r"(\d{1,2})\s*(\+|plus)?\s*(?:years?|yrs?)", re.I)


def years_asked(text):
    """(lo, hi) years of experience the job asks for, hi None for 'X+'; None when not stated. Only counts numbers near the word 'experience'."""
    t = text or ""
    for rx, ranged in ((YEARS_RANGE_RE, True), (YEARS_MIN_RE, False)):
        for m in rx.finditer(t):
            win = t[max(0, m.start() - 60):m.end() + 80].lower()
            if "experience" not in win and "exp " not in win and "exp." not in win:
                continue
            lo = int(m.group(1))
            if lo > 30:
                continue
            if ranged:
                hi = int(m.group(2))
                if hi < lo or hi > 40:
                    continue
                return lo, hi
            return lo, None
    return None


def _overlap(lo, hi, a, b):
    return lo <= b and (hi is None or hi >= a)


def gate_location(g, lead):
    loc = (lead.get("location") or "").lower()
    cities = [c.lower() for c in ((g.get("rule") or {}).get("allow_cities") or ["chennai"])]
    if not loc.strip() or loc.strip() in ("india", "in", "anywhere"):
        return "not_stated", "location not given"
    if any(c in loc for c in cities):
        return "pass", lead.get("location")
    if "remote" in loc or "work from home" in loc or "wfh" in loc:
        padded = " " + loc + " "
        if "india" not in loc and any(w in padded for w in FOREIGN_WORDS):
            return "fail", "remote outside India: " + lead.get("location")
        return "pass", "remote: " + lead.get("location")
    return "fail", lead.get("location")


def gate_years(g, lead):
    r = g.get("rule") or {}
    mn, mx = float(r.get("min", 0)), float(r.get("max", 99))
    ya = years_asked((lead.get("jd_text") or "") + "\n" + (lead.get("raw_snippet") or lead.get("snippet") or ""))
    if not ya:
        return "not_stated", "years not stated"
    lo, hi = ya
    txt = f"{lo}+ years" if hi is None else f"{lo}-{hi} years"
    return ("pass" if _overlap(lo, hi, mn, mx) else "fail"), txt


def gate_title(g, lead):
    t = lead.get("title") or ""
    if re.search(r"product\s+marketing", t, re.I):
        return "fail", t
    if ROLE_PASS_RE.search(t):
        return "pass", t
    if ROLE_FAIL_RE.search(t):
        return "fail", t
    return "unclear", t


def gate_ai(g, lead, jev):
    """Yes/no question to Jev about the job only. Fail only when Jev is at least 80% sure the answer is no."""
    if not jev or getattr(jev, "blocked", None):
        return "not_stated", "no AI check available"
    st = {"job": {"title": lead.get("title"), "company": lead.get("company"), "location": lead.get("location"),
                  "job_description": ((lead.get("jd_text") or lead.get("raw_snippet") or "")[:JEV_JD_CHARS] or "not fetched")}}
    try:
        ans = jev.evaluate(st, {"g": {"type": "boolean", "instructions": g.get("ask") or g.get("description") or g.get("name"),
                                      "criteria": {"true": g.get("pass") or "yes", "false": g.get("fail") or "no"}}}, timeout=45)
        p = float((ans.get("g") or {}).get("probability"))
    except Exception as e:
        return "not_stated", "AI check failed: " + str(e)[:80]
    if p < GATE_FAIL_P:
        return "fail", f"Jev p(yes)={p:.2f}"
    return ("pass" if p >= 0.5 else "not_stated"), f"Jev p(yes)={p:.2f}"


def check_gates(rub, lead, jev=None):
    """Returns (failed_gate_name or None, {key: {result, why}}). 'not_stated' always lets the job through unless the gate says if_unknown=fail."""
    res, failed = {}, None
    for g in (rub or {}).get("gates") or []:
        if g.get("enabled") is False:
            continue
        typ = (g.get("rule") or {}).get("type")
        if typ == "location":
            r, why = gate_location(g, lead)
        elif typ == "years":
            r, why = gate_years(g, lead)
        elif typ == "title":
            r, why = gate_title(g, lead)
            if r == "unclear":
                r, why = gate_ai(g, lead, jev)
        else:
            r, why = gate_ai(g, lead, jev)
        if r == "not_stated" and g.get("if_unknown") == "fail":
            r = "fail"
        res[g["key"]] = {"result": r, "why": str(why or "")[:120]}
        if r == "fail" and not failed:
            failed = g.get("name") or g["key"]
    return failed, res


def gate_reason(failed, res, rub):
    g = next((x for x in (rub or {}).get("gates") or [] if (x.get("name") or x["key"]) == failed), {})
    why = (res.get(g.get("key")) or {}).get("why") or ""
    return f"Failed: {failed}" + (f" ({why[:60]})" if why else "")


def rule_param_scores(rub, lead):
    """Weighted params that code scores from the job itself (rule: years_grade). {key: score or None}."""
    out = {}
    for p in (rub or {}).get("params") or []:
        r = p.get("rule") or {}
        if p.get("enabled") is False or r.get("type") != "years_grade":
            continue
        ya = years_asked((lead.get("jd_text") or "") + "\n" + (lead.get("raw_snippet") or lead.get("snippet") or ""))
        if not ya:
            out[p["key"]] = None
            continue
        lo, hi = ya
        hb, mb = r.get("high") or [8, 10], r.get("mid") or [6, 11]
        out[p["key"]] = 90 if _overlap(lo, hi, hb[0], hb[1]) else (50 if _overlap(lo, hi, mb[0], mb[1]) else 10)
    return out


def apply_rule_params(rub, lead, params):
    """Override AI scores for rule params when the rule could read the job; recompute total and caps."""
    rp = rule_param_scores(rub, lead)
    for k, v in rp.items():
        if v is not None:
            params[k] = {"score": v, "why": "from the years the job asks for (rule)"}
    return compute_fit(rub, params)


def gate_leads(leads, rubrics, noise, run, jev=None):
    """Mark leads that fail a gate as parked (in place). Returns the leads that passed."""
    passed = []
    for l in leads:
        rv = rubrics.get(l.get("job_stream_id"))
        rub = (rv or {}).get("rubric") or {}
        if not rub.get("gates"):
            passed.append(l)
            continue
        failed, res = check_gates(rub, l, jev)
        fb = dict(l.get("fit_breakdown") or {})
        fb["gates"] = res
        l["fit_breakdown"] = fb
        if failed:
            reason = gate_reason(failed, res, rub)
            l["status"], l["noise_reason_id"], l["matched_criterion"] = "parked", noise.get("Failed mandatory gate"), reason[:200]
            run.parked += 1
            run.notes.append(f"gate: {l.get('company')} · {l.get('title')} → {reason}"[:200])
        else:
            passed.append(l)
    return passed


def gate_sweep(sb, llm, agents, settings, run, jev=None, limit=8):
    """Leads still live (new / fit_checked, last 21 days) that were scored on an older rubric: run the gates, park failures,
    re-score the rest on the active rubric (up to `limit` per run, the rest on later runs). Promoted leads are never parked."""
    streams, docs, _, _, _, noise = load_context(sb)
    rubrics = load_rubrics(sb, streams)
    live = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "in.(new,fit_checked)", "created_at": "gte." + iso(now_utc() - timedelta(days=21)),
                               "select": "id,title,company,location,raw_snippet,jd_text,job_stream_id,fit_breakdown,status", "order": "created_at.desc", "limit": "200"})
    todo = []
    for l in live:
        rv = rubrics.get(l.get("job_stream_id"))
        if not rv or not ((rv.get("rubric") or {}).get("gates")):
            continue
        if (l.get("fit_breakdown") or {}).get("rubric_version") == rv.get("version") and "gates" in (l.get("fit_breakdown") or {}):
            continue
        todo.append(l)
    if not todo:
        return 0
    parked = n = 0
    keep = []
    for l in todo:
        before = run.parked
        gate_leads([l], rubrics, noise, run, jev)
        if run.parked > before:
            sb.update("leads", {"id": l["id"]}, {"status": "parked", "noise_reason_id": l.get("noise_reason_id"), "matched_criterion": l.get("matched_criterion"),
                                                  "fit_breakdown": l["fit_breakdown"]})
            parked += 1
        else:
            keep.append(l)
    for s in streams:
        items = [l for l in keep if l.get("job_stream_id") == s["id"]][:limit]
        resume = resume_for(s, docs)
        if not items or not resume or llm.gave_up_429:
            continue
        thr = stream_threshold(rubrics, settings, s["id"])
        res = score_items(llm, agents, s, resume, items, rubrics.get(s["id"]), run, "gate_sweep")
        for k, (fs, fb) in res.items():
            fb = dict(fb or {}); fb["gates"] = (items[k].get("fit_breakdown") or {}).get("gates")
            patch = {"fit_score": fs, "fit_breakdown": fb, "fit_shadow": None}
            if fs is not None and fs < thr:
                patch.update(status="parked", noise_reason_id=noise.get("Fit below threshold"), matched_criterion="Fit below threshold")
            sb.update("leads", {"id": items[k]["id"]}, patch)
            n += 1
    run.notes.append(f"gate sweep: {parked} parked by a gate, {n} re-scored on the new rubric, {max(0, len(keep) - n)} left for later")
    return parked + n


PORTFOLIO_RAW = "https://raw.githubusercontent.com/sudharsan454/sudharsan454.github.io/main/"
NOTES_SYS = ("You turn a product manager's portfolio website text into career notes for a job-matching system. "
             "Write plain bullet lines, no marketing words. Cover: years and titles, products owned and what they did, measurable results, "
             "domains and markets worked in, team size and leadership, technical depth (AI, data, platforms), go-to-market work, and anything a resume might underplay. "
             "Only facts stated in the text. Max 2500 characters. Output JSON {\"notes\": \"...\"}.")


def portfolio_text():
    pages = ["index.html"]
    try:
        st, d = http("GET", "https://api.github.com/repos/sudharsan454/sudharsan454.github.io/contents/work", None, timeout=20)
        if st < 300 and isinstance(d, list):
            pages += ["work/" + x["name"] for x in d if str(x.get("name", "")).endswith(".html")][:8]
    except Exception:
        pass
    out = []
    for p in pages:
        try:
            req = urllib.request.Request(PORTFOLIO_RAW + p, headers={"User-Agent": "job-driver"})
            raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        except Exception:
            continue
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
        out.append(f"[{p}] {txt[:6000]}")
    return "\n\n".join(out)[:24000]


def career_notes_refresh(llm, settings, run):
    """Once a day: read the portfolio and store a synthesis in settings.career_notes_auto. Your own Extra notes stay in settings.career_notes."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if settings.get("career_notes_auto_date") == today:
        return False
    txt = portfolio_text()
    if not txt:
        run.notes.append("career notes: portfolio not readable")
        return False
    notes = None
    try:
        out = llm_json_checked(llm, NOTES_SYS, txt, lambda o: isinstance(o, dict) and isinstance(o.get("notes"), str))
        notes = out["notes"].strip()[:3000]
    except Exception as e:
        run.errors.append({"stage": "career_notes", "error": str(e)[:200]})
    if not notes:
        notes = txt[:3000]
    settings.set(career_notes_auto=notes, career_notes_auto_date=today, career_notes_auto_source="sudharsan454.github.io")
    run.notes.append(f"career notes: refreshed from the portfolio ({len(notes)} chars)")
    return True


def career_notes_all(settings):
    a, b = (settings.get("career_notes_auto") or "").strip(), (settings.get("career_notes") or "").strip()
    return ("From portfolio:\n" + a if a else "") + ("\n\nExtra notes:\n" + b if b else "")


def _jev_of(x):
    return getattr(x, 'jev', None) or getattr(getattr(x, 'base', None), 'jev', None)


def fit_backlog(sb, llm, agents, settings, run, exclude_keys=()):
    """Leads saved earlier but left unscored (fit was off, not due, or the AI limit hit) get scored now."""
    streams, docs, _, _, _, noise = load_context(sb)
    rubrics = load_rubrics(sb, streams)
    cfg = agents.get("fit")
    limit = 2 * max(1, int((cfg or {}).get("max_items") or FIT_BATCH))
    backlog = [l for l in sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.new", "created_at": "gte." + iso(now_utc() - timedelta(days=7)),
                                              "select": "id,title,company,location,raw_snippet,jd_text,job_stream_id,dedup_key", "order": "created_at.desc", "limit": str(limit)})
               if l.get("dedup_key") not in exclude_keys and l.get("id")]
    n = 0
    for s in streams:
        items = [l for l in backlog if l.get("job_stream_id") == s["id"]]
        resume = resume_for(s, docs)
        if not items or not resume or llm.gave_up_429:
            continue
        thr = stream_threshold(rubrics, settings, s["id"])
        before = run.parked
        passed = gate_leads(items, rubrics, noise, run, _jev_of(llm))
        for l in items:
            if l not in passed:
                sb.update("leads", {"id": l["id"]}, {"status": "parked", "noise_reason_id": l.get("noise_reason_id"), "matched_criterion": l.get("matched_criterion"), "fit_breakdown": l.get("fit_breakdown")})
        items = passed
        if not items:
            continue
        res = score_items(llm, agents, s, resume, items, rubrics.get(s["id"]), run, "fit_backlog")
        for k, (fs, fb) in res.items():
            if isinstance(fb, dict) and (items[k].get("fit_breakdown") or {}).get("gates"):
                fb["gates"] = items[k]["fit_breakdown"]["gates"]
            patch = {"fit_score": fs, "fit_breakdown": fb, "status": "fit_checked"}
            if fs is not None and fs < thr:
                patch.update(status="parked", noise_reason_id=noise.get("Fit below threshold"), matched_criterion="Fit below threshold")
                run.parked += 1
            sb.update("leads", {"id": items[k]["id"]}, patch)
            n += 1
    if n:
        run.notes.append(f"backlog: scored {n} earlier leads")
    return n


def run_evals(sb, base_llm, agents, settings, max_runs=1):
    """Process queued eval runs for the Fit agent (queued from the app). Never writes to leads."""
    fit = agents.get("fit")
    if not fit:
        return 0
    try:
        queued = sb.select("agent_eval_runs", {"owner_id": "eq." + OWNER_ID, "agent_id": "eq." + fit["id"], "status": "eq.queued",
                                               "select": "*", "order": "requested_at.asc", "limit": str(max_runs)})
    except Exception as e:
        log(f"eval runs not readable: {str(e)[:120]}")
        return 0
    done = 0
    for er in queued:
        run = Run(sb, "evals", "-")
        sb.update("agent_eval_runs", {"id": er["id"]}, {"status": "running", "started_at": iso(now_utc())})
        try:
            pv = None
            if er.get("prompt_version_id"):
                rows = sb.select("agent_prompt_versions", {"id": "eq." + er["prompt_version_id"], "select": "id,version,system_template"})
                pv = rows[0] if rows else None
            ev_agents = dict(agents)
            ev_agents["fit"] = dict(fit, prompt=pv or fit.get("prompt"))
            streams, docs, _, _, _, _ = load_context(sb)
            rubrics = load_rubrics(sb, streams, ids=list((er.get("rubric_version_ids") or {}).values()) or None)
            for s in streams:  # a stream not in the request uses its active rubric
                if s["id"] not in rubrics:
                    rubrics.update(load_rubrics(sb, [s]))
            cases = sb.select("agent_evals", {"owner_id": "eq." + OWNER_ID, "agent_id": "eq." + fit["id"], "is_active": "eq.true", "expected_band": "not.is.null", "select": "*"})
            n_calls = sum(-(-len([c for c in cases if c.get("job_stream_id") == s["id"]]) // max(1, int(fit.get("max_items") or FIT_BATCH))) for s in streams)
            llm = AgentLLM(base_llm, ev_agents["fit"], max_calls_default=None)
            llm.max_calls = n_calls * 2 + 2   # the request is explicit; allow one retry per batch, not the live per-run cap
            results, err_n = [], 0
            for s in streams:
                cs = [c for c in cases if c.get("job_stream_id") == s["id"]]
                if not cs:
                    continue
                rv = rubrics.get(s["id"])
                thr = float(((rv or {}).get("rubric") or {}).get("threshold", settings.get("fit_threshold", 60)))
                res = score_items(llm, ev_agents, s, resume_for(s, docs), [dict(c.get("input") or {}) for c in cs], rv, run, "evals")
                for k, c in enumerate(cs):
                    i = c.get("input") or {}
                    band = c.get("expected_band")
                    lo, hi, push = BANDS.get(band, (c.get("expected_min") or 0, c.get("expected_max") or 100, False))
                    lo = c.get("expected_min") if c.get("expected_min") is not None else lo
                    hi = c.get("expected_max") if c.get("expected_max") is not None else hi
                    row = {"case_id": c["id"], "title": i.get("title"), "company": i.get("company"), "stream_id": s["id"], "expected_band": band, "expected_min": lo, "expected_max": hi, "threshold": thr}
                    if k in res and res[k][0] is not None:
                        got, fb = res[k]
                        row.update(got=got, decision_pass=(got >= thr) == push, band_pass=lo <= got <= hi,
                                   params=(fb or {}).get("params"), basis=(fb or {}).get("basis"), note=(fb or {}).get("note"), caps_applied=(fb or {}).get("caps_applied") or [])
                    else:
                        err_n += 1
                        row.update(got=None, decision_pass=False, band_pass=False, error="not scored (AI error or limit)")
                    results.append(row)
            scored = [r for r in results if r.get("got") is not None]
            limit_hit = llm.gave_up_429 and not llm.capped
            if not scored and results and limit_hit:
                sb.update("agent_eval_runs", {"id": er["id"]}, {"status": "queued", "started_at": None,
                                                                 "error": f"waiting: AI limit hit at {datetime.now(IST).strftime('%H:%M')} IST, retries next pass"})
                run.notes.append("eval run put back in the queue: AI limit")
            else:
                dp = sum(1 for r in scored if r["decision_pass"])
                bp = sum(1 for r in scored if r["band_pass"])
                t = len(scored)
                sb.update("agent_eval_runs", {"id": er["id"]}, {
                    "status": "done", "finished_at": iso(now_utc()), "model": llm.label, "total": t, "decision_pass": dp, "band_pass": bp,
                    "decision_agreement": round(100.0 * dp / t, 1) if t else None, "band_agreement": round(100.0 * bp / t, 1) if t else None,
                    "results": results, "error": (f"{err_n} cases not scored" if err_n else None)})
                run.read, run.created = len(results), t
                run.notes.append(f"eval run: {t} cases scored, decision {dp}/{t}, band {bp}/{t}" + (f", {err_n} not scored" if err_n else ""))
                done += 1
            run.model = llm.label
            run.finish(llm)
        except Exception as e:
            sb.update("agent_eval_runs", {"id": er["id"]}, {"status": "failed", "finished_at": iso(now_utc()), "error": str(e)[:500]})
            run.errors.append({"stage": "evals", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]})
            run.finish()
    return done


# ---------------------------------------------------------------- Sourcer + Fit
def sender_domains(sb):
    doms = set(DEFAULT_SENDERS)
    for a in sb.select("alert_definitions", {"owner_id": "eq." + OWNER_ID, "select": "sender_pattern"}):
        p = (a.get("sender_pattern") or "").replace("from:", "").strip().lower()
        if p:
            doms.add(p.split("@")[-1])
    return doms


def load_context(sb):
    streams = sb.select("job_streams", {"owner_id": "eq." + OWNER_ID, "is_active": "eq.true", "select": "id,name,goal,target_titles,locations,generic_document_id,fit_rubric_version_id"})
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


LI_META = re.compile(r"(actively hiring|alumni|connections?$|apply with resume|easy apply|applicants?|early applicant|promoted|actively recruiting|"
                     r"fast.growing|in your network|\bago$|viewed|reposted|top applicant|hiring now|responses? managed|verified)", re.I)
LI_AGO = re.compile(r"(\d+)\s*(minute|hour|day|week|month)s?\s+ago", re.I)


def parse_linkedin_alert(text):
    """Fixed-rule reader for LinkedIn job-alert mails (text part: title / company / location lines, then 'View job: <url>').
    Returns a list of jobs, or None when the layout is not recognised (caller then falls back to Gemini)."""
    if "View job:" not in text:
        return None
    jobs, seen = [], set()
    chunks = re.split(r"\n-{5,}\n", text)
    for ch in chunks:
        m = re.search(r"View job:\s*(https?://\S+)", ch)
        if not m:
            continue
        jid = re.search(r"/jobs/view/(\d+)", m.group(1))
        if not jid:
            return None
        before = [ln.strip() for ln in ch[:m.start()].splitlines()]
        before = [ln for ln in before if ln and not ln.startswith("<") and "http" not in ln]
        meta = [ln for ln in before if LI_META.search(ln)]
        core = [ln for ln in before if not LI_META.search(ln)]
        if len(core) < 3:
            return None
        title, company, location = core[-3], core[-2], core[-1]
        if len(location) > 60 or len(company) > 100 or len(title) > 200:
            return None
        if jid.group(1) in seen:
            continue
        seen.add(jid.group(1))
        ago = next((LI_AGO.search(x).group(0) for x in meta if LI_AGO.search(x)), None)
        jobs.append({"title": title, "company": company, "location": location,
                     "url": f"https://www.linkedin.com/jobs/view/{jid.group(1)}/",
                     "easy_apply": True if any("easy apply" in x.lower() for x in meta) else None,
                     "posted_text": ago, "snippet": "; ".join(meta)[:200], "stream": None})
    return jobs or None


def stream_by_title(title, streams):
    """Pick the stream whose target title matches the job title best (longest match); ties go to the PM stream."""
    t = (title or "").lower()
    best, best_len = None, 0
    for s in streams:
        for tt in s.get("target_titles") or []:
            k = tt.lower()
            if k and k in t and (len(k) > best_len or (len(k) == best_len and s["id"] == PM_STREAM)):
                best, best_len = s, len(k)
    return best


def sourcer(sb, gmail, llm, settings, run, dry_fixtures=None, agents=None, llm_fit=None, do_fit=True):
    streams, docs, boards, alerts, criteria, noise = load_context(sb)
    agents = agents or {}
    scfg = agents.get("sourcer")
    llm_fit = llm_fit or llm
    rubrics = load_rubrics(sb, streams)
    max_mails = int((scfg or {}).get("max_items") or MAX_MAILS_PER_RUN)
    rules_first = guard_on(scfg, "rules_first", True)
    extract_sys = render_system("sourcer", template_for(agents, "sourcer"), streams=streams)
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
        uids = sorted(uids)
        retry = {int(r["uid"]): int(r.get("tries", 0)) for r in (settings.get("mail_retry") or []) if r.get("uid")}
        retry_uids = sorted(u for u in retry if u not in uids)
        if len(uids) > max_mails:
            run.notes.append(f"{len(uids)} new mails, taking {max_mails} this run")
            uids = uids[:max_mails]
        max_uid = int(last_uid or 0)
        for u in retry_uids + uids:
            if u not in retry:
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
            mails.append({"uid": u, "msg_id": mid, "from": frm, "subject": msg.get("Subject") or "", "date": dt, "text": mail_text(msg)[:14000],
                          "tries": retry.get(u, 0)})
        if max_uid and not sb.dry:
            settings.set(imap_last_uid=max_uid)  # always forward; unfinished mails live in mail_retry instead of rewinding
    run.read = len(mails)
    log(f"[sourcer] {len(mails)} alert mails to read")

    # 2) extract jobs per mail
    new_leads = []
    t_start = time.time()
    retry_next = []   # [{"uid", "tries", "msg_id"}] carried to the next run
    rule_mails = 0
    for idx, m in enumerate(mails):
        if time.time() - t_start > EXTRACT_BUDGET_S:
            rest = mails[idx:]
            run.notes.append(f"time budget hit; {len(rest)} mails moved to the retry list")
            retry_next += [{"uid": x["uid"], "tries": x.get("tries", 0), "msg_id": x["msg_id"]} for x in rest if x["uid"]]
            break
        out = None
        if rules_first and "linkedin.com" in m["from"]:
            jobs = parse_linkedin_alert(m["text"])
            if jobs:
                out = {"is_job_alert": True, "jobs": jobs}
                rule_mails += 1
        if out is None:
            if llm.gave_up_429:
                # limit already hit this run: don't burn more calls, keep the mail for later
                retry_next.append({"uid": m["uid"], "tries": m.get("tries", 0), "msg_id": m["msg_id"]})
                continue
            try:
                out = llm_json_checked(llm, extract_sys, f"From: {m['from']}\nSubject: {m['subject']}\nDate: {m['date']}\n\n{m['text']}",
                                       lambda o: isinstance(o, dict) and isinstance(o.get("jobs", []), list))
            except Exception as e:
                tries = m.get("tries", 0) + 1
                if m["uid"] and tries < MAX_MAIL_TRIES:
                    retry_next.append({"uid": m["uid"], "tries": tries, "msg_id": m["msg_id"]})
                    run.errors.append({"mail": m["msg_id"], "stage": "extract", "error": str(e)[:300], "will_retry": True, "try": tries})
                else:
                    run.errors.append({"mail": m["msg_id"], "stage": "extract", "error": str(e)[:300], "dropped_after_tries": tries})
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
            st = stream_by_name.get((j.get("stream") or "").lower()) or stream_by_title(j["title"], streams) \
                or next((s for s in streams if s["id"] == PM_STREAM), streams[0])
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

    if rule_mails:
        run.notes.append(f"{rule_mails} LinkedIn mails read by rules (no Gemini call)")
    if dry_fixtures is None and not sb.dry:
        settings.set(mail_retry=[r for r in retry_next if r.get("uid")][:100])
    elif retry_next:
        run.notes.append(f"dry run: {len(retry_next)} mails would go to the retry list")

    # 2b) JD Fetcher: full job description for every live lead before Fit (v1.0.8; on/off and max pages from the jd_fetcher agent row since v1.0.9)
    do_jd, why_jd = due(agents, "jd_fetcher", "cycle")
    jdb = JDBudget(dry=sb.dry, limit=(int((agents.get("jd_fetcher") or {}).get("max_items") or JD_MAX_PER_RUN) if do_jd else 0))
    if not do_jd:
        run.notes.append("JD fetcher: " + why_jd)
    run.jd_budget = jdb
    for l in new_leads:
        if l["status"] != "new" or not l.get("url") or not jdb.left():
            continue
        r = jdb.fetch(l["url"], l["title"])
        l["jd_fetch_attempts"] = 1
        if r.get("error"):
            l["jd_last_error"] = r["error"][:300]
        else:
            l.update(jd_text=r["text"], jd_source_url=r["source_url"], jd_confidence=r["confidence"], jd_fetched_at=iso(now_utc()))
    if jdb.n:
        run.notes.append(f"JD: {jdb.ok} fetched, {jdb.failed} failed for new leads")

    # 2c) mandatory gates (v1.0.17): a failed gate parks the lead before any scoring
    gate_leads([l for l in new_leads if l["status"] == "new"], rubrics, noise, run, _jev_of(llm_fit) or _jev_of(llm))

    # 3) fit scoring for live leads, per stream (rubric from the Agents screen; batch size = Fit "max items")
    live = [l for l in new_leads if l["status"] == "new"]
    if live and not do_fit:
        run.notes.append(f"fit is off or not due: {len(live)} leads saved unscored")
    for s in (streams if do_fit else []):
        batch_all = [l for l in live if l["job_stream_id"] == s["id"]]
        if not batch_all:
            continue
        resume = resume_for(s, docs)
        if not resume:
            run.notes.append(f"stream {s['name']}: no generic resume, leads left unscored")
            continue
        res = score_items(llm_fit, agents, s, resume, batch_all, rubrics.get(s["id"]), run, "fit")
        for k, (fs, fb) in res.items():
            batch_all[k]["fit_score"], batch_all[k]["fit_breakdown"], batch_all[k]["status"] = fs, fb, "fit_checked"

    # 4) write
    if new_leads:
        for l in new_leads:
            if l["status"] == "fit_checked" and l.get("fit_score") is not None and l["fit_score"] < stream_threshold(rubrics, settings, l["job_stream_id"]):
                l["status"], l["noise_reason_id"], l["matched_criterion"] = "parked", noise.get("Fit below threshold"), "Fit below threshold"
                run.parked += 1
        keys = set().union(*(l.keys() for l in new_leads))
        for l in new_leads:
            for k in keys:
                l.setdefault(k, 0 if k == "jd_fetch_attempts" else None)
        if run.id and not sb.dry:
            for l in new_leads:
                l["agent_run_id"] = run.id
        rows = sb.insert("leads", new_leads)
        run.created = len(rows)
        for aid in {l["alert_definition_id"] for l in new_leads if l.get("alert_definition_id")}:
            sb.update("alert_definitions", {"id": aid}, {"last_lead_at": iso(now_utc())})

    # 6) JD backlog (v1.0.8): earlier leads and open applications that still have no JD.
    #    v1.0.14: OFF by default (Sudharsan, 20 Oct). Only new leads get a JD. Turn back on with user_settings.settings.jd_backlog = true.
    try:
        if settings.get("jd_backlog") is True:
          jd_backlog(sb, llm_fit, settings, run, streams, docs, getattr(run, "jd_budget", None) or JDBudget(dry=sb.dry, limit=0),
                     skip={l.get("dedup_key") for l in new_leads}, agents=agents, rubrics=rubrics, do_fit=do_fit)
    except Exception as e:
        run.errors.append({"stage": "jd_backlog", "error": str(e)[:300]})
    return new_leads


def jd_backlog(sb, llm, settings, run, streams, docs, jdb, skip=(), agents=None, rubrics=None, do_fit=True):
    agents, rubrics = agents or {}, rubrics or {}
    since = iso(now_utc() - timedelta(days=14))
    leads = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "in.(new,fit_checked,promoted)", "jd_text": "is.null",
                                "jd_fetch_attempts": "lt." + str(JD_MAX_TRIES), "url": "not.is.null", "created_at": "gte." + since,
                                "select": "id,title,company,location,raw_snippet,url,status,job_stream_id,jd_fetch_attempts,fit_score,dedup_key",
                                "order": "created_at.desc", "limit": "30"})
    rescore, n_ok, n_fail = [], 0, 0
    for l in leads:
        if not jdb.left():
            break
        if not l.get("id") or not l.get("url") or l.get("dedup_key") in skip:
            continue
        r = jdb.fetch(l["url"], l.get("title", ""))
        tries = int(l.get("jd_fetch_attempts") or 0) + 1
        if r.get("error"):
            n_fail += 1
            patch = {"jd_fetch_attempts": tries, "jd_last_error": r["error"][:300]}
            if tries >= JD_MAX_TRIES:
                patch["jd_confidence"] = "fetch_failed"
            sb.update("leads", {"id": l["id"]}, patch)
            continue
        n_ok += 1
        sb.update("leads", {"id": l["id"]}, {"jd_text": r["text"], "jd_source_url": r["source_url"], "jd_confidence": r["confidence"],
                                             "jd_fetched_at": iso(now_utc()), "jd_fetch_attempts": tries, "jd_last_error": None})
        if l.get("status") == "fit_checked":
            l["jd_text"] = r["text"]
            rescore.append(l)
    if leads:
        run.notes.append(f"JD backlog: {n_ok} lead JDs filled, {n_fail} failed")

    # open applications (no lead, or a lead without JD): fill straight from the application's own link
    tries_map = settings.get("jd_app_attempts") or {}
    apps = sb.select("applications", {"owner_id": "eq." + OWNER_ID, "status": "in.(" + ",".join(OPEN_STATUSES) + ")", "jd_text": "is.null",
                                      "url": "not.is.null", "select": "id,title,company,url,status", "order": "updated_at.desc", "limit": "30"})
    a_ok = a_fail = 0
    for a in apps:
        if not jdb.left():
            break
        if not a.get("id") or not a.get("url") or int(tries_map.get(a["id"], 0)) >= JD_MAX_TRIES:
            continue
        r = jdb.fetch(a["url"], a.get("title", ""))
        tries_map[a["id"]] = int(tries_map.get(a["id"], 0)) + 1
        if r.get("error"):
            a_fail += 1
            if tries_map[a["id"]] >= JD_MAX_TRIES:
                sb.update("applications", {"id": a["id"]}, {"jd_confidence": "fetch_failed"})
            continue
        a_ok += 1
        sb.update("applications", {"id": a["id"]}, {"jd_text": r["text"], "jd_source_url": r["source_url"], "jd_confidence": r["confidence"],
                                                    "jd_fetched_at": iso(now_utc())})
    if apps:
        run.notes.append(f"JD backlog: {a_ok} application JDs filled, {a_fail} failed")
        if not sb.dry:
            settings.set(jd_app_attempts=tries_map)

    # re-score leads that were scored on the title alone; status is left as it is (they may already be on his phone)
    if rescore and do_fit and not llm.gave_up_429:
        for s in streams:
            resume = resume_for(s, docs)
            todo = [l for l in rescore if l.get("job_stream_id") == s["id"]]
            if not todo or not resume or llm.gave_up_429:
                continue
            res = score_items(llm, agents, s, resume, todo, rubrics.get(s["id"]), run, "fit_rescore")
            for k, (fs, fb) in res.items():
                if isinstance(fb, dict):
                    fb["rescored_with_jd"] = True
                    fb["previous_score"] = todo[k].get("fit_score")
                sb.update("leads", {"id": todo[k]["id"]}, {"fit_score": fs, "fit_breakdown": fb})
            if res:
                run.notes.append(f"re-scored {len(res)} leads with full JD ({s['name']})")


# ---------------------------------------------------------------- Notifier
def fmt_lead(l):
    fb = l.get("fit_breakdown") or {}
    return (f"<b>{html.escape(l['title'])}</b> · {html.escape(l['company'])}\n"
            f"{html.escape(l.get('location') or '—')} · fit <b>{l.get('fit_score') if l.get('fit_score') is not None else '?'}</b> · {l.get('age_days', '?')}d old"
            f"{' · easy apply' if l.get('easy_apply') else ''}\n"
            f"{html.escape(str(fb.get('note') or fb.get('domain') or ''))[:160]}"
            + (f"\nResume: <b>{'Tailor' if l.get('resume_decision') == 'tailored' else 'Generic is enough'}</b>{' (unsure, your call)' if l.get('resume_low_confidence') else ''} · {html.escape(str(l.get('resume_reason') or ''))[:120]}"
               if l.get("resume_decision") in ("generic", "tailored") else ""))


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
    streams = sb.select("job_streams", {"owner_id": "eq." + OWNER_ID, "select": "id,fit_rubric_version_id"})
    rubrics = load_rubrics(sb, streams)
    thrs = [stream_threshold(rubrics, settings, s["id"]) for s in streams] or [float(settings.get("fit_threshold", 60))]
    leads = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.fit_checked", "fit_score": "gte." + fmt_num(min(thrs)),
                                "select": "id,title,company,location,url,fit_score,fit_breakdown,age_days,easy_apply,created_at,job_stream_id,resume_decision,resume_low_confidence,resume_reason", "order": "fit_score.desc,created_at.desc", "limit": "50"})
    leads = [l for l in leads if l["id"] not in notified and float(l.get("fit_score") or 0) >= stream_threshold(rubrics, settings, l.get("job_stream_id"))][:budget]
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
def status_sync(sb, gmail, llm, settings, run, agents=None):
    agents = agents or {}
    cfg = agents.get("status_sync")
    status_sys = render_system("status_sync", template_for(agents, "status_sync"))
    min_conf = float(guard_value(cfg, "min_confidence", 0.7) or 0)
    max_items = int((cfg or {}).get("max_items") or 0) or None
    classified = 0
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
            if max_items and classified >= max_items:
                run.notes.append(f"max {max_items} mails classified; the rest wait for tomorrow")
                return
            if llm.gave_up_429:
                run.notes.append("AI limit or max AI calls reached; the rest wait for tomorrow")
                return
            try:
                classified += 1
                out = llm_json_checked(llm, status_sys, f"Application: {a['title']} at {comp}\nFrom: {frm}\nSubject: {msg.get('Subject')}\n\n{text}",
                                       lambda o: isinstance(o, dict) and "outcome" in o)
            except Exception as e:
                run.errors.append({"stage": "status_classify", "company": comp, "error": str(e)[:200]})
                continue
            oc, conf = out.get("outcome"), float(out.get("confidence") or 0)
            if conf < min_conf or oc in ("other", "acknowledgement"):
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
    # v1.0.16: alerts with no leads are not reported (Sudharsan, 25 Oct: only tell me when there IS something)
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
# ---------------------------------------------------------------- Jev (TypeSafe) via Vercel AI Gateway + Resume Decider + Fit shadow (v1.0.9)
# Jev answers typed questions (score / boolean / choice) with probabilities; it never writes text.
# Every rubric parameter becomes one Score question (criteria = the three anchors low/mid/high -> 10/50/90) plus one Boolean
# "is there enough information to judge it?". The weighting, if-unknown rule and caps stay in compute_fit, same as the Gemini path.
JEV_URL = "https://ai-gateway.vercel.sh/v1/evaluate"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
JEV_PRICE_PER_M_IN = 0.04   # USD per million input tokens (estimate; output free)


def jev_direct_key():
    for k in ("TYPESAFE_API_KEY", "TYPEFACE_API_KEY", "JEV_API_KEY"):
        if os.environ.get(k):
            return os.environ[k], k
    return None, None


def make_jev():
    """v1.0.15: TypeSafe direct first, Vercel AI Gateway second, else None."""
    key, name = jev_direct_key()
    if key:
        return Jev(key, direct=True, key_name=name)
    if os.environ.get("AI_GATEWAY_API_KEY"):
        return Jev(os.environ["AI_GATEWAY_API_KEY"], key_name="AI_GATEWAY_API_KEY")
    return None
JEV_JD_CHARS, JEV_RESUME_CHARS, JEV_NOTES_CHARS = 12000, 9000, 6000   # Vercel caps Jev at 32K tokens per request
OUTAGE_RE = re.compile(r"(jev 40[23]|free tier users|insufficient|no AI model available|no AI_GATEWAY|\b429\b|\b503\b|high demand|limit|max AI calls|timed? ?out)", re.I)
RESUME_SYS = "DECIDE_RESUME. You decide how much a candidate's generic resume needs tailoring for one job. JSON only."


class Jev:
    def __init__(self, key, model=None, dry=False, direct=False, key_name=None):
        self.key, self.dry, self.direct, self.key_name = key, dry, direct, key_name
        envm = os.environ.get("JEV_MODEL") or ""
        if direct:
            self.model = model or (envm if envm.startswith("jev") else "jev-latest")
        else:
            self.model = model or (envm if envm.startswith("typesafe") else "typesafe-ai/jev")
        self.route = "typesafe" if direct else "vercel"
        self.calls = self.errors = self.tokens_in = 0
        self.cost = 0.0

    def evaluate(self, state, questions, timeout=60):
        self.calls += 1
        if self.dry:
            out = {}
            for k, q in questions.items():
                if q["type"] == "score":
                    out[k] = {"type": "score", "score": 1.4, "probabilities": {"0": 0.1, "1": 0.4, "2": 0.5}}
                elif q["type"] == "boolean":
                    out[k] = {"type": "boolean", "probability": 0.8}
                else:
                    first = list(q["criteria"])[-1]
                    out[k] = {"type": "choice", "choice": first, "probabilities": {c: (0.7 if c == first else 0.3) for c in q["criteria"]}}
            return out
        if self.direct:
            qs = {k: (dict(q, type="noul") if q.get("type") == "boolean" else q) for k, q in questions.items()}
            st, d = http("POST", TYPESAFE_URL, {"model": self.model, "state": state, "questions": qs},
                         headers={"Authorization": "Bearer " + self.key}, timeout=timeout)
        else:
            st, d = http("POST", JEV_URL, {"model": self.model, "state": state, "questions": questions},
                         headers={"Authorization": "Bearer " + self.key}, timeout=timeout)
        if st >= 300 or not isinstance(d, dict):
            self.errors += 1
            raise RuntimeError(f"jev {st} ({self.route}): {str(d)[:240]}")
        u = d.get("usage") or {}
        tin = int(u.get("input_tokens") or u.get("inputTokens") or 0)
        self.tokens_in += tin
        try:
            c = (((d.get("providerMetadata") or {}).get("gateway") or {}).get("cost"))
            self.cost += float(c) if c is not None else tin * JEV_PRICE_PER_M_IN / 1e6
        except Exception:
            pass
        ans = d.get("answers") or {}
        for k, a in ans.items():
            if isinstance(a, dict) and a.get("type") == "noul" and "probability" not in a:
                a["probability"] = a.get("noul")
                a["type"] = "boolean"
        return ans


def jev_rubric_questions(rub):
    qs = {}
    for p in (rub or {}).get("params") or []:
        if p.get("enabled") is False:
            continue
        if (p.get("rule") or {}).get("type") == "years_grade" or float(p.get("weight") or 0) == 0:
            continue
        a = p.get("anchors") or {}
        qs["s_" + p["key"]] = {"type": "score", "instructions": p.get("ask") or f'Look only at THE JOB (title and job description), not the candidate. {p.get("name")}: {p.get("description") or ""}',
                               "criteria": [a.get("low") or "low", a.get("mid") or "medium", a.get("high") or "high"]}
        qs["k_" + p["key"]] = {"type": "boolean", "instructions": f'Is there enough information here to judge "{p.get("name")}"?',
                               "criteria": {"true": "the details given are enough to judge it", "false": "key details are missing (for example only a job title is known, or no career notes are given)"}}
    return qs


def jev_param_scores(rub, answers, force_unknown=()):
    """{key: {"score": 0-100|None, "why": str, "p": confidence}} from Jev answers."""
    clean = {}
    for p in (rub or {}).get("params") or []:
        if p.get("enabled") is False:
            continue
        k = p["key"]
        s, ok = answers.get("s_" + k) or {}, answers.get("k_" + k) or {}
        judge_p = float(ok.get("probability", 1.0)) if ok else 1.0
        conf = max([float(v) for v in (s.get("probabilities") or {}).values()] or [0.0])
        score = None
        if k not in force_unknown and s.get("score") is not None and judge_p >= 0.5:
            score = int(round(max(0.0, min(100.0, 10 + 40 * float(s["score"])))))
        clean[k] = {"score": score, "why": (f"jev rung {float(s.get('score', 0)):.2f}, p={conf:.2f}" if score is not None else f"cannot judge (p={judge_p:.2f})"), "p": round(conf, 3)}
    return clean


def jev_state(lead, stream, resume, notes=None, extra=None):
    st = {"job": {"title": lead.get("title"), "company": lead.get("company"), "location": lead.get("location"),
                  "snippet": lead.get("raw_snippet") or lead.get("snippet"), "job_description": ((lead.get("jd_text") or "")[:JEV_JD_CHARS] or "not fetched")},
          "job_stream": {"name": stream.get("name"), "goal": stream.get("goal"), "locations": stream.get("locations")},
          "candidate_resume": (resume or "")[:JEV_RESUME_CHARS]}
    if notes is not None:
        st["career_notes"] = (notes or "")[:JEV_NOTES_CHARS] or "none given"
    st.update(extra or {})
    return st


def load_agent_rubrics(sb, streams, field):
    ids = [s.get(field) for s in streams if s.get(field)]
    if not ids:
        return {}
    try:
        rows = sb.select("fit_rubric_versions", {"id": "in.(" + ",".join(ids) + ")", "select": "id,version,job_stream_id,rubric"})
    except Exception as e:
        log(f"rubrics ({field}) not readable: {str(e)[:120]}")
        return {}
    return {r["job_stream_id"]: r for r in rows if r.get("id") in ids}


def fit_shadow(sb, jev, run, limit=20):
    """Jev scores the same leads Gemini scored, with the same fit rubric, into leads.fit_shadow (never used for decisions)."""
    if not jev:
        return 0
    streams, docs, _, _, _, _ = load_context(sb)
    rubrics = load_rubrics(sb, streams)
    try:
        leads = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "fit_score": "not.is.null", "fit_shadow": "is.null", "status": "in.(new,fit_checked,promoted)", "created_at": "gte." + iso(now_utc() - timedelta(days=21)),
                                    "select": "id,title,company,location,raw_snippet,jd_text,job_stream_id", "order": "created_at.desc", "limit": str(limit)})
    except Exception as e:
        run.notes.append(f"fit shadow: leads not readable ({str(e)[:80]})")
        return 0
    n = 0
    for l in leads:
        s = next((x for x in streams if x["id"] == l.get("job_stream_id")), None)
        rv = rubrics.get(l.get("job_stream_id"))
        if not s or not rv:
            continue
        rub = rv["rubric"]
        try:
            ans = jev.evaluate(jev_state(l, s, resume_for(s, docs)), jev_rubric_questions(rub))
        except Exception as e:
            run.errors.append({"stage": "fit_shadow", "lead": l["id"], "error": str(e)[:240]})
            if jev.errors >= 3 or re.search(r"jev 40[23]|free tier users|insufficient", str(e), re.I):
                break
            continue
        params = jev_param_scores(rub, ans)
        total, caps = apply_rule_params(rub, l, params)
        sb.update("leads", {"id": l["id"]}, {"fit_shadow": {"engine": "jev", "model": jev.model, "score": total, "params": params, "caps_applied": caps,
                                                            "rubric_version": rv.get("version"), "at": iso(now_utc())}})
        n += 1
    if n:
        run.notes.append(f"fit shadow: Jev scored {n} leads")
    return n


def _resume_reason(rub, params, decision):
    ps = [p for p in (rub or {}).get("params") or [] if p.get("enabled") is not False and (params.get(p["key"]) or {}).get("score") is not None]
    if decision == "tailored":
        top = sorted(ps, key=lambda p: -float(p.get("weight") or 0) * params[p["key"]]["score"])[:2]
    else:
        top = sorted(ps, key=lambda p: float(p.get("weight") or 0) * params[p["key"]]["score"])[:2]
    return "; ".join(f'{p.get("name")} {params[p["key"]]["score"]}' for p in top)


def resume_decider(sb, llm, agents, settings, run):
    """Generic or Tailored for each lead at or above its stream's fit threshold. Picklist: generic | tailored | not_run | failed."""
    cfg = agents.get("resume_decider") or {}
    jev = getattr(llm, "jev", None)
    streams, docs, _, _, _, _ = load_context(sb)
    try:
        full = sb.select("job_streams", {"owner_id": "eq." + OWNER_ID, "select": "id,resume_rubric_version_id"})
    except Exception as e:
        run.notes.append(f"resume decider: needs schema resume-decider v1.0 ({str(e)[:80]})")
        return 0
    rmap = {x["id"]: x.get("resume_rubric_version_id") for x in full}
    for s in streams:
        s["resume_rubric_version_id"] = rmap.get(s["id"])
    rrubs = load_agent_rubrics(sb, streams, "resume_rubric_version_id")
    frubs = load_rubrics(sb, streams)
    limit = max(1, int(cfg.get("max_items") or 10))
    leads = sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "in.(fit_checked,promoted)", "resume_decision": "eq.not_run", "fit_score": "not.is.null",
                                "created_at": "gte." + iso(now_utc() - timedelta(days=21)),
                                "select": "id,title,company,location,raw_snippet,jd_text,job_stream_id,fit_score,easy_apply,resume_attempts",
                                "order": "fit_score.desc,created_at.desc", "limit": str(limit * 3)})
    leads = [l for l in leads if float(l.get("fit_score") or 0) >= stream_threshold(frubs, settings, l.get("job_stream_id"))][:limit]
    if not leads:
        run.notes.append("resume decider: nothing to decide")
        return 0
    try:
        targets = {(t.get("name") or "").strip().lower() for t in sb.select("target_companies", {"owner_id": "eq." + OWNER_ID, "select": "name"})}
    except Exception:
        targets = set()
    notes = career_notes_all(settings)
    margin = guard_value(cfg, "low_confidence_ask", 8)
    max_tries = int(guard_value(cfg, "max_attempts", 3) or 3)
    order = [(cfg.get("model") or {}).get("primary") or "jev", (cfg.get("model") or {}).get("fallback") or "gemini"]
    llm_r = AgentLLM(llm, cfg)
    n = 0
    for l in leads:
        s = next((x for x in streams if x["id"] == l.get("job_stream_id")), None)
        rv = rrubs.get(l.get("job_stream_id"))
        attempts = int(l.get("resume_attempts") or 0) + 1
        try:
            if not s or not rv:
                raise RuntimeError("no Resume Decider criteria for this stream")
            resume = resume_for(s, docs)
            if not resume:
                raise RuntimeError("no generic resume for this stream")
            rub = rv["rubric"]
            force_unknown = () if notes.strip() else ("hidden_experience",)
            state = jev_state(l, s, resume, notes, {"on_target_company_list": (l.get("company") or "").strip().lower() in targets, "easy_apply": bool(l.get("easy_apply"))})
            params = direct = None
            engine, last_err = None, None
            for eng in order:
                try:
                    if eng == "jev":
                        if not jev:
                            raise RuntimeError("no Jev key secret")
                        if getattr(jev, "blocked", None):
                            raise RuntimeError(jev.blocked)
                        qs = jev_rubric_questions(rub)
                        qs["direct"] = {"type": "choice", "instructions": "Should the candidate send the generic resume as it is, or tailor it for this job?",
                                        "criteria": {"generic": "the generic resume already fits this job well enough", "tailored": "the resume should be rewritten to fit this job"}}
                        ans = jev.evaluate(state, qs, timeout=int((cfg.get("model") or {}).get("timeout_s") or 60))
                        params = jev_param_scores(rub, ans, force_unknown)
                        direct = ans.get("direct") or {}
                        engine = "jev"
                    elif eng in ("gemini", "groq"):
                        system = RESUME_SYS + "\nScore each parameter 0-100 against its anchors. A higher score means more need to tailor.\n" + render_rubric(rub) + \
                                 '\n\nOutput format (fixed by the system): JSON only.\n{"params":{"<parameter key>":{"score":<0-100 or null>,"why":"<under 120 chars>"}},"direct":"generic|tailored"}'
                        out = llm_json_checked(llm_r, system, json.dumps(state), lambda o: isinstance(o, dict) and isinstance(o.get("params"), dict))
                        params = {}
                        for p in rub.get("params") or []:
                            if p.get("enabled") is False:
                                continue
                            v = out["params"].get(p["key"])
                            sc = None if p["key"] in force_unknown else _score(v)
                            params[p["key"]] = {"score": int(round(sc)) if sc is not None else None, "why": str((v or {}).get("why") if isinstance(v, dict) else "")[:160]}
                        d = str(out.get("direct") or "").lower()
                        direct = {"choice": d, "probabilities": {}} if d in ("generic", "tailored") else {}
                        engine = llm_r.label
                    else:
                        continue
                    break
                except Exception as e:
                    last_err = e
                    if eng == "jev" and jev and re.search(r"jev 40[23]|free tier users|insufficient", str(e), re.I):
                        jev.blocked = "jev unavailable this run: " + str(e)[:160]
                    log(f"resume decider: {eng} failed ({str(e)[:100]}); trying the next engine")
            if params is None:
                raise last_err or RuntimeError("no engine available")
            total, _ = compute_fit(rub, params)
            if total is None:
                raise RuntimeError("no parameter could be judged")
            thr = float(rub.get("threshold", 55))
            decision = "tailored" if total >= thr else "generic"
            dchoice = (direct or {}).get("choice")
            conf = (direct or {}).get("probabilities", {}).get(decision) if dchoice else None
            low = (margin is not None and abs(total - thr) < float(margin)) or (dchoice in ("generic", "tailored") and dchoice != decision)
            sb.update("leads", {"id": l["id"]}, {
                "resume_decision": decision, "resume_score": total, "resume_reason": _resume_reason(rub, params, decision)[:300],
                "resume_confidence": round(float(conf), 3) if conf is not None else None, "resume_low_confidence": bool(low), "resume_engine": engine,
                "resume_rubric_version_id": rv["id"], "resume_attempts": attempts, "resume_error": None, "resume_decided_at": iso(now_utc()),
                "resume_breakdown": {"params": params, "threshold": thr, "direct": direct, "rubric_version": rv.get("version"), "career_notes": bool(notes.strip())}})
            n += 1
        except Exception as e:
            if OUTAGE_RE.search(str(e)):
                # an outage, not this lead's fault: keep its tries, note why, stop for this run
                sb.update("leads", {"id": l["id"]}, {"resume_error": ("waiting: " + str(e))[:300]})
                run.errors.append({"stage": "resume_decider", "lead": l["id"], "outage": True, "error": str(e)[:240]})
                run.notes.append(f"resume decider: stopped, no engine available ({str(e)[:100]}); {len(leads) - n} left for the next pass")
                break
            patch = {"resume_attempts": attempts, "resume_error": str(e)[:300]}
            if attempts >= max_tries:
                patch["resume_decision"] = "failed"
            sb.update("leads", {"id": l["id"]}, patch)
            run.errors.append({"stage": "resume_decider", "lead": l["id"], "attempt": attempts, "error": str(e)[:240]})
    run.notes.append(f"resume decider: decided {n} of {len(leads)}" + (f" · jev ${jev.cost:.5f}" if jev and jev.cost else ""))
    run.model = ",".join(dict.fromkeys(x for x in ["jev" if jev and jev.calls else None, llm_r.label if llm_r.label != "-" else None] if x)) or "-"
    return n


# runner_calls_module_v1.0.py · v1.0 · 27 Oct 2026 · inserted into runner v1.0.18
# "My calls": every job you label (agent_evals, fit or resume_decider) is scored by Gemini AND Jev on the ACTIVE rubric, gates included.
# Results go to agent_evals.ai_results; the app compares them with your call. Never writes to leads.

CALLS_PER_PASS = 6


def _gemini_resume(llm_r, rub, state, force_unknown):
    system = RESUME_SYS + "\nScore each parameter 0-100 against its anchors. A higher score means more need to tailor.\n" + render_rubric(rub) + \
             '\n\nOutput format (fixed by the system): JSON only.\n{"params":{"<parameter key>":{"score":<0-100 or null>,"why":"<under 120 chars>"}},"direct":"generic|tailored"}'
    out = llm_json_checked(llm_r, system, json.dumps(state), lambda o: isinstance(o, dict) and isinstance(o.get("params"), dict))
    params = {}
    for p in rub.get("params") or []:
        if p.get("enabled") is False:
            continue
        v = out["params"].get(p["key"])
        sc = None if p["key"] in force_unknown else _score(v)
        params[p["key"]] = {"score": int(round(sc)) if sc is not None else None, "why": str((v or {}).get("why") if isinstance(v, dict) else "")[:160]}
    return params


def calls_check(sb, llm, agents, settings, run, jev=None, limit=CALLS_PER_PASS):
    fit_a, res_a = agents.get("fit") or {}, agents.get("resume_decider") or {}
    ids = [x for x in (fit_a.get("id"), res_a.get("id")) if x]
    if not ids:
        return 0
    cases = sb.select("agent_evals", {"owner_id": "eq." + OWNER_ID, "agent_id": "in.(" + ",".join(ids) + ")", "is_active": "eq.true",
                                      "expected_band": "not.is.null", "select": "id,agent_id,job_stream_id,input,expected_band,ai_results", "order": "created_at.desc", "limit": "400"})
    if not cases:
        return 0
    streams, docs, _, _, _, _ = load_context(sb)
    full = sb.select("job_streams", {"owner_id": "eq." + OWNER_ID, "select": "id,resume_rubric_version_id"})
    rmap = {x["id"]: x.get("resume_rubric_version_id") for x in full}
    for s in streams:
        s["resume_rubric_version_id"] = rmap.get(s["id"])
    frubs, rrubs = load_rubrics(sb, streams), load_agent_rubrics(sb, streams, "resume_rubric_version_id")
    todo = []
    for c in cases:
        rv = (frubs if c["agent_id"] == fit_a.get("id") else rrubs).get(c.get("job_stream_id"))
        if rv and (c.get("ai_results") or {}).get("rubric_version_id") != rv["id"]:
            todo.append((c, rv))
    if not todo:
        return 0
    llm_f, llm_r = AgentLLM(llm, fit_a), AgentLLM(llm, res_a)
    notes = career_notes_all(settings)
    n = 0
    for c, rv in todo[:limit]:
        s = next((x for x in streams if x["id"] == c.get("job_stream_id")), None)
        if not s:
            continue
        resume = resume_for(s, docs)
        lead = dict(c.get("input") or {})
        rub = rv.get("rubric") or {}
        thr = float(rub.get("threshold", 60 if c["agent_id"] == fit_a.get("id") else 55))
        out = {"rubric_version_id": rv["id"], "rubric_version": rv.get("version"), "threshold": thr, "at": iso(now_utc())}
        if c["agent_id"] == fit_a.get("id"):
            failed, gates = check_gates(rub, lead, jev)
            out.update(gates=gates, failed_gate=failed)
            if failed:
                out["gemini"] = out["jev"] = {"score": 0, "decision": "park", "why": "failed gate: " + failed}
            else:
                try:
                    res = score_items(llm_f, agents, s, resume, [lead], rv, run, "calls")
                    sc = res.get(0, (None, None))[0]
                    out["gemini"] = {"score": sc, "decision": None if sc is None else ("push" if sc >= thr else "park"), "params": (res.get(0, (None, {}))[1] or {}).get("params")}
                except Exception as e:
                    out["gemini"] = {"error": str(e)[:160]}
                if jev and not getattr(jev, "blocked", None):
                    try:
                        ans = jev.evaluate(jev_state(lead, s, resume), jev_rubric_questions(rub))
                        params = jev_param_scores(rub, ans)
                        sc, caps = apply_rule_params(rub, lead, params)
                        out["jev"] = {"score": sc, "decision": None if sc is None else ("push" if sc >= thr else "park"), "params": params, "caps": caps}
                    except Exception as e:
                        out["jev"] = {"error": str(e)[:160]}
        else:
            force_unknown = () if notes.strip() else ("hidden_experience",)
            state = jev_state(lead, s, resume, notes)
            try:
                params = _gemini_resume(llm_r, rub, state, force_unknown)
                sc, _ = compute_fit(rub, params)
                out["gemini"] = {"score": sc, "decision": None if sc is None else ("tailored" if sc >= thr else "generic"), "params": params}
            except Exception as e:
                out["gemini"] = {"error": str(e)[:160]}
            if jev and not getattr(jev, "blocked", None):
                try:
                    ans = jev.evaluate(state, jev_rubric_questions(rub))
                    params = jev_param_scores(rub, ans, force_unknown)
                    sc, _ = compute_fit(rub, params)
                    out["jev"] = {"score": sc, "decision": None if sc is None else ("tailored" if sc >= thr else "generic"), "params": params}
                except Exception as e:
                    out["jev"] = {"error": str(e)[:160]}
        sb.update("agent_evals", {"id": c["id"]}, {"ai_results": out})
        n += 1
    run.notes.append(f"my calls: {n} labelled jobs checked by Gemini and Jev" + (f", {len(todo) - n} left for later" if len(todo) > n else ""))
    return n


def jev_cycle(sb, llm, settings, agents):
    """Resume Decider (if due) then Fit shadow. One agent_runs row each."""
    failures = 0
    jev = getattr(llm, "jev", None)
    do_r, why_r = due(agents, "resume_decider", "cycle") if "resume_decider" in agents else (False, "no agents row (schema resume-decider v1.0 needed)")
    if do_r:
        r = Run(sb, "resume_decider", "jev")
        try:
            resume_decider(sb, llm, agents, settings, r)
        except Exception as e:
            r.errors.append({"stage": "resume_decider", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]}); failures += 1
        r.finish()
        mark(sb, agents, "resume_decider", True, "ran with errors" if r.errors else "ran")
    else:
        log(f"resume decider: {why_r}")
        mark(sb, agents, "resume_decider", False, "skipped: " + why_r)
    if jev and not getattr(jev, "blocked", None):
        r = Run(sb, "fit_shadow", "jev")
        try:
            fit_shadow(sb, jev, r)
        except Exception as e:
            r.errors.append({"stage": "fit_shadow", "error": str(e)[:300]})
        r.finish()
    r = Run(sb, "my_calls", "gemini+jev")
    try:
        if calls_check(sb, llm, agents, settings, r, jev=jev if jev and not getattr(jev, "blocked", None) else None) == 0:
            r.skipped = True
    except Exception as e:
        r.errors.append({"stage": "my_calls", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]})
    r.finish()
    if jev and jev.calls and not sb.dry:
        u = settings.get("jev_usage") or {}
        day = today_ist().isoformat() if hasattr(today_ist(), "isoformat") else str(today_ist())
        if u.get("date") != day:
            u = {"date": day, "calls": 0, "cost": 0.0}
        u["calls"] = int(u.get("calls", 0)) + jev.calls
        u["cost"] = round(float(u.get("cost", 0)) + jev.cost, 6)
        try:
            settings.set(jev_usage=u)
        except Exception as e:
            log(f"jev usage not saved: {e}")
    return failures


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
    if os.environ.get("GROQ_API_KEY"):
        q = Groq(os.environ["GROQ_API_KEY"], os.environ.get("GROQ_MODEL", ""))
        chk("groq", lambda: (q.json("Return JSON {\"ok\":true}", "ping"), q.model)[1])
    else:
        log("INFO groq: no GROQ_API_KEY secret, backup off")
    jv = make_jev()
    if jv:
        chk("jev", lambda: (jv.evaluate("The job title is Senior Product Manager.", {"pm": {"type": "boolean", "instructions": "Is this a product management job?"}}), f"{jv.route} {jv.model} ok, ${jv.cost:.6f}")[1])
    else:
        log("INFO jev: no Jev key (TYPESAFE_API_KEY / TYPEFACE_API_KEY / AI_GATEWAY_API_KEY), Resume Decider uses Gemini/Groq")
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
    ap.add_argument("mode", choices=["run", "nightly", "verify", "evals"])
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
        llm = LLM(Gemini("", model, dry=True))
        llm.jev = Jev("", dry=True)
        PROVIDERS.update(gemini=llm.gem, groq=llm.groq, jev=llm.jev)
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
        gem = Gemini(env["GEMINI_API_KEY"], model if model != "auto" else (settings.get("gemini_model") or "auto"),
                     remember=lambda m: settings.set(gemini_model=m))
        groq = Groq(os.environ["GROQ_API_KEY"], os.environ.get("GROQ_MODEL", "")) if os.environ.get("GROQ_API_KEY") else None
        log("groq backup: " + ("on" if groq else "off (no GROQ_API_KEY secret)"))
        for key, obj in (("gemini_backoff_until", gem), ("groq_backoff_until", groq)):
            bo = settings.get(key)
            try:
                if obj and bo and datetime.fromisoformat(bo) > now_utc():
                    obj.gave_up_429 = True
                    log(f"{key.split('_')[0]} paused after a recent 429 until {bo}")
            except Exception:
                pass
        llm = LLM(gem, groq)
        llm.jev = make_jev()
        log("jev: " + (f"on ({llm.jev.route}, {llm.jev.model}, key {llm.jev.key_name})" if llm.jev else "off (no Jev key secret)"))
        PROVIDERS.update(gemini=gem, groq=groq, jev=llm.jev)
        tg = Telegram(env["TELEGRAM_BOT_TOKEN"])
        gmail = Gmail(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"]).connect()
        fixtures = None

    failures = 0
    agents = load_agents(sb)
    try:
        mark_crashed(sb)
    except Exception as e:
        log(f"crash check failed: {e}")
    try:
        if args.mode == "evals":
            run_evals(sb, llm, agents, settings, max_runs=3)
        elif args.mode == "run":
            failures += cycle(sb, gmail, llm, tg, settings, model, agents, fixtures)
            try:
                run_evals(sb, llm, agents, settings)
            except Exception as e:
                log(f"evals failed: {e}")
            if nightly_due(settings):
                log("nightly due and not yet done today -> running it inside this run")
                failures += nightly(sb, gmail, llm, tg, settings, model, agents, fixtures)
        else:
            if not dry and not nightly_due(settings) and os.environ.get("FORCE_NIGHTLY") != "1":
                log("nightly already done today (a run after 21:36 IST did it); skipping. Set FORCE_NIGHTLY=1 to force.")
            else:
                failures += nightly(sb, gmail, llm, tg, settings, model, agents, fixtures)
    finally:
        try:
            if args.mode in ("run", "nightly"):
                health_alerts(sb, tg, settings, load_agents(sb) if not dry else agents)
        except Exception as e:
            log(f"agent alerts failed: {e}")
        try:
            record_usage(settings, llm, tg, dry)
        except Exception as e:
            log(f"usage bookkeeping failed: {e}")
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


def nightly_due(settings):
    """Due once per day: after 21:36 IST for today, or (if that slot was missed) before 21:36 for yesterday."""
    now = datetime.now(IST)
    catch_up = now.strftime("%H:%M") < NIGHTLY_AT
    target = now.date() - timedelta(days=1) if catch_up else now.date()
    last = settings.get("last_nightly_date") or ""
    if catch_up and in_quiet_hours(settings):
        return False  # yesterday's digest waits until quiet hours end
    return last < target.isoformat()


def record_usage(settings, llm, tg, dry):
    """Daily Gemini counter in user_settings.gemini_usage, plus one Telegram warning per day when the limit (429) is hit."""
    today = today_ist().isoformat()
    u = settings.get("gemini_usage") or {}
    if u.get("date") != today:
        u = {"date": today, "calls": 0, "n429": 0}
    gem, groq = llm.gem, llm.groq
    u["calls"] = int(u.get("calls", 0)) + gem.calls
    u["n429"] = int(u.get("n429", 0)) + gem.n429
    if gem.n429:
        u["last_429_at"] = datetime.now(IST).strftime("%H:%M")
    g = settings.get("groq_usage") or {}
    if g.get("date") != today:
        g = {"date": today, "calls": 0, "n429": 0}
    if groq:
        g["calls"] = int(g.get("calls", 0)) + groq.calls
        g["n429"] = int(g.get("n429", 0)) + groq.n429
    if dry:
        log(f"dry run: gemini usage would be {u}; groq {g}")
        return
    patch = {"gemini_usage": u, "groq_usage": g}
    if gem.n429:
        patch["gemini_backoff_until"] = iso(now_utc() + timedelta(minutes=60))
    if groq and groq.gave_up_429:
        patch["groq_backoff_until"] = iso(now_utc() + timedelta(minutes=60))
    settings.set(**patch)
    chat = settings.get("telegram_chat_id")
    # warn only when no brain is left (Gemini limited and Groq absent or limited too)
    both_down = u.get("n429", 0) > 0 and (groq is None or g.get("n429", 0) > 0 or llm.gave_up_429)
    if both_down and chat and settings.get("gemini_429_alert_date") != today and not in_quiet_hours(settings):
        tg.send(chat, f"⚠️ AI limit hit: Gemini at {u.get('last_429_at')} IST ({u['calls']} calls today)"
                      + ("" if groq is None else f", Groq too ({g.get('calls', 0)} calls)") + ". "
                      "Unread mails are kept and retried on later runs; Gemini resets around 12:30–13:30 IST.")
        settings.set(gemini_429_alert_date=today)


def usage_line(settings):
    u = settings.get("gemini_usage") or {}
    if u.get("date") != today_ist().isoformat():
        return "Gemini today: 0 calls"
    budget = settings.get("gemini_daily_budget")
    pct = f" ({round(100 * u['calls'] / int(budget))}% of budget {budget})" if budget else ""
    lim = f", limit hit {u['n429']}x (last {u.get('last_429_at')})" if u.get("n429") else ""
    g = settings.get("groq_usage") or {}
    gq = f" · Groq backup: {g.get('calls', 0)} calls" if g.get("date") == today_ist().isoformat() and g.get("calls") else ""
    return f"Gemini today: {u.get('calls', 0)} calls{pct}{lim}{gq}"


def source_and_fit(sb, gmail, llm, settings, model, agents, fixtures, phase):
    """Sourcer and Fit for one phase. One agent_runs row ('sourcer+fit'), as before."""
    failures = 0
    do_src, why_src = due(agents, "sourcer", phase)
    do_fit, why_fit = due(agents, "fit", phase)
    if not do_src and not do_fit:
        if phase == "cycle":
            log(f"sourcer: {why_src}; fit: {why_fit}")
            mark(sb, agents, "sourcer", False, "skipped: " + why_src)
            mark(sb, agents, "fit", False, "skipped: " + why_fit)
        return 0
    r = Run(sb, "sourcer+fit", model)
    llm_x = AgentLLM(llm, agents.get("sourcer"))
    llm_f = AgentLLM(llm, agents.get("fit"))
    for k, x in (("sourcer", llm_x), ("fit", llm_f)):
        if x.skipped:
            r.notes.append(f"{k}: skipped model {', '.join(x.skipped)}")
    new = []
    if do_src:
        try:
            new = sourcer(sb, gmail, llm_x, settings, r, dry_fixtures=fixtures, agents=agents, llm_fit=llm_f, do_fit=do_fit) or []
        except Exception as e:
            r.errors.append({"stage": "sourcer", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]}); failures += 1
    else:
        r.notes.append("sourcer: " + why_src)
    if do_fit:
        try:
            fit_backlog(sb, llm_f, agents, settings, r, exclude_keys={l.get("dedup_key") for l in new})
        except Exception as e:
            r.errors.append({"stage": "fit_backlog", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]}); failures += 1
        try:
            gate_sweep(sb, llm_f, agents, settings, r, jev=_jev_of(llm))
        except Exception as e:
            r.errors.append({"stage": "gate_sweep", "error": str(e)[:300], "trace": traceback.format_exc()[-800:]}); failures += 1
    try:
        career_notes_refresh(llm_f, settings, r)
    except Exception as e:
        r.errors.append({"stage": "career_notes", "error": str(e)[:300]})
    else:
        r.notes.append("fit: " + why_fit)
    r.model = "/".join(x for x in (llm_x.label, llm_f.label) if x != "-") or "-"
    r.finish(TokenSum(llm_x, llm_f))
    st = "ran with errors" if r.errors else "ran"
    mark(sb, agents, "sourcer", do_src, st if do_src else "skipped: " + why_src)
    mark(sb, agents, "fit", do_fit, st if do_fit else "skipped: " + why_fit)
    return failures


def cycle(sb, gmail, llm, tg, settings, model, agents, fixtures):
    failures = source_and_fit(sb, gmail, llm, settings, model, agents, fixtures, "cycle")
    try:
        failures += jev_cycle(sb, llm, settings, agents)
    except Exception as e:
        log(f"resume decider / fit shadow failed: {e}")
    do_n, why_n = due(agents, "notifier", "cycle")
    r = Run(sb, "notifier", "-")
    if do_n:
        try:
            notifier(sb, tg, settings, r)
        except Exception as e:
            r.errors.append({"stage": "notifier", "error": str(e)[:300]}); failures += 1
    else:
        r.notes.append("notifier: " + why_n + " (no pushes)")
        r.skipped = True
    r.finish()
    mark(sb, agents, "notifier", do_n, ("ran with errors" if r.errors else "ran") if do_n else "skipped: " + why_n)
    r = Run(sb, "replies", "-")   # your button taps are always processed
    try:
        replies(sb, tg, settings, r)
    except Exception as e:
        r.errors.append({"stage": "replies", "error": str(e)[:300]}); failures += 1
    r.finish()
    return failures


def nightly(sb, gmail, llm, tg, settings, model, agents=None, fixtures=None):
    agents = agents or {}
    failures = source_and_fit(sb, gmail, llm, settings, model, agents, fixtures, "nightly")  # only agents set to "nightly"
    do_s, why_s = due(agents, "status_sync", "nightly")
    r = Run(sb, "status_sync", model)
    llm_s = AgentLLM(llm, agents.get("status_sync"))
    if do_s:
        try:
            if gmail:
                status_sync(sb, gmail, llm_s, settings, r, agents)
            else:
                r.notes.append("dry run: status sync skipped (needs Gmail)")
        except Exception as e:
            r.errors.append({"stage": "status_sync", "error": str(e)[:300]}); failures += 1
    else:
        r.notes.append("status sync: " + why_s)
        r.skipped = True
    r.model = llm_s.label
    r.finish(llm_s)
    mark(sb, agents, "status_sync", do_s, ("ran with errors" if r.errors else "ran") if do_s else "skipped: " + why_s)
    do_w, why_w = due(agents, "sweeps", "nightly")
    r = Run(sb, "sweeps", "-")
    lines, waiting = [], 0
    if do_w:
        try:
            lines, waiting = sweeps(sb, settings, r)
        except Exception as e:
            r.errors.append({"stage": "sweeps", "error": str(e)[:300]}); failures += 1
    else:
        r.notes.append("sweeps: " + why_w)
        r.skipped = True
        waiting = len(sb.select("leads", {"owner_id": "eq." + OWNER_ID, "status": "eq.fit_checked", "select": "id"}))
    r.finish()
    mark(sb, agents, "sweeps", do_w, ("ran with errors" if r.errors else "ran") if do_w else "skipped: " + why_w)
    chat = settings.get("telegram_chat_id")
    actionable = [l for l in lines if not l.startswith("🗄")]   # parking old leads is housekeeping, not a reason to message
    if chat and actionable:   # v1.0.16: nothing to act on -> no message at all
        retry_n = len(settings.get("mail_retry") or [])
        off = [a["name"] for a in agents.values() if a.get("built_status") != "not_built" and not a.get("enabled")]
        digest = ("🌙 Nightly\n" + "\n".join(lines) + (f"\nLeads waiting in Inbox: {waiting}" if waiting else "")
                  + f"\n{usage_line(settings)}" + (f"\nMails waiting for retry: {retry_n}" if retry_n else "")
                  + (f"\nAgents off: {', '.join(off)}" if off else "") + f"\n{APP_URL}")
        tg.send(chat, digest)
    elif chat:
        log("nightly: nothing to act on, no digest sent")
    if not sb.dry:
        now = datetime.now(IST)
        done_for = now.date() if now.strftime("%H:%M") >= NIGHTLY_AT else now.date() - timedelta(days=1)
        settings.set(last_nightly_date=done_for.isoformat())
    return failures


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
            "noise_reasons": [{"id": "n1", "reason": "Title excluded"}, {"id": "n2", "reason": "Location not allowed"}, {"id": "n3", "reason": "Fit below threshold"}, {"id": "n4", "reason": "Older than 14 days"}, {"id": "n5", "reason": "Parked by you"}, {"id": "n6", "reason": "Failed mandatory gate"}],
            "leads": [{"dedup_key": "existing co|product manager|chennai", "email_message_id": "<old>", "status": "fit_checked", "job_stream_id": PM_STREAM, "job_board_id": "b-li", "source_platform": "linkedin", "fit_score": 70, "id": "lead-old", "title": "Product Manager", "company": "Existing Co", "location": "Chennai", "url": "https://x/1", "fit_breakdown": {"note": "old"}, "age_days": 3, "easy_apply": True, "created_at": iso(now_utc())}],
            "notifications": [], "applications": [{"id": "app-dry", "title": "Senior PM", "company": "Dry Co", "status": "applied", "url": "https://boards.example/dry"}], "interviews": [],
        }
        if os.environ.get("DRY_NO_AGENTS") != "1":
            rub = {"threshold": 60, "params": [
                {"key": "role_level", "name": "Role level", "weight": 25, "enabled": True, "description": "seniority", "anchors": {"high": "Senior", "mid": "PM", "low": "Junior"}, "cap": {"below": 30, "max": 40}, "if_unknown": "neutral"},
                {"key": "location", "name": "Location", "weight": 15, "enabled": True, "description": "city", "anchors": {"high": "Chennai", "mid": "Bengaluru", "low": "other"}, "cap": {"below": 30, "max": 50}, "if_unknown": "neutral"},
                {"key": "must_haves", "name": "Must-haves", "weight": 15, "enabled": True, "description": "JD", "anchors": {"high": "all", "mid": "most", "low": "none"}, "cap": None, "if_unknown": "skip"}]}
            self.tables["job_streams"][0]["fit_rubric_version_id"] = "rv1"
            self.tables["job_streams"][0]["resume_rubric_version_id"] = "rr1"
            rrub = {"threshold": 55, "params": [
                {"key": "must_have_gaps", "name": "Must-haves missing", "weight": 30, "enabled": True, "description": "top of resume", "anchors": {"high": "2+ missing", "mid": "1 missing", "low": "none missing"}, "cap": None, "if_unknown": "neutral"},
                {"key": "hidden_experience", "name": "Underplayed experience", "weight": 25, "enabled": True, "description": "career notes", "anchors": {"high": "clear", "mid": "some", "low": "none"}, "cap": None, "if_unknown": "skip"},
                {"key": "domain_shift", "name": "Domain shift", "weight": 15, "enabled": True, "description": "industry", "anchors": {"high": "different", "mid": "adjacent", "low": "same"}, "cap": None, "if_unknown": "neutral"}]}
            self.tables["fit_rubric_versions"] = [{"id": "rv1", "version": 1, "job_stream_id": PM_STREAM, "rubric": rub},
                                                  {"id": "rr1", "version": 1, "job_stream_id": PM_STREAM, "rubric": rrub}]
            self.tables["agent_prompt_versions"] = [
                {"id": "pv-src", "version": 1, "system_template": DEFAULT_TEMPLATE["sourcer"]},
                {"id": "pv-fit", "version": 1, "system_template": "You are a strict recruiter.\nParameters:\n{{rubric}}\nPark below {{threshold}}."},
                {"id": "pv-st", "version": 1, "system_template": DEFAULT_TEMPLATE["status_sync"]}]
            mk = lambda k, en=True, mode="every_run", pv=None, gr=None, mi=None: {"id": "ag-" + k, "key": k, "name": k, "enabled": en, "built_status": "live", "schedule": {"mode": mode},
                                                                              "model": {"primary": "gemini", "fallback": "groq"}, "active_prompt_version_id": pv, "guardrails": gr or [], "max_items": mi, "last_run_at": None}
            self.tables["agents"] = [mk("sourcer", pv="pv-src", mi=25), mk("fit", pv="pv-fit", mi=4, gr=[{"key": "max_calls", "on": True, "value": 6}, {"key": "require_basis", "on": True}]),
                                     mk("notifier"), mk("jd_fetcher", mi=20), dict(mk("resume_decider", mi=10, gr=[{"key": "low_confidence_ask", "on": True, "value": 8}, {"key": "max_attempts", "locked": True, "value": 3}]), model={"primary": "jev", "fallback": "gemini"}),
                                     mk("status_sync", mode="nightly", pv="pv-st", gr=[{"key": "min_confidence", "on": True, "value": 0.7}]), mk("sweeps", mode="nightly")]
            self.tables["agent_evals"] = [{"id": "ev1", "agent_id": "ag-fit", "job_stream_id": PM_STREAM, "is_active": True, "expected_band": "strong", "expected_min": 80, "expected_max": 100,
                                           "input": {"title": "Senior Product Manager", "company": "Acme", "location": "Chennai"}},
                                          {"id": "ev2", "agent_id": "ag-fit", "job_stream_id": PM_STREAM, "is_active": True, "expected_band": "no", "expected_min": 0, "expected_max": 39,
                                           "input": {"title": "Project Manager", "company": "Infra Co", "location": "Pune"}}]
            self.tables["agent_eval_runs"] = [{"id": "er1", "agent_id": "ag-fit", "status": "queued", "prompt_version_id": "pv-fit", "rubric_version_ids": {PM_STREAM: "rv1"}}]

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
