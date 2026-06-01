# 장중 주도섹터/대장주 리더보드 전환 계획

## 현재 구조

현재 프로젝트는 두 개의 표시 계층을 가진다.

- `app.py`는 로컬 Streamlit 대시보드의 진입점이다. `src/market_data.py`에서 `summary`, `heatmap`, `leaders`를 받아 `src/dashboard_components.py`로 렌더링하고, `src/snapshot_service.py`로 로컬 JSON/섹터보드 DB 스냅샷을 저장한다.
- `sector_board/*`는 Render/Flask 배포용 보드 계층이다. `sector_board/blueprint.py`가 DB의 최신 스냅샷을 읽어 `sector_board/templates/sector_board/index.html`에 보여주고, 데이터가 없거나 오류 상태면 `sector_board/collector.py`를 통해 백그라운드 수집을 시작한다.

현재 데이터 흐름은 다음과 같다.

1. `sector_board/__init__.py`가 Flask 앱에 `sector_board` 블루프린트를 등록하고, KRX 모드일 때 `sector_board/scheduler.py`의 일일 수집 스케줄러를 설정한다.
2. `sector_board/scheduler.py`는 매일 `KRX_COLLECT_HOUR` 기본값인 04:00 KST에 `sector_board/collector.collect_and_store()`를 실행한다. 시작 시 최신 전거래일 스냅샷이 없으면 즉시 백그라운드 수집도 시도한다.
3. `sector_board/collector.py`는 `src.market_data.get_morning_board_view_models()`를 호출한다. 이후 `src.snapshot_service.build_morning_snapshot_payload()`로 `summary`, `themes`, `leaders` JSON 구조를 만들고, 상승이유는 `src.evidence_service.build_evidence_bundles()`와 `src.rise_reason_service.summarize_rise_reasons()`로 별도 생성한다.
4. `src/market_data.py`는 기본적으로 `Settings.use_krx_data=True`이면 `src.krx_collector.fetch_krx_snapshot()`을 통해 전체 KRX 스냅샷을 가져오고 `src.sector_ranker.rank_sectors_krx()`로 랭킹을 만든다. KRX 수집 실패 또는 KRX 비활성 시에는 `theme_map.csv` 기반 후보 종목을 Kiwoom REST 또는 mock 데이터로 조회하고 `rank_sectors()`를 사용한다.
5. `src/sector_ranker.py`는 종목별 `change_rate`, `trade_value`, `open_price`, `current_price`, `volume`를 사용해 섹터 점수와 섹터 내 대장주 점수를 계산한다. 점수는 등락률, 거래대금 순위, 시가 대비 현재가 강도, 대표성 기본값을 혼합한다.
6. `sector_board/repository.py`는 `sector_snapshots` 테이블에 날짜별 스냅샷을 upsert한다. 현재 스키마는 `snapshot_date`를 유니크 키로 사용하므로 하루에 여러 장중 스냅샷을 저장하는 구조가 아니다.
7. `sector_board/blueprint.py`는 최신 스냅샷 하나를 읽고, 전일 스냅샷과 비교해 카드별 `rank_change`를 만든다. 화면은 기본 12개 섹터 카드와 Top 5 리더를 보여준다.
8. `templates/sector_board/index.html`은 "오늘의 주도섹터" 제목을 쓰지만, 실제 중심 UI는 요약 지표, treemap, 이번 주 주도테마, 섹터 카드 12개, 상승이유 분석 순서다.

현재 앱은 "전날 종가 브리핑"에 더 가깝다. 특히 Render/Flask 배포 경로는 KRX 기본 모드에서 04:00 KST에 전거래일 전체 KRX 데이터를 수집하고 날짜별 단일 스냅샷으로 저장한다. Streamlit 경로에는 장중 체크포인트와 Kiwoom REST 조회 경로가 있지만, 기본 KRX 모드와 DB 스키마/스케줄러/템플릿은 장중 반복 갱신 리더보드라기보다 아침 브리핑 스냅샷에 맞춰져 있다.

## 문제점

