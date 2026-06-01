# REQUEST 08: Intraday Evidence and Runbook

## Goal

Connect intraday leader results to optional evidence/rise-reason collection without blocking ranking, snapshot creation, or Flask rendering.

## Constraints

- Keep existing morning board behavior intact.
- Keep `get_market_movers()` as fallback/test data.
- Do not use order, account, buy, sell, amend, cancel, balance, or trading endpoints.
- Evidence collection is optional and must fail open.
- No DB migration.

## Acceptance Criteria

- `src/evidence_service.py` can build evidence bundles directly from intraday leaders.
- Intraday collector optionally attaches rise reasons when enabled.
- Evidence failure still produces and stores an intraday snapshot.
- Intraday runtime settings are documented and have safe defaults.
- A runbook documents mock, WebSocket smoke test, Flask/Render enablement, fallbacks, and common errors.
- Integration tests cover mock intraday board generation through Flask render and evidence failure behavior.
