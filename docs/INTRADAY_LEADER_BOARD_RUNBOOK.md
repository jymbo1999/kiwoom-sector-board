# Intraday Leader Board Runbook

> **대상 독자**: 이 프로젝트를 처음 접하는 개발자, 또는 새 세션을 시작한 AI 에이전트.  
> 이 문서만 읽으면 로컬에서 mock 실행 → prod smoke → Flask 화면까지 진행할 수 있다.

---

## 1. 프로젝트 목적

**장중 주도섹터 + 섹터별 대장주를 자동 탐지해 대시보드로 표시한다.**

- 08:00부터 SOR(통합시세) WebSocket 으로 150~200종목 실시간 체결을 수신한다.
- 1분 단위로 거래대금 증가량과 등락률을 집계한다.
- 섹터별로 가장 강하게 움직이는 섹터를 찾고, 각 섹터 안에서 대장주/2등주/3등주를 뽑는다.
- 최종 화면: 주도섹터 Top 5 + 섹터별 대장주 Top 5.

---

## 2. v1 Morning Board vs v2 Intraday Board

| 항목 | v1 Morning Board | v2 Intraday Board |
|---|---|---|
| 데이터 소스 | KRX EOD (전일 종가) | Kiwoom WebSocket SOR 실시간 체결 |
| 수집 시점 | 매일 04:00 KST (cron) | 08:00~18:00 장중, smoke script 실행 중 |
| 집계 단위 | 종가 기준 하루 | 1분 OHLC + 거래대금 delta |
| Flask route | `GET /sector-board/` | `GET /sector-board/intraday` |
| DB 연동 | PostgreSQL (Render) | 없음 — JSONL 파일 기반 (A안) |
| 상태 | **운영 중** (건드리지 말 것) | **v2 완성 — smoke/화면 연결 완료** |

v1 은 절대 깨지 않는다. v2 는 v1 과 완전히 독립된 route, module, template 을 사용한다.

---

## 3. 아키텍처 개요 (v2 파이프라인)

```
[Kiwoom WebSocket SOR]
         │  REAL 0B 메시지 (주식체결)
         ▼
  normalize_tick_rows()          — src/kiwoom_websocket.py
         │  row dict 리스트
         ▼
  IntradayTickAggregator          — src/intraday_tick_aggregator.py
         │  LatestTickState + MinuteBucket (1분 OHLC + 거래대금 delta)
         ▼
  aggregate_sector_minutes()      — src/intraday_sector_aggregator.py
         │  sector_map.json 과 결합 → SectorMinuteSummary 리스트
         ▼
  rank_intraday_leaders()         — src/intraday_leader_ranker.py
         │  IntradaySectorLeaderView 리스트 (대장/2등주/3등주 badge)
         ▼
  IntradaySnapshotService         — src/intraday_snapshot_service.py
         │  IntradaySnapshot (status: empty/warming/ready)
         ▼
  run_intraday_snapshot_smoke.py  — scripts/
         │  --dump-snapshot-jsonl
         ▼
  logs/intraday_snapshot_*.jsonl  — 파일 기반 영속
         │  가장 최신 파일의 마지막 줄
         ▼
  intraday_reader.py              — sector_board/
         │  build_intraday_view()
         ▼
  GET /sector-board/intraday      — Flask Blueprint
```

---

## 4. 환경 설정

### 4-1. .env 파일

```env
# 모의투자 키 (mockapi.kiwoom.com)
KIWOOM_MOCK_APP_KEY=<모의투자 App Key>
KIWOOM_MOCK_SECRET_KEY=<모의투자 Secret Key>

# 실전투자 키 (api.kiwoom.com) — prod/real 환경 필수
KIWOOM_REAL_APP_KEY=<실전투자 App Key>
KIWOOM_REAL_SECRET_KEY=<실전투자 Secret Key>

# 환경 선택 — 기본값은 mock (Morning Board 보존)
KIWOOM_ENV=mock

# v1 Morning Board 설정 (건드리지 않는다)
USE_KRX_DATA=true
SECTOR_BOARD_DATABASE_URL=<Render PostgreSQL URL>
```

