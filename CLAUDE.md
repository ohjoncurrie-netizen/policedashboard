# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Activate virtualenv (always required)
source venv/bin/activate

# Run dev server
python app.py

# Production runs via gunicorn + systemd
systemctl restart montanablotter
systemctl status montanablotter

# Run a one-off worker script
python email_worker.py
python resend_bounced.py
python morning_briefing.py
```

## Database

SQLite at `/root/montanablotter/blotter.db`. Schema migrations run automatically at startup via `init_db.migrate()` (called in `app.py` line ~19). To add a migration, append to the `migrate()` function in `init_db.py` using `ALTER TABLE ... ADD COLUMN` wrapped in `try/except`.

```bash
# Inspect live DB
sqlite3 blotter.db ".tables"
sqlite3 blotter.db "SELECT * FROM posts ORDER BY created_at DESC LIMIT 5;"
```

## Architecture

**Ingestion pipeline:**
`email_worker.py` (runs every 15 min via cron) → fetches PDFs/text from IONOS IMAP → `processor.py` → `pdf_parser.py` (OCR fallback via pytesseract) → `summarizer.py` (Claude API) → writes to `blotters`, `records`, `posts` tables.

**Key data flow:**
1. Blotter arrives (PDF email or manual upload)
2. `processor.process_new_blotter(filepath)` → parses incidents → calls `summarizer.generate_posts(blotter_id)`
3. Summarizer detects agency type (sheriff/police), calls Claude API, writes `posts` rows
4. Morning briefing cron emails digest to subscribers daily at 7am

**Email sending:**
- Inbound blotters: IONOS IMAP (`config.IMAP_SERVER`)
- Outbound to sheriffs/PDs: Gmail SMTP (`config.SMTP_USER` / `config.SMTP_PASSWORD`)
- `resend_bounced.py` scans IONOS inbox for bounces and resends via Gmail

**Admin panel** (`/admin/*`, all `@login_required`):
- Dashboard, PDF upload, blotter management, bulk email to agencies, blog CMS, analytics
- `emailed_agencies` table prevents duplicate outreach; UI shows green "Sent" badge

**Public pages:**
- `/` — paginated activity feed with calendar, search, filters
- `/arrests` — filtered arrest log
- `/jail-rosters` — all 56 county jail roster links
- `/laws` — Montana statute reference (criminal, traffic, hunting, general)
- `/blog`, `/blog/<slug>` — CMS blog
- `/api/posts`, `/api/counties`, `/api/agencies` — public JSON API

## Config

Credentials live in `config.py` (gitignored). Never commit it. Key vars:
- `EMAIL_USER` / `EMAIL_PASSWORD` — IONOS account (inbound IMAP only)
- `SMTP_USER` / `SMTP_PASSWORD` — Gmail app password (outbound sends)
- `ANTHROPIC_API_KEY` — Claude API for blotter summarization
- `DB_PATH`, `UPLOAD_DIR`, `LOG_FILE`

## Cron Jobs

See `crontab.txt`. Main entries:
- Every 15 min: `email_worker.py` (fetch blotters)
- Daily 7am: `morning_briefing.py` (subscriber digest)
- Daily 2am: `backup_db.sh`

## Sheriff / PD Email Lists

Hardcoded in the `admin_emails` route in `app.py` (`SHERIFFS_EMAILS` + `POLICE_EMAILS` dicts). Daniels County is missing — URL was invalid when collected. Add new addresses there directly.