- `sector_board/schema.py`의 `sector_snapshots.snapshot_date` 유니크 제약 때문에 같은 거래일의 09:30, 10:00, 13:00 등 장중 여러 스냅샷을 히스토리로 보관할 수 없다.
- `sector_board/scheduler.py`와 `sector_board/collector.py`의 기본 운영 모델은 일일 수집이다. 장중 N초/N분 단위 polling 또는 WebSocket 이벤트 누적 모델이 없다.
- `src/market_data.py`의 기본 KRX 경로는 `FinanceDataReader.StockListing("KRX")`와 KRX/KIND 캐시 조합이다. 이 경로는 전거래일/지연성 스냅샷에 적합하고, 장중 현재가 소스로 보기 어렵다.
- `src/sector_ranker.py`는 현재 섹터 점수에 시장 대비 초과수익, 거래대금 집중도, 지속성, 오전/오후 교체 감지를 직접 반영하지 않는다.
- Universe 필터 계층이 분리되어 있지 않다. 시가총액 기준, 거래대금 하위 제외, ETF/스팩/우선주/관리종목 제외 같은 실전 필터가 랭킹 엔진 앞단에 명시적으로 없다.
- 사용자 관리 실전 테마/섹터는 `src/theme_loader.py`의 `theme1~theme3` CSV에 묶여 있고, KRX 모드에서는 공식 업종 중심으로 계산된다.
- `src/kiwoom_client.py`는 종목별 REST polling만 제공한다. 대량 종목을 초단위로 지속 조회하기에는 API 제한과 비용이 크다.
- `src/kiwoom_websocket.py`는 placeholder이며, 이벤트를 받아 메모리 상태를 갱신하는 어댑터 계약이 없다.
- `src/evidence_service.py`는 현재 `get_market_movers()`의 mock mover를 기반으로 뉴스 evidence를 만든다. 실제 leaders 결과와 상승이유가 직접 연결되어 있지 않다.
- `templates/sector_board/index.html`은 Top 5 압축 화면이 아니라 12개 카드와 treemap/주간표가 중심이다. 사용자가 장중 즉시 볼 "오늘 갑자기 치고 올라오는 3~5개 섹터와 대장주" 화면과 다르다.

## 목표 구조

기존 아침 스냅샷을 깨뜨리지 않고, 새 장중 리더보드 구조를 병렬로 추가한다.

```text
Universe Layer
  - KRX 전일 데이터, theme_map, 사용자 제외 규칙으로 감시 후보군 생성
  - 시가총액/거래대금/종목 유형 필터 적용
  - 무료형 V1은 제한된 후보군만 Kiwoom REST polling 대상으로 선정

Data Provider Layer
  - KRX delayed/eod provider
  - Kiwoom REST polling provider
  - Kiwoom WebSocket provider placeholder
  - Mock provider
  - 모든 provider는 동일한 quote/event/snapshot 스키마를 반환

Intraday State Layer
  - 종목별 현재가, 등락률, 거래대금, 거래량, 최근 업데이트 시각을 메모리에 누적
  - 일정 주기마다 board snapshot 생성
  - WebSocket V2에서는 tick/event 수신 시 상태만 갱신하고, 화면용 snapshot은 N초마다 생성

Ranking Engine
  - 후보군에서 오늘 주도섹터 Top 5 계산
  - 섹터별 대장주 Top 3~5 계산
  - 거래대금, 상승률, 시장 대비 강도, 거래대금 집중도, 지속성을 점수화
  - 랭크 교체 이벤트 생성

Delivery Layer
  - Render/Flask 화면: 장중 리더보드 우선 표시
  - Streamlit 화면: 동일 snapshot contract 사용
  - 데이터 모드: krx, rest, websocket, mock, fallback
  - 마지막 업데이트 시각과 snapshot freshness 표시
```

핵심 원칙은 "데이터 공급자 교체 가능성"이다. 무료형 V1은 KRX 전일 데이터로 universe를 만들고 장중에는 제한된 종목만 REST polling한다. 확장형 V2는 같은 ranking/snapshot contract 위에 Kiwoom WebSocket 어댑터를 붙인다.

