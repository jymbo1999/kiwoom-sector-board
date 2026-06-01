# 인수인계 보고서 — 2026-06-01

## 프로젝트 개요

**kiwoom-sector-board** — 키움증권 REST/WebSocket API 기반 장중 주도섹터/대장주 대시보드.

- **절대 금지**: 주문·매수·매도·정정·취소·잔고·계좌 API. 시세 데이터(현재가·체결·호가)만 사용.
- **DB migration 금지**: 명시적 요청 없이 `sector_board/schema.py` 변경 금지.
- **기존 morning board 보호**: `get_morning_board_view_models()`, `collect_and_store()`, `/sector-board/` 라우트 보존.

---

## 현재 상태 (완료된 것)

### ✅ 테스트: 142 passed, 0 failed

### ✅ prod WebSocket 연결 성공 (실전키 기준)

| exchange | REG item | 수신 확인 |
|---|---|---|
| krx | `000660` | LOGIN=0, REG=0, REAL item=000660 수신 |
| nxt | `000660_NX` | LOGIN=0, REG=0, REAL item=000660_NX 수신 |
| sor | `000660_AL` | LOGIN=0, REG=0, REAL item=000660_AL 수신 |

LOGIN 응답에 `sor_yn=Y` 확인. suffix `_NX`/`_AL` **확정**.

### ✅ 구현된 핵심 모듈

| 파일 | 역할 |
|---|---|
| `src/kiwoom_auth.py` | 환경별 키 선택, token 발급, 8030 오류 안내 |
| `src/kiwoom_websocket.py` | WebSocket 클라이언트, normalize, 0B 필드 매핑 |
| `src/data_providers.py` | Mock / REST / WebSocket provider 추상화 |
| `src/universe_builder.py` | 종목 universe 생성 (pykrx 기반) |
| `src/intraday_state.py` | 장중 tick 상태 관리 |
| `src/intraday_snapshot_service.py` | 장중 스냅샷 생성 |
| `src/config.py` | 환경변수 로딩, KIWOOM_ENV 최우선 |
| `scripts/test_kiwoom_ws.py` | 단일 종목 WebSocket smoke test |
| `scripts/test_kiwoom_ws_bulk.py` | 대량 종목 bulk WebSocket smoke test |

---

## 환경변수 핵심 구조

```env
# 모의투자 키 (mockapi.kiwoom.com)
KIWOOM_MOCK_APP_KEY=
KIWOOM_MOCK_SECRET_KEY=

# 실전투자 키 (api.kiwoom.com) — KIWOOM_ENV=real/prod 시 필수
KIWOOM_REAL_APP_KEY=
KIWOOM_REAL_SECRET_KEY=

# 환경 선택 (최우선): mock | real | prod(real alias)
KIWOOM_ENV=mock

# provider: mock | rest | websocket
INTRADAY_PROVIDER=mock
INTRADAY_BOARD_ENABLED=false
```

**우선순위**: `KIWOOM_ENV` > `KIWOOM_USE_MOCK` > `USE_DUMMY_DATA`

---

## WebSocket 핵심 코드 구조

### `src/kiwoom_websocket.py` 주요 API

