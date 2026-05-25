# REQUEST_01: 주도테마 정보판 — Streamlit 프로젝트 구조 분석만 수행

## 목표

현재 Streamlit 프로젝트 구조를 먼저 읽고, “주도섹터/테마 + 섹터별 대장주 Top 5 정보판”을 어떤 파일에 어떤 방식으로 붙일지 분석한다.

이 단계에서는 코드를 수정하지 않는다.

## 반드시 확인할 것

### 1. Streamlit 앱 구조

- app.py의 실행 흐름
- st.set_page_config 사용 여부
- sidebar 사용 여부
- layout wide 설정 여부
- src/dashboard_components.py의 역할
- 기존 chart/table/metric 컴포넌트 사용 여부

### 2. 데이터 계층

- src/market_data.py
- src/dummy_data.py
- src/theme_loader.py
- src/sector_ranker.py
- data/sample_prices.csv
- data/theme_map.csv

각 파일이 어떤 책임을 갖는지 확인한다.

### 3. 시각화 라이브러리

- Plotly 사용 여부
- Altair 사용 여부
- streamlit-echarts 사용 여부
- pandas dataframe/st.dataframe 사용 여부

없다면 Streamlit과 궁합이 좋은 Plotly treemap을 1순위 후보로 판단한다.

### 4. Kiwoom 관련 파일

- src/kiwoom_auth.py
- src/kiwoom_client.py
- src/kiwoom_websocket.py

이번 단계에서는 실제 Kiwoom API를 연결하지 않고, 나중에 연결 가능한 인터페이스만 분석한다.

## 산출물

- 현재 구조 요약
- 수정 예정 파일
- 유지해야 할 파일 책임
- Streamlit UI 배치 제안
- Plotly treemap 적용 가능성
- Render 배포 시 주의점

## 제한

- 코드 수정 금지
- 파일 생성 금지
- 실제 Kiwoom API 연결 금지
- 대규모 리팩토링 제안 금지