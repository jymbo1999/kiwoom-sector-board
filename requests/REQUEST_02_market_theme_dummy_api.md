# REQUEST_02: 주도테마 정보판 — 더미 데이터 서비스와 점수 계산 구현

## 사용자 요청

Streamlit 대시보드에서 다음 단계 UI가 안정적으로 소비할 수 있는 더미-safe 시장/테마 view-model 계층을 구현한다.
실제 Kiwoom API를 더미 모드에서 호출하지 않고, 기존 데이터 흐름을 재사용한다.

## 작업 범위

- `get_market_summary()` 추가
- `get_theme_heatmap()` 추가
- `get_theme_leaders(theme_id)` 추가
- `get_theme_timeline(days=5)` 추가
- 기존 `load_settings() -> load_theme_map() -> load_market_prices() -> rank_sectors()` 흐름 재사용
- 현재 `app.py` UI는 변경하지 않음
- 새 view-model 함수 테스트 추가

## 관련 파일 후보

- `src/market_data.py`
- `src/sector_ranker.py`
- `src/dummy_data.py`
- `src/theme_loader.py`
- `tests/test_market_data_view_models.py`

## 리스크

- 더미 모드에서 실제 Kiwoom API가 호출되면 안 된다.
- 현 단계에서 실제 과거 시계열 데이터가 있는 것처럼 표현하면 안 된다.
- Flask route/template/static JS/CSS, DB, Plotly 의존성은 추가하지 않는다.

## 검증 계획

```bash
python -m py_compile app.py src/*.py
python -m pytest -q
git diff --check
git status --short
git diff --stat
```

## 완료 기준

- 네 view-model 함수가 안정적인 key/column 스키마를 반환한다.
- mock 모드 heatmap 데이터가 비어 있지 않다.
- 유효 theme_id 대장주는 최대 5개만 반환한다.
- 알 수 없는 theme_id는 안정적인 빈 DataFrame을 반환한다.
- timeline은 빈 DataFrame이거나 `is_dummy_timeline=True`로 명시된 더미 행만 반환한다.
- 검증 명령이 통과하고 관련 파일만 커밋한다.

---

## 전제

REQUEST_01 분석 결과를 먼저 읽고 따른다.

이번 단계의 목표는 실제 Kiwoom 데이터 연동이 아니라, Streamlit UI에서 바로 호출 가능한 데이터 서비스 함수를 완성하는 것이다.

## 목표 함수

다음 함수들이 안정적으로 동작하게 한다.

- get_market_summary()
- get_theme_heatmap()
- get_theme_leaders(theme_id)
- get_theme_timeline(days=5)

권장 위치:

- src/market_data.py
- src/sector_ranker.py
- src/dummy_data.py
- src/theme_loader.py

## 더미 테마 목록

반드시 아래 테마를 포함한다.

- 반도체/MLCC
- 2차전지
- 제약/바이오
- 양자/광통신
- 신재생/SOFC
- OLED
- 로봇
- 방산
- 전선/전력설비

각 테마마다 최소 5개 종목을 포함한다.

## 데이터 설계 원칙

종목 하나가 여러 테마에 속할 수 있게 설계한다.

data/theme_map.csv가 이미 있으면 그것을 우선 사용한다.
없거나 부족하면 src/dummy_data.py에서 fallback dummy mapping을 제공한다.

## market_phase

시장 시간대 구분값을 포함한다.

가능한 값:

- pre_market
- regular_market
- after_market
- closed

초기 구현에서는 서버 현재 시각 기준 또는 단순 기본값으로 처리해도 된다.

## 점수 계산

다음 계산 책임을 src/sector_ranker.py에 둔다.

- calculate_theme_score(theme_snapshot)
- calculate_leader_score(stock_snapshot)
- format_trading_value(value)

테마 점수는 단순 상승률이 아니라 다음을 함께 본다.

- 평균 등락률
- 거래대금
- 상승 종목 비율
- 상한가 수
- 지속성

대장주 점수는 다음을 함께 본다.

- 등락률
- 거래대금
- 거래량 증가율
- 장중 강도
- 테마 중심성

## 검증

다음 명령을 실행한다.

```bash
python -m py_compile app.py src/*.py
pytest -q
```

## 제한

실제 Kiwoom API 연결 금지
DB 추가 금지
Flask route 추가 금지
Streamlit UI 구현은 REQUEST_03에서 처리