## 단계별 변경 계획

1. 스키마/계약 문서화 먼저
   - 새 snapshot contract를 `summary`, `themes`, `leaders`, `rank_events`, `universe`, `provider_status`로 정의한다.
   - 기존 `build_morning_snapshot_payload()`와 `sector_snapshots` 호환을 유지하기 위해 `themes`/`leaders` 필드는 기존 키를 포함하고, 새 키는 optional로 추가한다.
   - 하루 여러 번 저장이 필요해지는 시점 전까지는 DB migration 없이 최신 장중 snapshot을 같은 날짜 row에 overwrite하는 V1로 시작한다.

2. Universe Layer 추가
   - 신규 후보 파일: `src/universe_builder.py`.
   - 입력: KRX 전일 데이터, `theme_map.csv`, 설정값.
   - 출력: polling 대상 종목 DataFrame과 제외 사유 통계.
   - 필터: 최소 시가총액, 최소 거래대금, ETF/스팩/우선주/관리종목 제외 옵션.
   - `src/market_data.py`는 직접 codes를 만들지 않고 universe builder 결과를 받도록 점진 전환한다.

3. Data Provider 계약 추가
   - 신규 후보 파일: `src/data_providers.py` 또는 `src/quote_provider.py`.
   - 공통 메서드: `load_universe_snapshot()`, `fetch_quotes(codes)`, `provider_mode`.
   - `src/kiwoom_client.py`는 REST provider 구현으로 감싼다.
   - `src/kiwoom_websocket.py`는 바로 실시간 구현하지 않고 공통 quote/event schema와 연결 지점만 맞춘다.
   - 기존 mock/sample 데이터 provider도 같은 계약을 구현해 테스트를 안정화한다.

4. Intraday Ranking Engine 추가
   - `src/sector_ranker.py`에 기존 함수는 유지하고, 새 함수 후보 `rank_intraday_leaders()`를 추가한다.
   - 섹터 점수 후보:
     - 상위 리더 평균 등락률
     - 섹터 총 거래대금 및 거래대금 증가/집중도
     - KOSPI/KOSDAQ 또는 전체 후보군 대비 초과수익
     - 리더 지속성 또는 최근 N회 snapshot 유지 점수
   - 종목 점수 후보:
     - 등락률 rank
     - 거래대금 rank
     - 시가 대비 강도
     - 섹터 내 기여도
     - 최근 유지/급부상 점수
   - 출력은 Top 5 sectors와 각 sector Top 3~5 leaders로 제한한다.

5. Snapshot/State Layer 추가
   - 신규 후보 파일: `src/intraday_snapshot_service.py`.
   - 입력: provider quote DataFrame, universe, 이전 snapshot.
   - 출력: 화면용 snapshot payload.
   - 교체 감지는 이전 snapshot의 Top 5와 현재 Top 5를 비교해 `rank_events`로 만든다.
   - 기존 `src/snapshot_service.py`는 morning snapshot 호환 계층으로 유지한다.

6. Render/Flask delivery 전환
   - `sector_board/collector.py`에 V1 장중 수집 경로를 추가하되 기존 `collect_and_store()`는 유지한다.
   - 새 함수 후보: `collect_intraday_and_store(database_url)`.
   - `sector_board/blueprint.py`는 `summary.data_mode`, `summary.board_type` 또는 feature flag로 장중 snapshot UI와 기존 morning UI를 선택한다.
   - `sector_board/repository.py`는 우선 기존 row overwrite를 유지하고, 장중 히스토리 저장이 확정될 때만 migration 계획을 별도로 세운다.

7. 화면 개편
   - `templates/sector_board/index.html`은 첫 화면을 "오늘의 주도섹터 Top 5"로 압축한다.
   - 각 섹터는 섹터명, 평균 상승률, 거래대금, 시장대비 강도, 리더 Top 3~5를 보여준다.
   - `rank_events`가 있으면 "교체 감지" 섹션을 표시한다.
   - treemap, 주간표, 상승이유는 보조 섹션으로 유지해 기존 기능을 제거하지 않는다.