### 4-2. Kiwoom 환경별 키 선택

| `KIWOOM_ENV` | REST host | 사용 키 |
|---|---|---|
| `mock` | `https://mockapi.kiwoom.com` | `KIWOOM_MOCK_APP_KEY` |
| `real` / `prod` | `https://api.kiwoom.com` | `KIWOOM_REAL_APP_KEY` (**필수**) |

> **오류 8030**: "투자구분(실전/모의)이 달라서 Appkey를 사용할 수가 없습니다."  
> 키 자체가 틀린 것이 아니라 키 종류와 서버 환경이 불일치한 것이다.  
> → `KIWOOM_ENV=prod` 인데 모의투자 키를 넣으면 8030 발생. 실전 키로 교체한다.

### 4-3. Exchange suffix (확정 2026-06-01)

| `--exchange` | REG item 예시 | 의미 |
|---|---|---|
| `krx` | `000660` | KRX 정규시장 |
| `nxt` | `000660_NX` | NXT (넥스트레이드) |
| `sor` | `000660_AL` | SOR/통합 ← **v2 기본** |

---

## 5. Universe 및 sector_map 생성

### 5-1. 현재 운영 파일 (이미 생성 완료)

```
data/universe_codes_150.txt   — 150종목 코드 (SOR 운영용)
data/sector_map.json          — 150종목 → 27개 섹터 매핑
data/theme_map.csv            — 원본 테마 데이터 (code, name, theme1, theme2, theme3)
```

### 5-2. universe 파일 생성 스크립트

```bash
# 템플릿 CSV 생성 (처음 시작할 때)
.venv/bin/python scripts/build_intraday_universe.py \
  --write-template data/my_universe.csv

# theme_map.csv 로 150종목 운영 파일 생성 (기본)
.venv/bin/python scripts/build_intraday_universe.py \
  --input data/theme_map.csv \
  --limit 150

# 200종목 파일 생성
.venv/bin/python scripts/build_intraday_universe.py \
  --input data/theme_map.csv \
  --limit 200 \
  --output-codes data/universe_codes_200.txt \
  --output-sector-map data/sector_map.json

# dry-run (파일 안 쓰고 미리 보기)
.venv/bin/python scripts/build_intraday_universe.py \
  --input data/theme_map.csv --limit 150 --dry-run
```

### 5-3. 입력 CSV 형식

```csv
code,name,market_cap,sector
005930,삼성전자,500000000000000,반도체
000660,SK하이닉스,100000000000000,반도체
042660,한화오션,10000000000000,조선
```

- `market_cap` 있으면 내림차순 정렬 후 limit 적용
- `sector` 없고 `theme1`/`theme2`/`theme3` 있으면 자동 감지 (기존 `data/theme_map.csv` 호환)
- 우선주(`우` 접미사), ETF, SPAC 은 기본 자동 제외

### 5-4. sector_map.json 형식

```json
{
  "005930": ["반도체"],
  "000660": ["반도체"],
  "042660": ["조선"]
}
```

- 코드 key: 6자리 zero-padded 문자열
- value: 섹터명 리스트 (multi-sector 허용)
- `--sector-map-file` 없이 smoke script 실행 시 에러. 반드시 지정하거나 `--allow-fallback-sector-map` 추가

---

## 6. Snapshot Smoke 실행법

### 6-1. mock 실행 (API 키 불필요, 로컬 검증)

```bash
.venv/bin/python scripts/run_intraday_snapshot_smoke.py \
  --provider mock \
  --exchange sor \
  --codes-file data/universe_codes_150.txt \
  --sector-map-file data/sector_map.json \
  --listen-seconds 30 \
  --summary-interval-seconds 5
```

