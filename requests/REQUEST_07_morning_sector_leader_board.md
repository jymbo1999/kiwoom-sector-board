# REQUEST 07 - Morning sector leader board

## Goal

Build the dashboard toward the user's daily morning workflow:

- At market open, show today's leading sectors/themes.
- For each sector, show up to the top 5 leading stocks.
- Keep the first screen focused on the real-time board rather than historical/sample sections.
- Prepare a daily snapshot path that can later be backed by Cloudflare R2.

## Scope

- Expand the local stock/theme universe beyond the current 12-stock MVP.
- Add a first-screen morning board table using current ranked sector and leader data.
- Keep existing news/rise-reason and history sections available but secondary.
- Add snapshot persistence that works locally and can optionally upload to R2 when credentials are configured.

## Non-goals

- No order, account, or trading functions.
- No database migration.
- No destructive deletion of existing user data.

## Verification

- `python -m py_compile app.py src/*.py`
- `pytest -q`
- Streamlit smoke check in live/mock mode
