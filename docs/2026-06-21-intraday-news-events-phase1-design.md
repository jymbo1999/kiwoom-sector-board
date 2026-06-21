# Intraday 뉴스 이벤트 추적 — Phase 1 설계

**작성일:** 2026-06-21
**대상 레포:** `kiwoom-sector-board` (Render는 `@master` pull, 로컬은 sibling 폴더)
**상태:** 설계 합의 완료 → 구현 플랜 작성 대기

---

## 1. 목표 (한 줄)
인트라데이 세션이 켜져 있는 동안, 가격 급변(급등/급락) **이벤트를 감지 → 네이버 뉴스 자동 수집 → DB 영속 → `/intraday`의 탭 UI에서 알림과 함께 확인**할 수 있게 한다.

## 2. 범위 (Phase 1만)
**포함:**
- 가격 이벤트 감지 + 30분 쿨다운
- 이벤트/기사 **Postgres 영속**(공유 DB)
- 기사 수집(기존 `search_naver_news` 재사용) + **stage 간 영속 dedupe**
- 단계 수집 `T0 / T+10 / T+30` (이벤트당 최대 3회 — 구조적 상한)
- `/intraday` 탭 UI: `가격 / 뉴스 / 일일로그`
- 뉴스 탭 **NEW·느낌표 책갈피 버튼**(읽지 않은 이벤트 표시)

**제외 (이후 Phase):**
- OpenAI 요약(`summarize_rise_reasons` 연결) — Phase 2
- 호출 예산/429 백오프/`naver_api_call_logs` — Phase 2
- 16:10 일일 최종 요약 생성 + 요약 로그 테이블 — Phase 4
- 내용 유사도 기반 dedupe(3단계) — 이후

> Phase 1 일일로그 탭은 **요약 없이** 날짜별 이벤트/기사 목록만 보여준다(요약은 Phase 4에서 얹음).

## 3. 핵심 제약 (이미 확인된 사실)
1. **인트라데이는 상시 워커가 아님.** `POST /intraday/api/start`로 사용자가 켤 때만 `IntradaySnapshotService`(in-process 데몬 스레드, 기본 2시간)가 돈다. → 이벤트 감지/수집은 **세션이 켜진 동안만** 작동. 배포/재시작 시 스레드는 죽지만 **DB 기록은 영구 보존**.
2. **수집·요약 엔진은 이미 존재** → 재사용:
   - `src/news_service.py`: `search_naver_news(query, display, sort=date)`, `build_news_queries_for_mover(mover)`
   - `src/evidence_service.py`: `_dedupe_evidence` (번들 내 메모리 dedupe — Phase 1은 **DB 영속 dedupe로 보강**)
   - (요약 `src/rise_reason_service.summarize_rise_reasons`는 Phase 2에서 연결)
3. **저장 이원화:** 데일리 보드 = Postgres(`repository.py`), 인트라데이 스냅샷 = JSONL(휘발). 신규 테이블은 **Postgres**.
4. **스냅샷 필드(감지 입력):** 대장주 `last_change_rate`(일중 등락률), `minute_trade_value_delta`, `base_code`; 섹터 `average_change_rate`, `sector_score`, `sector_name`. (10분 단기수익률 전용 필드는 없음 → Phase 1은 **일중 등락률 기준**, 단기수익률은 직전 스냅샷 대비 파생 가능 시 옵션.)

## 4. 비파괴 원칙 (최우선)
- 신규 기능 전체를 `SECTOR_BOARD_INTRADAY_NEWS_ENABLED`(신규 env)로 게이팅. 기본 OFF.
- 감지/수집은 **틱 루프와 분리된 사이드카 스레드**에서 `runtime.get_latest_snapshot()`을 주기(기본 30초) 폴링 → 틱 성능 무영향.
- 모든 감지/수집/DB 호출은 try/except로 감싸 **가격판 렌더와 인트라데이 수집을 절대 막지 않음**.
- 네이버/OpenAI 키 없거나 실패 시: 이벤트는 기록하되 기사 0개로 graceful.

## 5. 데이터 모델 (신규 2개 테이블, `repository.py` 패턴 미러)

### `intraday_news_events`
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | PK | |
| trade_date | date | 인덱스 |
| detected_at | timestamp | |
| event_type | text | `rise` / `fall` |
| scope | text | `stock` / `sector` |
| sector_name | text | nullable |
| stock_code | text | nullable |
| stock_name | text | nullable |
| change_rate | float | 일중 등락률 |
| short_change_rate | float | nullable(파생 가능 시) |
| trigger_reason | text | 사람이 읽는 감지 사유 |
| status | text | `detected`→`collecting`→`collected`/`failed` |
| is_read | bool | 기본 false |
| created_at / updated_at | timestamp | |
| payload_json | json | 감지 시 스냅샷 일부 등 부가 |

**쿨다운/멱등:** `(trade_date, scope, COALESCE(stock_code,sector_name), event_type)` 기준, **30분 내 신규 생성 금지** → 기존 이벤트의 `change_rate`/`updated_at`만 갱신.

### `intraday_news_articles`
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | PK | |
| event_id | FK→events.id | 인덱스 |
| title | text | strip_html 적용 |
| url | text | originallink 우선, 없으면 link |
| source | text | |
| published_at | text/timestamp | naver pubDate 정규화 |
| description | text | |
| query | text | 어떤 검색어로 잡혔는지 |
| stage | text | `T0`/`T+10`/`T+30` |
| collected_at | timestamp | |
| dedupe_key | text | **unique(event_id, dedupe_key)** |
| created_at | timestamp | |