### 6-2. prod SOR 150종목 실행 (장중 08:00~18:00 KST)

```bash
KIWOOM_REAL_APP_KEY=<키> KIWOOM_REAL_SECRET_KEY=<시크릿> \
.venv/bin/python scripts/run_intraday_snapshot_smoke.py \
  --provider websocket \
  --kiwoom-env prod \
  --exchange sor \
  --codes-file data/universe_codes_150.txt \
  --sector-map-file data/sector_map.json \
  --listen-seconds 300 \
  --summary-interval-seconds 30 \
  --dump-snapshot-jsonl
```

### 6-3. dry-run (연결 없이 계획 확인)

```bash
.venv/bin/python scripts/run_intraday_snapshot_smoke.py \
  --dry-run \
  --exchange sor \
  --codes-file data/universe_codes_150.txt \
  --sector-map-file data/sector_map.json
```

### 6-4. 콘솔 출력 예시

```
[smoke] ===== startup =====
  provider=websocket  exchange=sor  codes=150
  sector_map=150종목  listen=300.0s  interval=30.0s

[smoke] ===== 13:45 snapshot =====
status=ready minute=1345 latest=150 unmapped=0 buckets=300 sectors=5 raw_rows=8400 ignored=0 no_tick=0/150

1. 반도체  score=108110549679  trade=1.1천억  avg_rate=+2.31%  rising=0.92  active=13
   대장  005930  close=81200  rate=+1.82%  1m_tv=88.4억
   2등주 000660  close=182000  rate=+3.20%  1m_tv=73.6억
   3등주 042700  close=32100  rate=+5.11%  1m_tv=23.2억

[smoke] ===== FINAL SUMMARY =====
  total_messages=12834
  total_ingested_rows=12833
  total_snapshots=10
  final_status=ready
  final_sector_count=5
  elapsed=300.0s
  rows_per_sec=42.8

  snapshot JSONL → logs/intraday_snapshot_20260601_134500.jsonl
```

---

## 7. JSONL dump 위치

```
logs/intraday_snapshot_YYYYMMDD_HHMMSS.jsonl
```

- `--dump-snapshot-jsonl` 옵션을 추가하면 자동 생성
- 경로 직접 지정: `--dump-snapshot-jsonl /tmp/my.jsonl`
- `logs/intraday_snapshot_*.jsonl` 은 `.gitignore` 에 포함되어 커밋되지 않는다
- token/appkey/secretkey 는 저장 전 자동 제거됨
- Flask `/sector-board/intraday` 화면이 이 파일의 마지막 줄을 자동으로 읽어 표시한다

---

## 8. Flask 화면 실행법

### 8-1. 로컬 실행

```bash
# smoke script 로 JSONL 먼저 생성한 뒤
flask --app "sector_board:create_app()" run
# → http://localhost:5000/sector-board/intraday
```

또는 `app.py` 가 있으면:

```bash
FLASK_APP=sector_board FLASK_DEBUG=1 flask run
```

### 8-2. URL 목록

| URL | 내용 |
|---|---|
| `GET /sector-board/` | v1 Morning Board (기존) |
| `GET /sector-board/intraday` | **v2 장중 리더보드 (신규)** |
| `GET /sector-board/api/snapshot` | v1 snapshot JSON API |
| `GET /sector-board/health` | 헬스체크 |

### 8-3. 화면 데이터 공급 방식 (A안)

```
logs/intraday_snapshot_*.jsonl
  └→ 파일명 사전순 가장 마지막 파일
       └→ 비어 있지 않은 마지막 줄 (JSON)
            └→ /sector-board/intraday 렌더링
```

- JSONL 파일이 없으면 `empty` 상태 표시 (화면이 죽지 않는다)
- smoke script 가 실행될 때마다 자동 반영된다 (새로고침으로 확인)

### 8-4. 앱 설정 (Flask config)

