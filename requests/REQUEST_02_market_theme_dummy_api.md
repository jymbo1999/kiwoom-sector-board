# REQUEST_02: 주도테마 정보판 — 더미 데이터 서비스와 점수 계산 구현

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