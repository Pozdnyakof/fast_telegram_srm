# fast_telegram_srm

## How to run (Windows, PowerShell)

1. Create and activate venv (optional):
	- If not created yet: `python -m venv .venv`
	- Activate: `.venv\\Scripts\\Activate.ps1`

2. Install dependencies:
	- `pip install -r requirements.txt`

3. Configure environment:
	- Copy `.env.example` to `.env` and fill:
	  - `BOT_TOKEN=...`
	  - `GOOGLE_SPREADSHEET_ID=...`
	  - `GOOGLE_SERVICE_ACCOUNT_JSON=` one of: file path, raw JSON, or base64-encoded JSON
	  - Optional: `TIMEZONE=Europe/Moscow`, `LOG_LEVEL=INFO`, `SENTRY_DSN=`

4. Run the bot from the project root to avoid import issues:
	- `python -m app.main`

Notes
- Do NOT create a file named `logging.py` in `app/` (it shadows Python's stdlib logging).
- If you see `BOT_TOKEN is not set`, ensure `.env` is present or env vars are exported in your shell.