**dedupe_key 규칙(2단계):** `originallink`(없으면 `link`) 우선; 그것도 없으면 `sha256(normalized_title + source + published_date)`. `normalized_title` = HTML/`<b>` 제거 → 특수문자/공백 정리 → 언론사명 제거 → 소문자화. `(event_id, dedupe_key)` unique 제약으로 stage 재수집 시 중복 자동 skip.

> 스키마 생성은 `metadata.create_all(checkfirst=True)` + 신규 `ensure_news_schema()`를 기존 `ensure_schema()` 호출 지점에서 함께 호출(dialect-aware: postgres/sqlite/기타 fallback — 기존 `_upsert_row` 패턴 그대로).

## 6. 이벤트 감지 규칙 (Phase 1, 단순)
- **상승:** `change_rate >= +8%` (단기수익률 파생 가능 시 `>= +5%` OR)
- **하락:** `change_rate <= -8%` (단기 `<= -5%` OR)
- **섹터:** 같은 섹터 내 `+10%` 이상 종목 3개 이상 **또는** 섹터가 인트라데이 Top5 **신규 진입**
- 처음엔 종목 일중 등락률만으로 시작해도 됨(오탐↓). 단기/섹터 규칙은 스냅샷 필드 확인 후 점증.

## 7. 수집 오케스트레이션 (사이드카)
```
세션 start → 사이드카 스레드 시작(INTRADAY_NEWS_ENABLED일 때만)
loop(30초):
  snap = runtime.get_latest_snapshot()
  for cand in detect_events(snap):           # 종목/섹터 후보
     if should_create_event(cand):           # 30분 쿨다운 통과
        ev = create_event(cand)              # status=detected
        enqueue(ev, stage="T0")
  process_due_stages():                       # T+10/T+30 도래분
     for ev,stage in due:
        collect_news_for_event(ev, stage)     # search_naver_news 재사용 → 기사 upsert(dedupe)
세션 stop → 사이드카 종료
```
- `collect_news_for_event`: `build_news_queries_for_mover` + 섹터 키워드 → `search_naver_news(query, display=20)` → 기사 정규화 → `(event_id,dedupe_key)` upsert. 이벤트당 stage 상한 3회.
- **검색어 쿨다운**(같은 query 5분 내 재검색 금지)은 가벼우므로 Phase 1 포함(예산 시스템은 Phase 2).

## 8. UI (`/intraday`)
- `?tab=price`(기본) / `?tab=news` / `?tab=daily-log` — 서버사이드 탭. 기존 가격판 마크업 **무수정**(price 탭으로 감싸기만).
- **뉴스 탭:** 오늘 이벤트 시간 역순 카드 — 감지시각·타입·섹터·관련종목·감지사유·기사수·기사 링크 목록. (요약문은 Phase 2 자리만 비워둠.)
- **일일로그 탭:** 상단에 **용량 관리 패널**(총 이벤트 수 · 총 기사 수 · 전체 저장 용량) → 그 아래 `trade_date`별 이벤트 집계 목록 → 날짜 클릭 시 그날 이벤트.
  - **전체 저장 용량:** 두 테이블 합산. Postgres = `pg_total_relation_size('intraday_news_events') + pg_total_relation_size('intraday_news_articles')`, SQLite = 행수 기반 추정 또는 `dbstat`, 기타 dialect = 추정치. 사람이 읽는 단위(KB/MB)로 포맷.
- **책갈피 버튼:** 가격판 우상단 `뉴스 이벤트 N건 !` — `is_read=false`인 이벤트 있으면 NEW/느낌표. 클릭 → `?tab=news`. 뉴스 탭 진입 시 `mark_news_events_read(today)`.

## 9. 신규/수정 파일 (kiwoom-sector-board)
- `sector_board/intraday_news.py` (신규): `detect_intraday_news_events`, `should_create_event`, `create_news_event`, `collect_news_for_event`, `process_pending_stages`, `get_unread_news_event_count`, `mark_news_events_read`, 사이드카 러너.
- `sector_board/news_repository.py` (신규): 테이블 정의 + `ensure_news_schema` + 이벤트/기사 upsert·조회 + `get_news_storage_stats()`(총 이벤트/기사 수 + dialect-aware 전체 용량) (기존 `repository.py` 엔진/패턴 재사용).
- `sector_board/intraday_blueprint.py` (수정): `index`에 `tab` 분기 + unread count 주입; `api_start` 경로에서 사이드카 기동(게이팅).
- `sector_board/templates/sector_board/intraday.html` (수정): 탭/책갈피/뉴스·로그 파셜.
- `tests/`: 쿨다운 중복방지 / 기사 dedupe / unread count / 뉴스 수집 실패해도 가격판 유지.

## 10. 검증 기준
- INTRADAY_NEWS_ENABLED OFF → 기존 인트라데이 동작 **완전 동일**.
- 같은 종목/섹터+타입 30분 내 이벤트 1개만 생성.
- 같은 기사 T0/T+10/T+30 중복 수집해도 `articles` 행 1개.
- 네이버 키 제거 시: 이벤트 생성·표시되되 기사 0개, 가격판 정상.
- `?tab=news` NEW 표시 → 진입 후 사라짐(read 처리).
- 일일로그 탭 용량 패널이 총 이벤트/기사 수 + 전체 용량(KB/MB)을 정확히 표시.
- 기존 sector-board/intraday 테스트 + 신규 테스트 그린.

## 11. 배포
- 작업은 `kiwoom-sector-board` → `master` push → Render 재빌드(`requirements.txt @master`). 로컬은 sibling 폴더 즉시 반영.
- 신규 env `SECTOR_BOARD_INTRADAY_NEWS_ENABLED`는 host(flask-star) `render.yaml`에 추가해 켠다(기본 OFF라 안 넣으면 무영향).
- 네이버 키(`NAVER_CLIENT_ID/SECRET`)는 이미 `src/config.get_naver_credentials` 경로 — Render env 확인 필요.