```python
# JSONL 경로 오버라이드 (테스트용)
app.config["INTRADAY_LOGS_DIR"] = "/path/to/logs"
```

---

## 9. 200종목 제한과 150종목 권장

### 9-1. 200종목 제한 (Kiwoom WebSocket 확정)

Kiwoom WebSocket 은 **세션 단위 총 등록 상한 200종목**이다.

| 실험 | 결과 |
|---|---|
| SOR 50종목 | ✅ 안정 |
| SOR 100종목 | ✅ 안정 (180초, rows/sec=226) |
| SOR 300종목 단일 REG | ❌ `return_code=105118` (그룹당 200 초과) |
| SOR 300종목 분할(200+100) | ❌ group 2 `return_code=105115` (세션 총 200 초과) |
| SOR 200종목 | ✅ REG 성공, 일부 세션에서 1000 Bye 조기 종료 |

`run_intraday_snapshot_smoke.py` 와 `test_kiwoom_ws_bulk.py` 는 200종목 초과 시 즉시 차단한다:

```
[smoke] ERROR: formatted_code_count=201 > max_total_realtime_codes=200.
  --codes-file 를 줄이거나 --allow-fallback-sector-map 등을 확인하세요.
```

### 9-2. 150종목 권장 이유

- 200종목은 REG 성공하지만 **서버 1000 Bye 조기 종료 사례**가 있었다
- 150종목은 100종목과 동일한 안정성 프로파일로 판단된다
- theme_map.csv 가 150종목을 커버하므로 sector_map 매핑이 100% 된다
- **v2 기본값**: `data/universe_codes_150.txt`

200종목이 반복 종료될 경우 150종목 파일로 교체한다:

```bash
.venv/bin/python scripts/build_intraday_universe.py \
  --input data/theme_map.csv --limit 150
```

---

## 10. 1000 Bye 의미

```
[smoke] WebSocket 정상 종료 (1000 OK Bye) — 서버 연결 수명 초과 또는 장 마감 후 서버 정상 종료.
  LOGIN 실패가 아닙니다. 스크립트를 다시 실행하면 재연결됩니다.
```

`1000 (OK) Bye` 는 WebSocket 정상 종료 코드다. **인증 실패나 네트워크 오류가 아니다.**

원인:
- 서버 측 연결 수명 초과 (200종목 가까이 등록 시 더 빨리 발생하는 경향)
- 장 마감(18:00) 이후 서버 정상 종료
- Kiwoom 서버 점검

대응:
- 스크립트를 다시 실행하면 즉시 재연결된다
- 반복된다면 종목 수를 150으로 줄인다 (`data/universe_codes_150.txt`)
- 장시간 자동 운영은 v3 과제 (외부 루프 재연결)

---

## 11. 장애 대응

### 오류 8030 — 키 종류/환경 불일치

```
8030: 투자구분(실전/모의)이 달라서 Appkey를 사용할 수가 없습니다.
```

→ `.env` 에서 `KIWOOM_ENV=prod` 인데 모의투자 키를 썼는지 확인. 실전 키로 교체.

### `sector-map-file` 미지정 에러

```
[smoke] ERROR: --sector-map-file 이 지정되지 않았습니다.
```

→ `--sector-map-file data/sector_map.json` 추가. 파일이 없으면 먼저 생성:

```bash
.venv/bin/python scripts/build_intraday_universe.py --input data/theme_map.csv --limit 150
```

### snapshot status = warming (sector_views 없음)

```
status=warming minute=1345 latest=50 unmapped=50 buckets=50 sectors=0
```

원인 진단 순서:
1. `unmapped=N` 이 크면 → sector_map 이 수신 종목을 커버하지 못함. `--sector-map-file` 확인
2. `unmapped=0` 인데 warming → `--min-total-trade-value` 가 너무 높음 (0으로 낮춰서 확인)
3. 장외 시간(08:00 전, 18:00 후)이면 tick 이 없을 수 있음

