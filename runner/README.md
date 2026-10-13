# Job Application Driver · runner v1.0 (13 Oct 2026)

The always-on part of the Job Application Driver. GitHub Actions boots a small Linux machine every 15 minutes and once nightly; no laptop, no domain, no mail forwarding.

Loop (every 15 min): Gmail (IMAP, app password) → job-alert mails → Gemini extracts jobs → filters (title / location / age) → Gemini fit score against the stream's generic resume → Supabase `leads` → Telegram push with buttons (Apply generic · Tailor · Park · Remind tonight · Open) → button replies create applications, park leads, queue tailoring.

Nightly 21:30 IST: mails from companies you applied to → rejection / interview / offer classified, verbatim text stored → sweeps (stale, ghosted, debrief pending, overdue next actions, alerts with no leads in 7 days, old leads parked) → one digest message.

Secrets (repo → Settings → Secrets and variables → Actions → New repository secret):
GMAIL_USER, GMAIL_APP_PASSWORD, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, SUPABASE_SERVICE_KEY. Optional variable: GEMINI_MODEL (default auto = newest free Flash model).

First run: Actions → job-driver → Run workflow → mode `verify`. It checks every secret, links your Telegram chat (send the bot one message first) and sends a test message.

Dry run: `python runner/job_driver_runner.py run --dry-run` (fixtures, fake LLM, writes nothing). Every push to `runner/` runs this automatically.

Known limits: scheduled runs can lag a few minutes at busy hours; GitHub pauses schedules in a repo with no commits for 60 days (any push re-enables them); Gemini free tier rate limits are handled with retries.
