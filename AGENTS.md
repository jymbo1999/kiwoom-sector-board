# AGENTS.md

## Project Overview

This repository is `kiwoom-sector-board`, a sector and market-leader stock dashboard project.

The project currently has two display layers:

1. `app.py`
   - Local Streamlit dashboard entry point.
   - Uses `src/market_data.py`, `src/dashboard_components.py`, and `src/snapshot_service.py`.

2. `sector_board/*`
   - Flask Blueprint + DB layer for Render deployment.
   - Reads the latest DB snapshot and renders `sector_board/templates/sector_board/index.html`.

The current production behavior is closer to a previous-day, KRX-based morning briefing than to a true intraday leaderboard.

The target direction is documented in:

- `docs/INTRADAY_LEADER_BOARD_PLAN.md`

Always read this document before making intraday leaderboard-related changes.

---

## Core Goal

Add an intraday sector and market-leader stock board without breaking the existing morning snapshot board.

Target architecture:

1. Universe Layer
2. Data Provider Layer
3. Intraday State Layer
4. Ranking Engine
5. Snapshot/Delivery Layer
6. Evidence/Rise Reason Layer

The key principle is that data providers should be replaceable.

The same ranking/snapshot contract should work with:

- KRX delayed/EOD provider
- Kiwoom REST polling provider
- Kiwoom WebSocket provider
- Mock provider
- Fallback provider

---

## Hard Rules

### Do Not Break Existing Morning Board

Do not remove or break:

- `get_morning_board_view_models()`
- `build_morning_snapshot_payload()`
- `sector_board/collector.collect_and_store()`
- Existing `/sector-board/` rendering
- Existing KRX fallback behavior
- Existing mock fallback behavior

New intraday behavior must be added in parallel.

---

### No Trading or Order APIs

This project is for market data display only.

Never add or call:

- Buy order API
- Sell order API
- Order correction API
- Order cancellation API
- Balance inquiry logic unless explicitly requested
- Account trading logic

Kiwoom integration should be limited to quote, current-price, tick, and orderbook-style market data.

---

### Avoid DB Migration Unless Explicitly Requested

Do not change the production DB schema unless explicitly requested.

Do not modify:

- `sector_board/schema.py`

For the V1 intraday board, use the existing snapshot upsert structure and optional JSON fields.

If a schema change seems necessary, stop and report why before changing it.

---

### Preserve Existing Public Routes

Do not remove or rename:

- `GET /sector-board/`
- `POST /sector-board/refresh`
- `GET /sector-board/api/snapshot`
- `GET /sector-board/health`
- `GET /sector-board/debug`

---

## Preferred Implementation Pattern

When adding intraday features, prefer new modules and facade functions.

Recommended files:

- `src/universe_builder.py`
- `src/data_providers.py` or `src/quote_provider.py`
- `src/intraday_state.py`
- `src/intraday_snapshot_service.py`

Modify existing files carefully:

- `src/market_data.py`
  - Keep the existing morning facade.
  - Add the intraday facade separately.

- `src/sector_ranker.py`
  - Keep the existing `rank_sectors()` and `rank_sectors_krx()`.
  - Add `rank_intraday_leaders()` separately.

- `sector_board/collector.py`
  - Keep the existing `collect_and_store()`.
  - Add an intraday collector separately.

- `sector_board/blueprint.py`
  - Keep the existing rendering.
  - Add intraday context only when the snapshot indicates intraday mode.

---

## Intraday Snapshot Contract

The intraday snapshot payload should follow this general structure:

```python
{
    "summary": {
        "board_type": "intraday",
        "data_mode": "mock/rest/websocket/fallback",
        "provider_mode": "...",
        "generated_at": "...",
        "freshness_seconds": 0,
        "universe_count": 0,
        "selected_sector_count": 0,
        "selected_leader_count": 0,
    },
    "themes": [],
    "leaders": [],
    "rank_events": [],
    "universe": {},
    "provider_status": {},
}
```

Existing `themes` and `leaders` keys should remain compatible with the old template as much as possible.

New keys should be optional.

---

## Environment Variables

Use environment variables for intraday behavior.

Recommended defaults:

```text
INTRADAY_BOARD_ENABLED=false
INTRADAY_PROVIDER=mock
INTRADAY_POLL_SECONDS=60
INTRADAY_MAX_CODES=300

UNIVERSE_MIN_MARKET_CAP=500000000000
UNIVERSE_MIN_TRADE_VALUE=0

INTRADAY_EVIDENCE_ENABLED=false
INTRADAY_EVIDENCE_LIMIT=10

KIWOOM_ENV=mock
```

The user already has the Kiwoom app key and secret in `.env`.

Do not print secrets.

Do not commit `.env`.

---

## Kiwoom Notes

Kiwoom keys may currently be for simulated trading.

That is acceptable because this project only needs market data display.

However, simulated trading mode may not support all markets or real-time behavior.

Build the provider layer so that mock, REST, and WebSocket providers can be swapped without changing the ranking or UI code.

---

## Testing Rules

After changes, run:

```bash
python -m py_compile app.py src/*.py sector_board/*.py
pytest -q
git diff --check
git status --short
```

When external APIs are involved, tests should use mock data by default.

Do not require a real Kiwoom connection for normal pytest runs.

WebSocket smoke tests should live under `scripts/` and be run manually.

---

## Reporting Format

After each task, report:

- Success/failure
- Files changed
- Commands run
- Test results
- Existing behavior impact
- Production DB migration needed: YES/NO
- Remaining TODO

---

## 6. Codex 단계별 프롬프트 앞에 붙일 공통 헤더

앞으로 6단계 프롬프트마다 아래 공통 헤더를 맨 위에 붙이세요.

```text
작업 시작 전에 반드시 아래 두 문서를 먼저 읽으세요.

1. AGENTS.md
2. docs/INTRADAY_LEADER_BOARD_PLAN.md

이 작업은 장중 주도섹터/대장주 리더보드 전환 계획의 일부입니다.

중요 원칙:
- 기존 morning board 기능을 깨지 마세요.
- 기존 Flask/Render `/sector-board/` 흐름을 보존하세요.
- 주문/매수/매도/정정/취소/잔고 관련 API는 절대 추가하거나 호출하지 마세요.
- 실거래 기능은 만들지 않습니다. 필요한 것은 가격/체결/호가 등 시세 데이터뿐입니다.
- DB migration은 명시적으로 요청받기 전까지 수행하지 마세요.
- WebSocket 또는 Kiwoom API 연결이 실패해도 mock provider/fallback으로 테스트 가능해야 합니다.
- 작업 후 py_compile, pytest, git diff --check를 실행하고 결과를 보고하세요.
```