```python
# 종목 코드 포맷 (suffix 확정)
format_kiwoom_code("000660", "nxt")  # → "000660_NX"
format_kiwoom_code("000660", "sor")  # → "000660_AL"

# item 코드 분리
parse_item_code("000660_NX")
# → {"raw_code": "000660_NX", "base_code": "000660", "exchange": "nxt"}

# 부호 있는 숫자 파싱
parse_signed_int("+72000")   # → 72000
parse_signed_float("+0.70")  # → 0.70

# REAL 메시지 정규화 (전체 data 배열 처리)
rows = normalize_tick_rows(raw_json_str)
# rows[0] = {
#   item, raw_code, base_code, exchange, type, name,
#   trade_time, current_price, change_price, change_rate,
#   trade_volume, accumulated_volume, accumulated_trade_value,
#   best_ask(None), best_bid(None),  # TODO: 인덱스 미확인
#   raw_values  # 원본 numeric-key dict 보존
# }

# 0B 필드 인덱스 (prod 확정)
TYPE_0B_FIELD_MAP = {
    "20": "trade_time",             # 체결시간
    "10": "current_price",          # 현재가 (signed)
    "11": "change_price",           # 전일대비
    "12": "change_rate",            # 등락률 %
    "15": "trade_volume",           # 체결량
    "13": "accumulated_volume",     # 누적거래량
    "14": "accumulated_trade_value" # 누적거래대금
    # TODO: best_ask / best_bid 인덱스 미확인
}
```

### WebSocket 클라이언트 올바른 사용법

```python
# ✅ 올바른 방법 — iter_raw_messages() 사용 (단일·bulk 공통)
client = KiwoomWebSocketClient(ws_url, token)
async with client:
    async for msg in client.iter_raw_messages(
        codes,                        # 포맷된 코드 리스트
        listen_seconds=30.0,
        include_control_messages=True # LOGIN/REG/PING도 수신
    ):
        parsed = json.loads(msg.raw)
        trnm = parsed.get("trnm")
        # trnm == "LOGIN" → return_code 이미 검증됨 (0이 아니면 exception)
        # trnm == "REG"   → return_code 직접 확인 필요
        # trnm == "REAL"  → normalize_tick_rows(msg.raw) 로 처리

# ❌ 잘못된 패턴 (과거 bulk 버그)
rc = int(parsed.get("return_code", -1) or -1)
# → return_code=0(성공) 일 때 0 or -1 = -1 → 항상 FAILED
```

---

## smoke test 명령 (참조용)

```bash
# 단일 종목 SOR prod
KIWOOM_REAL_APP_KEY=<키> KIWOOM_REAL_SECRET_KEY=<시크릿> \
  .venv/bin/python scripts/test_kiwoom_ws.py \
    --provider websocket --kiwoom-env prod --exchange sor \
    --codes 000660 --listen-seconds 30 --max-messages 5

# bulk 5종목 NXT prod
KIWOOM_REAL_APP_KEY=<키> KIWOOM_REAL_SECRET_KEY=<시크릿> \
  .venv/bin/python scripts/test_kiwoom_ws_bulk.py \
    --provider websocket --kiwoom-env prod --exchange nxt \
    --codes-file requests/test_codes_5.txt \
    --listen-seconds 60 --summary-interval-seconds 10

# mock 로컬 확인
.venv/bin/python scripts/test_kiwoom_ws_bulk.py \
    --provider mock --exchange krx \
    --codes 000660,005930 --listen-seconds 5 --max-messages 5
```

---

## 다음 세션별 작업 범위

---

### 세션 A: 대량 실시간 수집기 구현

**목표**: 장중 300종목 SOR/NXT tick을 1분 버킷으로 집계해 `intraday_state`에 저장.

**전제 조건**: `scripts/test_kiwoom_ws_bulk.py --provider websocket`으로 prod 300종목 bulk 등록 및 tick 수신 성공 확인 후 진행.

**작업 범위**:
1. `src/intraday_state.py`에 1분 OHLCV 버킷 집계 로직 추가
   - `add_tick(base_code, exchange, price, volume, trade_time)` 메서드
   - 1분 버킷 완성 시 `IntraMinuteBucket` 생성
2. `src/data_providers.py`의 `KiwoomWebSocketRawProvider`를 streaming 방식으로 교체
   - `collect_raw_messages()` 대신 `stream_ticks()` async generator
   - tick 수신 → `normalize_tick_rows()` → `intraday_state.add_tick()`
3. universe 종목코드 + exchange suffix 조합 자동 적용
   - `data/universe_codes_300.txt` 사용
   - exchange 선택: sor (SOR 우선) 또는 nxt

