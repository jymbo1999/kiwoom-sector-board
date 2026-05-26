# REQUEST_migration.md

## 목표

현재 `kiwoom-sector-board`의 Streamlit 섹터/테마 대장주 보드를 기존 Render 배포 Flask 앱인 `flask-star-admin-master`(iChart)에 `/sector-board` 화면으로 얹는다.

단, iChart에 깊게 섞지 않는다. 나중에 `kiwoom-sector-board`를 별도 Flask 앱으로 독립 배포할 수 있도록, 섹터보드 기능은 이 레포 안의 독립 패키지로 유지한다.

## 현재 확인한 사실

- 현재 레포는 Streamlit 앱이다. 메인 진입점은 `app.py`.
- 현재 UI 렌더링은 `src/dashboard_components.py`, 데이터/랭킹은 `src/theme_loader.py`, `src/market_data.py`, `src/sector_ranker.py` 중심이다.
- 현재 스냅샷 저장은 `src/snapshot_service.py`에서 로컬 JSON과 선택적 R2 업로드를 처리한다.
- `app.py`는 `persist_morning_snapshot()`을 호출해 화면 렌더 이후 스냅샷을 저장한다.
- iChart Flask 앱은 `apps/__init__.py`의 `register_blueprints(app)`에서 기본 blueprint를 등록한다.
- iChart DB URL은 `DATABASE_URL`이 있으면 PostgreSQL, 없으면 SQLite로 동작한다.
- iChart 레포에는 Flask-Migrate 의존성은 있으나, 현재 확인 범위에서는 `migrations/` 디렉터리가 보이지 않는다. 런타임 schema 보정 로직도 존재한다.

## 핵심 설계 결정

`sector_board`는 "독립 Flask 앱이면서, 동시에 iChart에 mount 가능한 Blueprint 패키지"로 만든다.

iChart 쪽 변경은 원칙적으로 아래 두 종류만 허용한다.

1. `apps/__init__.py`에서 섹터보드 blueprint 등록
2. iChart navigation/sidebar 템플릿에 `/sector-board` 링크 추가

나머지 라우트, 템플릿, 정적 파일, DB repository, standalone 실행 진입점은 `kiwoom-sector-board/sector_board/` 안에 둔다.

## 선택한 아키텍처

```text
kiwoom-sector-board/
├── app.py                         # 기존 Streamlit 진입점 유지
├── src/
│   └── snapshot_service.py         # payload 생성은 유지, DB persist 호출만 추가
├── sector_board/
│   ├── __init__.py                 # create_app(), create_blueprint(), register helpers
│   ├── blueprint.py                # /, /api/snapshot, /health
│   ├── repository.py               # snapshot read/write, SQLAlchemy Core 또는 engine 기반
│   ├── schema.py                   # sector_snapshots DDL / idempotent ensure helper
│   ├── payload.py                  # payload validation/normalization
│   ├── auth.py                     # host login 연동 또는 no-auth 모드
│   ├── templates/sector_board/
│   └── static/sector_board/
├── standalone.py                   # 독립 Flask 실행 진입점
└── tests/
```

```text
flask-star-admin-master/
├── apps/__init__.py                # register_sector_board(app) 호출만 추가
└── templates/includes/sidebar.html # 또는 navigation.html에 링크 1개 추가
```

## DB 설계

테이블명: `sector_snapshots`

필드:

- `id`: primary key
- `snapshot_date`: date, unique
- `fetched_at`: datetime
- `summary_json`: JSON 또는 TEXT
- `themes_json`: JSON 또는 TEXT
- `leaders_json`: JSON 또는 TEXT
- `created_at`: datetime
- `updated_at`: datetime

운영 원칙:

- Streamlit/로컬 수집기가 Kiwoom API를 호출하고 DB에 write 한다.
- Flask/iChart 화면은 DB에서 read-only로 읽는다.
- 같은 날짜는 `snapshot_date` 기준 upsert 한다. 하루 여러 번 갱신해도 최신 1건만 유지한다.
- 환경변수는 `SECTOR_BOARD_DATABASE_URL`을 우선 사용한다.
- `SECTOR_BOARD_DATABASE_URL`이 없을 때만 host Flask의 `SQLALCHEMY_DATABASE_URI` 또는 기존 `DATABASE_URL`을 fallback으로 검토한다.
- production DB에 테이블을 실제 생성/변경하는 단계는 별도 확인 게이트로 둔다.