8. 상승이유 연결
   - `src/evidence_service.py`는 `get_market_movers()` mock 대신 실제 `leaders` snapshot에서 mover 후보를 받는 진입점을 추가한다.
   - 신규 함수 후보: `build_evidence_bundles_for_leaders(leaders, limit=10)`.
   - 기존 mock 기반 함수는 테스트/폴백용으로 유지한다.

9. 운영 설정 추가
   - `src/config.py`에 intraday 관련 설정을 추가한다.
   - 후보 설정: `INTRADAY_BOARD_ENABLED`, `INTRADAY_PROVIDER`, `INTRADAY_POLL_SECONDS`, `INTRADAY_MAX_CODES`, `UNIVERSE_MIN_MARKET_CAP`, `UNIVERSE_MIN_TRADE_VALUE`.
   - 기본값은 기존 운영을 깨지 않도록 disabled 또는 KRX/morning 호환 모드로 둔다.

## 파일별 변경 방향

| 파일 | 변경 방향 |
| --- | --- |
| `sector_board/blueprint.py` | 기존 snapshot 렌더링 유지. 장중 snapshot이면 Top 5 리더보드 컨텍스트와 `rank_events`를 템플릿에 전달. 기존 12개 카드/weekly/rise_reason은 fallback 또는 보조 섹션으로 유지. |
| `sector_board/collector.py` | 기존 `collect_and_store()` 유지. 장중 V1용 collector를 별도 함수로 추가하고 provider/ranking/snapshot layer를 호출. 실패 시 기존 mock/fallback 흐름을 보존. |
| `sector_board/repository.py` | V1에서는 기존 `upsert_snapshot()`와 `fetch_snapshot()` 유지. 하루 여러 snapshot 저장은 별도 migration 필요하므로 즉시 변경하지 않음. optional fields 저장만 허용. |
| `sector_board/schema.py` | 즉시 변경하지 않음. 장중 히스토리 저장을 시작할 때 `snapshot_time` 또는 별도 `intraday_snapshots` 테이블 검토. |
| `src/market_data.py` | 현재 morning board facade를 유지하고, intraday facade를 새로 추가. KRX/REST/mock provider 선택은 내부에서 분리. |
| `src/sector_ranker.py` | 기존 `rank_sectors()`/`rank_sectors_krx()` 유지. 새 `rank_intraday_leaders()`와 교체 감지에 필요한 stable output schema 추가. |
| `src/kiwoom_client.py` | REST 단건 polling 클라이언트를 provider 계약에 맞게 래핑. rate limit과 `INTRADAY_MAX_CODES` 보호 장치 추가. |
| `src/kiwoom_websocket.py` | placeholder 유지하되 quote event schema, subscribe/update/snapshot adapter 인터페이스 정의. 실제 접속 구현은 공식 문서 확인 후 별도 단계. |
| `src/theme_loader.py` | 기존 `theme1~theme3` CSV 유지. 사용자 관리 실전 테마를 universe builder가 재사용할 수 있도록 long format과 sector alias/weight 확장 가능성만 열어둠. |
| `src/evidence_service.py` | 실제 leaders 기반 evidence bundle 생성 진입점 추가. 기존 `get_market_movers()` mock 기반 함수는 폴백과 테스트용으로 유지. |
| `templates/sector_board/index.html` | 첫 화면을 Top 5 리더보드로 재배치. 기존 treemap/weekly/rise_reason 삭제 금지, 보조 섹션으로 유지. |
| `tests/` | 기존 테스트는 유지. universe/ranking/provider/snapshot/blueprint 표시 테스트를 추가. DB migration 없는 V1 호환 테스트를 먼저 작성. |

## 위험한 변경점