**금지**: DB 저장, Flask UI, ranking 로직 연결. 이번 세션은 "tick 수집 파이프라인" 만.

**검증**:
```bash
.venv/bin/python -m pytest -q
# + prod 환경에서 300종목 30분 수집 후 intraday_state 상태 출력
```

---

### 세션 B: 섹터 집계 + ranking 연결

**목표**: 1분 버킷 기반 섹터별 등락률/거래대금 집계 → `rank_intraday_leaders()` 공급.

**전제 조건**: 세션 A 완료 후 `IntraMinuteBucket`이 `intraday_state`에 정상 적재되는 것 확인.

**작업 범위**:
1. `src/sector_ranker.py`의 `rank_intraday_leaders()` 입력을 버킷 집계 데이터로 교체
   - 기존 `rank_intraday_leaders()` 시그니처 유지
   - 내부에서 `intraday_state`의 최근 N분 버킷을 읽어 섹터별 가중평균 등락률 계산
2. `src/intraday_snapshot_service.py`에서 ranking 결과 → snapshot 생성 연결
3. `sector_board/collector.py`의 intraday collector가 위 서비스를 호출하게 연결

**금지**: DB schema 변경, Flask template 변경, morning board 코드 수정.

**검증**:
```bash
.venv/bin/python -m pytest -q
INTRADAY_BOARD_ENABLED=true INTRADAY_PROVIDER=websocket \
  .venv/bin/python -c "from sector_board.collector import collect_intraday; ..."
```

---

### 세션 C: best_ask / best_bid 호가 필드 확인 + Flask 장중 UI 연결

**목표**: 호가 데이터 수신 확인 및 장중 리더보드를 Flask `/sector-board/` 화면에 표시.

**전제 조건**: 세션 A + B 완료 후 ranking 결과가 snapshot에 정상 저장되는 것 확인.

**작업 범위**:
1. **best_ask / best_bid 필드 인덱스 확인**
   - prod 환경에서 0B REAL 메시지의 `raw_values` 전체 필드 출력
   - `TYPE_0B_FIELD_MAP`에 확인된 호가 인덱스 추가
   - `normalize_tick_rows()` 반환에 `best_ask`, `best_bid` 채우기
2. **Flask 장중 UI 연결**
   - `sector_board/blueprint.py`: snapshot `board_type=intraday` 시 장중 컨텍스트 렌더링
   - `sector_board/templates/sector_board/index.html`: 장중 배지/경고 표시
   - 기존 morning board 렌더링 경로 보존

**금지**: DB schema 변경, 주문 기능, morning board 기존 라우트 제거.

**검증**:
```bash
.venv/bin/python -m pytest -q
INTRADAY_BOARD_ENABLED=true INTRADAY_PROVIDER=mock flask run
# → /sector-board/ 에서 intraday 배지 확인
```

---

## 필수 확인 명령 (세션 시작 전 항상 실행)

```bash
# 1. AGENTS.md 확인
cat AGENTS.md

# 2. 현재 상태
git status --short
git diff --stat

# 3. 테스트 통과 확인
.venv/bin/python -m pytest -q

# 4. Runbook
cat docs/INTRADAY_LEADER_BOARD_RUNBOOK.md
```

---

## 알려진 미확인 사항

| 항목 | 상태 |
|---|---|
| `best_ask` / `best_bid` 0B 필드 인덱스 | ❌ 미확인 — prod REAL raw_values 전체 출력으로 확인 필요 |
| 300종목 SOR bulk prod 실측 tick 수신 | ❌ 미실행 — 세션 A 시작 전 bulk smoke test 필요 |
| 모의투자 환경 WebSocket 시세 지원 범위 | ⚠️ KRX만 지원 가능 — prod 키 없이는 NXT/SOR 미검증 |

## Production DB migration needed: **NO**