## 단계별 진행 계획

### Phase 0. 경계 확정 및 안전장치

- `REQUEST_migration.md`를 이 문서처럼 실행 기준 문서로 유지한다.
- iChart에 직접 model을 추가하는 방식은 보류한다.
- `sector_board` 패키지가 iChart의 `apps.models`, `apps.db`에 직접 의존하지 않는 것을 원칙으로 한다.
- DB schema 변경은 계획/DDL 준비까지만 먼저 진행하고, 실제 Render PostgreSQL 반영은 별도 단계에서 검증 후 진행한다.

완료 조건:

- 구현 범위가 `kiwoom-sector-board/sector_board/`, `src/snapshot_service.py`, iChart 등록 1곳, iChart 링크 1곳으로 제한된다.

### Phase 1. 독립 `sector_board` 패키지 골격 생성

- `sector_board/__init__.py`에 `create_app()`과 `create_blueprint()`를 만든다.
- `sector_board/blueprint.py`에 아래 라우트를 둔다.
  - `GET /`: 오늘 스냅샷 화면
  - `GET /api/snapshot`: 최신 스냅샷 JSON
  - `GET /health`: DB 연결과 최신 스냅샷 상태
- `sector_board/repository.py`는 Flask host와 독립 standalone 양쪽에서 같은 함수를 쓰게 만든다.
- `sector_board/schema.py`는 테이블 생성 SQL 또는 SQLAlchemy metadata를 한 곳에 둔다.
- `standalone.py`는 `sector_board.create_app()`만 실행한다.

완료 조건:

- `python -m py_compile standalone.py sector_board/*.py` 통과
- DB 없이도 앱 import가 실패하지 않음

### Phase 2. DB 저장 연결

- `src/snapshot_service.py`의 payload 생성 로직은 유지한다.
- `persist_morning_snapshot()` 끝에서 선택적으로 PostgreSQL 저장을 호출한다.
- DB URL이 없으면 지금처럼 로컬 JSON/R2 저장만 수행한다.
- DB 저장 실패는 Streamlit 앱 전체 실패로 전파하지 않고 결과 dict에 `postgres_status` 또는 `sector_db_status`로 표시한다.
- 저장 함수는 `sector_board.repository.upsert_snapshot(payload, database_url)`처럼 패키지 내부 API를 사용한다.

완료 조건:

- DB URL 미설정 시 기존 동작 유지
- SQLite 테스트 DB 또는 임시 PostgreSQL URL로 upsert 동작 검증
- 같은 날짜 재저장 시 1건만 유지

### Phase 3. Flask/Jinja 화면 제작

- `sector_board/templates/sector_board/index.html` 작성
- 기존 Streamlit 화면을 1:1 복제하기보다 서버 렌더링에 맞게 간결하게 재구성한다.
- 우선 제공할 화면:
  - 오늘 시장 요약
  - 상위 섹터 카드/표
  - 섹터별 대장주 테이블
  - 데이터 없음 상태
  - 마지막 갱신 시각
- CSS/JS는 `sector_board/static/sector_board/` 안에 둔다.
- iChart와 같이 붙을 때는 base layout을 선택적으로 상속할 수 있게 하고, standalone에서는 자체 base를 쓴다.

완료 조건:

- `/sector-board/` 또는 `/sector-board`에서 오늘 스냅샷 표시
- 스냅샷이 없으면 안내 화면 표시
- `/sector-board/api/snapshot`에서 JSON 확인 가능

### Phase 4. iChart에 mount

- iChart `apps/__init__.py`에서 register 단계에 섹터보드 등록 함수를 추가한다.
- 등록 코드는 직접 route를 만들지 않고 `sector_board` 패키지의 helper를 호출한다.
- iChart 로그인 연동은 `flask_login.current_user.is_authenticated` 기준으로 처리한다.
- 개발/독립 실행을 위해 `SECTOR_BOARD_NO_AUTH=1`이면 인증 없이 접근 가능하게 한다.
- iChart 템플릿의 navigation/sidebar에 `/sector-board` 링크를 추가한다.

완료 조건:

- iChart 로그인 후 `/sector-board` 접근 가능
- 로그인 전 접근 시 기존 로그인 흐름으로 redirect
- iChart에서 제거할 때는 blueprint 등록과 링크만 제거하면 됨