- DB migration: `snapshot_date` 유니크 구조를 깨면 Render 배포 DB와 기존 테스트가 바로 영향을 받는다. 장중 히스토리 저장은 별도 승인과 migration 계획이 필요하다.
- Kiwoom REST 대량 polling: 무료형 V1에서 초당 수백 종목 조회 구조를 기본값으로 만들면 API 제한, 느린 응답, 계정 차단 위험이 있다. 반드시 universe를 제한하고 polling 주기를 길게 둔다.
- WebSocket 실제 연결: 현재 파일은 placeholder다. endpoint/auth/message schema는 최신 공식 문서 확인 전 구현하지 않는다.
- 화면 전면 교체: 기존 treemap, 주간표, 상승이유, mock fallback은 사용자가 이미 확인한 기능일 수 있으므로 삭제하지 않는다.
- KRX/KIND/FinanceDataReader 의존: 장중 현재가가 아니라 전일/지연 데이터일 가능성이 있어 `data_mode`와 freshness를 화면에 명확히 표시해야 한다.
- 상승이유 요약 비용/속도: leaders마다 뉴스 검색과 요약을 돌리면 화면 갱신을 막을 수 있다. 랭킹 계산과 evidence 수집은 분리하고 실패해도 보드는 표시해야 한다.
- 시장 대비 강도 계산: 기준 지수 또는 후보군 평균을 무엇으로 볼지 정해야 한다. 초기 V1은 후보군 평균 대비 초과수익으로 시작하고 지수 데이터는 후속으로 붙인다.

## 테스트 전략

1. 기존 회귀 보호
   - `python -m py_compile app.py src/*.py sector_board/*.py`
   - `pytest -q`
   - `git diff --check`

2. Universe Layer 테스트
   - 시가총액/거래대금 기준 미달 종목 제외.
   - ETF/스팩/우선주/관리종목 제외 옵션.
   - `theme_map.csv`의 다중 테마가 long format으로 유지되는지 확인.

3. Provider 계약 테스트
   - mock provider, KRX provider, REST provider가 같은 quote columns를 반환하는지 확인.
   - REST provider는 `INTRADAY_MAX_CODES`와 polling interval 보호를 테스트.
   - WebSocket provider는 실제 연결 없이 event schema와 state update 단위 테스트만 먼저 작성.

4. Ranking Engine 테스트
   - 거래대금이 크고 상승률이 높은 종목이 leader 상위에 오는지 확인.
   - 섹터 총 거래대금, 상승률, 시장 대비 초과수익, 지속성 점수가 섹터 순위에 반영되는지 확인.
   - Top 5 sectors와 sector별 Top 3~5 leaders로 결과가 제한되는지 확인.

5. Snapshot/교체 감지 테스트
   - 이전 snapshot 대비 신규 진입, 이탈, 순위 상승/하락 이벤트 생성.
   - `generated_at`, `data_mode`, `provider_status`, `rank_events`가 비어도 기존 화면이 깨지지 않는지 확인.
   - V1에서는 같은 날짜 row overwrite가 기존 repository 테스트와 호환되는지 확인.

6. Flask 화면 테스트
   - `tests/test_sector_board_blueprint.py`에 장중 snapshot fixture를 추가한다.
   - Top 5 제목, 마지막 업데이트, 데이터 모드, 섹터별 leader Top 3 표시를 검증한다.
   - 기존 morning snapshot fixture도 계속 렌더링되는지 확인한다.

7. Streamlit smoke 테스트
   - mock mode에서 첫 화면이 새 리더보드 중심으로 보이는지 확인.
   - KRX/morning mode에서도 기존 데이터가 fallback UI로 표시되는지 확인.

## 다음 단계에서 수정해야 할 파일

1. `src/universe_builder.py` 신규 추가
2. `src/data_providers.py` 또는 `src/quote_provider.py` 신규 추가
3. `src/intraday_snapshot_service.py` 신규 추가
4. `src/sector_ranker.py`
5. `src/market_data.py`
6. `src/config.py`
7. `src/kiwoom_client.py`
8. `src/kiwoom_websocket.py`
9. `src/evidence_service.py`
10. `sector_board/collector.py`
11. `sector_board/blueprint.py`
12. `sector_board/templates/sector_board/index.html`
13. `tests/test_sector_ranker.py`
14. `tests/test_market_data_view_models.py`
15. `tests/test_sector_board_blueprint.py`
16. 신규 universe/provider/snapshot 테스트 파일