### snapshot status = empty (bucket 없음)

- 장중(08:00~18:00 KST)이 아닌 경우
- WebSocket 연결은 됐지만 REG 실패: `[smoke] REG 실패` 메시지 확인
- `--provider mock` 으로 전환해 파이프라인 자체 문제인지 확인

### Flask `/sector-board/intraday` 화면이 empty 상태

1. `logs/` 디렉토리에 `intraday_snapshot_*.jsonl` 파일이 있는지 확인
2. 파일이 있으면 마지막 줄이 유효한 JSON 인지 확인
3. smoke script 를 `--dump-snapshot-jsonl` 옵션으로 실행했는지 확인

---

## 12. 하지 말아야 할 것

### ❌ 주문 / 계좌 / 잔고 기능 추가 금지

이 프로젝트는 **시세 수신과 대시보드 표시 전용**이다.  
다음 API 는 절대 추가하거나 호출하지 않는다:

- 매수/매도/정정/취소 주문 API
- 계좌 잔고 조회 API
- 보유 종목 조회 API
- 출금/입금 관련 API

### ❌ 200종목 초과 무리한 등록 금지

Kiwoom WebSocket 세션 총 등록 상한 200종목은 실험으로 확인된 사실이다.  
`--allow-over-200-experimental` 플래그를 운영에 사용하지 않는다.  
multi-connection 방식은 v3 과제다.

### ❌ 기존 Morning Board 파괴 금지

다음 파일/경로/함수를 수정하거나 삭제하지 않는다:

- `get_morning_board_view_models()`
- `build_morning_snapshot_payload()`
- `sector_board/collector.collect_and_store()`
- `GET /sector-board/` (route)
- `GET /sector-board/api/snapshot`
- `GET /sector-board/health`
- `sector_board/templates/sector_board/index.html`
- `sector_board/schema.py` (DB schema)

### ❌ DB schema migration 임의 변경 금지

`sector_board/schema.py` 는 명시적으로 요청받기 전까지 변경하지 않는다.  
v2 intraday board 는 JSONL 파일 기반으로 동작하며 DB 를 건드리지 않는다.

---

## 13. 테스트 및 검증 명령

```bash
# 문법 검사
.venv/bin/python -m py_compile app.py src/*.py sector_board/*.py scripts/*.py

# 전체 테스트 (현재 456개 통과)
.venv/bin/python -m pytest -q

# whitespace 검사
git diff --check
```

테스트 파일 목록 (v2 관련):

| 파일 | 내용 |
|---|---|
| `tests/test_intraday_tick_aggregator.py` | 1분 bucket 집계 |
| `tests/test_intraday_sector_aggregator.py` | 섹터별 집계 |
| `tests/test_intraday_leader_ranker.py` | 주도섹터 ViewModel |
| `tests/test_intraday_snapshot_service.py` | Snapshot Service |
| `tests/test_intraday_snapshot_smoke.py` | smoke script 헬퍼 |
| `tests/test_sector_map_loader.py` | sector_map 로더 |
| `tests/test_build_intraday_universe.py` | universe 생성 스크립트 |
| `tests/test_sector_board_intraday_reader.py` | JSONL reader / view builder |
| `tests/test_sector_board_intraday_route.py` | Flask `/intraday` route |

---

## 14. 새 개발자 빠른 시작