### Phase 5. Schema 반영 전략

선호 순서:

1. `sector_board/schema.py`에서 idempotent create table SQL 준비
2. 로컬/테스트 DB에서 schema 생성 검증
3. Render PostgreSQL에는 별도 SQL 또는 제한된 one-shot command로 적용
4. 자동 schema 생성은 `SECTOR_BOARD_AUTO_CREATE_TABLE=1` 같은 명시적 opt-in일 때만 허용

완료 조건:

- production DB 변경 전에 적용 SQL이 눈으로 검토 가능
- rollback이 필요한 경우 table drop이 아니라 기능 비활성화와 링크 제거로 우선 대응 가능

### Phase 6. 독립 배포 준비

- `standalone.py` 기준 gunicorn 실행 명령을 문서화한다.
- Render 독립 서비스용 환경변수 목록을 정리한다.
- iChart에서 떼어낼 때 필요한 체크리스트를 문서화한다.

분리 체크리스트:

- iChart `apps/__init__.py`의 섹터보드 등록 제거
- iChart navigation/sidebar 링크 제거
- 독립 Render 서비스에서 `standalone.py` 또는 gunicorn app target 사용
- 독립 DB를 쓸 경우 `SECTOR_BOARD_DATABASE_URL`만 교체

## 구현 시 건드릴 파일 예상

`kiwoom-sector-board`:

- `REQUEST_migration.md`
- `requirements.txt`
- `src/snapshot_service.py`
- `sector_board/__init__.py`
- `sector_board/blueprint.py`
- `sector_board/repository.py`
- `sector_board/schema.py`
- `sector_board/payload.py`
- `sector_board/auth.py`
- `sector_board/templates/sector_board/index.html`
- `sector_board/static/sector_board/sector_board.css`
- `standalone.py`
- `tests/test_sector_board_repository.py`
- `tests/test_sector_board_blueprint.py`

`flask-star-admin-master`:

- `apps/__init__.py`
- `templates/includes/sidebar.html` 또는 `templates/includes/navigation.html`
- 필요 시 `requirements.txt`

## 검증 계획

자동 검증:

```bash
python -m py_compile app.py src/*.py sector_board/*.py standalone.py
pytest -q
git diff --check
```

수동/스모크 검증:

```bash
streamlit run app.py
python standalone.py
```

iChart 통합 후:

```bash
python -m py_compile apps/__init__.py
```

브라우저 확인:

- Streamlit에서 스냅샷 저장 후 DB 저장 상태 표시
- standalone `/sector-board` 화면
- iChart 로그인 후 `/sector-board` 화면
- 스냅샷 없는 날의 no-data 화면

## 리스크와 대응

- production DB schema 변경 리스크: 자동 반영을 기본값으로 하지 않고 SQL 검토/명시 opt-in으로 처리한다.
- iChart coupling 리스크: `sector_board`가 `apps.db`, `apps.models`를 import하지 않게 한다.
- DB URL 혼동 리스크: `SECTOR_BOARD_DATABASE_URL`을 1순위로 쓰고, fallback은 명시적으로 문서화한다.
- Render cold start 리스크: Flask 화면은 Kiwoom API를 호출하지 않고 DB read-only로 유지한다.
- Streamlit 저장 실패 리스크: DB 저장 실패가 화면 렌더 실패로 번지지 않게 status만 반환한다.

## 구현 상태

2026-05-26 현재 Phase 1~4까지 1차 구현 완료.

- `sector_board` 독립 Flask 패키지 추가
- `standalone.py` 단독 실행 진입점 추가
- `src/snapshot_service.py`에서 선택적 DB upsert 연결
- `/sector-board`, `/sector-board/api/snapshot`, `/sector-board/health` 추가
- iChart `apps/__init__.py`에서 패키지를 찾을 수 있을 때만 blueprint 등록
- iChart sidebar 링크는 `SECTOR_BOARD_ENABLED`일 때만 표시
- packaging용 `pyproject.toml` 추가
- repository/blueprint 테스트 추가

남은 운영 작업:

- Render PostgreSQL에 `sector_snapshots` 테이블 반영 여부 결정
- Render 환경에서 `SECTOR_BOARD_DATABASE_URL`과 패키지 설치 경로 설정
- 실제 장중 Streamlit 수집 후 iChart `/sector-board` 화면 수동 확인
