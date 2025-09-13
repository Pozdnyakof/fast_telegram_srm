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
		- Optional: `TIMEZONE=Europe/Moscow`, `LOG_LEVEL=INFO`, `SENTRY_DSN=`, `LOG_JOINS_WITHOUT_INVITE=false`

4. Run the bot from the project root to avoid import issues:
	- `python -m app.main`

Notes
- Do NOT create a file named `logging.py` in `app/` (it shadows Python's stdlib logging).
- If you see `BOT_TOKEN is not set`, ensure `.env` is present or env vars are exported in your shell.

### Testing that rows are appended
- The handler writes to Google Sheets only when a user joins via an invite link by default.
- Create a channel invite link with a name (e.g., "Promo A"), then join the channel using that link from a test account.
- If you want to log all joins (even without invite links), set `LOG_JOINS_WITHOUT_INVITE=true` in your `.env`.
- Check logs:
	- You should see `Appending join event to sheet='...'...` followed by `Appended join event: sheet='...'`.
	- If you see `Skipping chat_member: no invite_link`, enable the flag above or join with an invite link.