```bash
# 1. 의존성 설치
pip install -e .  # 또는 pip install -r requirements.txt

# 2. .env 설정 (4절 참고)

# 3. universe / sector_map 생성 (이미 data/ 에 있으면 생략)
.venv/bin/python scripts/build_intraday_universe.py \
  --input data/theme_map.csv --limit 150

# 4. mock smoke (API 키 불필요)
.venv/bin/python scripts/run_intraday_snapshot_smoke.py \
  --provider mock \
  --exchange sor \
  --codes-file data/universe_codes_150.txt \
  --sector-map-file data/sector_map.json \
  --listen-seconds 15 \
  --summary-interval-seconds 5

# 5. Flask 로컬 실행
flask --app "sector_board:create_app()" run
# → http://localhost:5000/sector-board/intraday  (mock JSONL 없으면 empty 상태)

# 6. prod smoke (장중 08:00~18:00, 실전 키 필요)
KIWOOM_REAL_APP_KEY=<키> KIWOOM_REAL_SECRET_KEY=<시크릿> \
.venv/bin/python scripts/run_intraday_snapshot_smoke.py \
  --provider websocket --kiwoom-env prod --exchange sor \
  --codes-file data/universe_codes_150.txt \
  --sector-map-file data/sector_map.json \
  --listen-seconds 300 --summary-interval-seconds 30 \
  --dump-snapshot-jsonl
# → http://localhost:5000/sector-board/intraday 새로고침으로 결과 확인

# 7. 테스트
.venv/bin/python -m pytest -q
```

---

## 15. v3 후보 과제

다음은 v2 안정화 이후 별도 단계에서 검토한다.  
**현재 단계에서는 구현하지 않는다.**

### 15-1. multi-connection (300종목 이상)

- Kiwoom WebSocket 세션 1개 당 200종목 제한
- 세션을 2개 이상 유지해 200종목씩 나눠 등록
- 구현 복잡도 높음 — 세션 간 tick 동기화, 재연결 로직 필요

### 15-2. DB 저장 (히스토리 보관)

- 현재: in-memory + JSONL (프로세스 재시작 시 유실)
- 개선: `sector_snapshots` 테이블에 1분 단위 snapshot 저장
- DB schema migration 필요 → 명시적 요청 시 진행

### 15-3. Render background worker 자동화

- 현재: 로컬에서 smoke script 수동 실행
- 개선: Render Background Worker 로 장중 자동 실행
- `--listen-seconds` + 자동 재연결 루프 구현 필요

### 15-4. OpenDART/KRX 기반 universe 자동화

- 현재: `data/theme_map.csv` 수동 관리 (150종목)
- 개선: KRX 상장 데이터 API 또는 OpenDART 로 시가총액 기준 자동 생성
- ETF/SPAC/우선주 자동 필터링 강화
- `build_intraday_universe.py --auto-fetch` 옵션 추가

### 15-5. 시장 평균 대비 초과수익률 scoring

- 현재 `sector_score` 는 임시 v1 계산식
- 개선: KOSPI/KOSDAQ 지수 기준 초과수익률 반영
- 섹터별 기준 거래대금(베이스라인) 정규화

### 15-6. NXT/KRX/SOR 비교 화면

- 현재: SOR 단일 데이터 소스
- 개선: 거래소별 체결 비중, NXT 선행 감지 등 비교 분석

### 15-7. 장중 자동 재연결 루프

- 현재: 1000 Bye 발생 시 스크립트가 종료됨
- 개선: supervisor 또는 외부 루프로 자동 재연결
- 세션 수명 측정 → 적정 `--listen-seconds` 최적화

---

## 부록: WebSocket 필드 매핑 (0B 주식체결, 확정 2026-06-01)

| 필드 인덱스 | 필드명 | 설명 |
|---|---|---|
| `"20"` | `trade_time` | 체결시간 HHMMSS |
| `"10"` | `current_price` | 현재가 (부호 포함 int) |
| `"11"` | `change_price` | 전일대비 (부호 포함 int) |
| `"12"` | `change_rate` | 등락률 % (부호 포함 float) |
| `"15"` | `trade_volume` | 체결량 |
| `"13"` | `accumulated_volume` | 누적거래량 |
| `"14"` | `accumulated_trade_value` | 누적거래대금 |

---

*최종 업데이트: 2026-06-01 | 테스트 456 passed*
