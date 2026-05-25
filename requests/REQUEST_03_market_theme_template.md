## REQUEST_03 — Streamlit UI 구현

기존 REQUEST_03~04의 역할을 Streamlit용으로 합치면 됨.

```markdown
# REQUEST_03: 주도테마 정보판 — Streamlit 대시보드 UI 구현

## 전제

REQUEST_01, REQUEST_02 결과를 먼저 읽고 따른다.

이번 단계의 목표는 Streamlit 화면에서 주도테마 정보판이 실제로 보이게 하는 것이다.

## 목표 화면

app.py와 src/dashboard_components.py를 사용해 다음 영역을 구현한다.

1. 상단 시장 요약
2. 중앙 테마 treemap 또는 heatmap
3. 우측/하단 선택 테마 대장주 Top 5
4. 최근 5거래일 테마 지속성 타임라인
5. 데이터 기준 시각
6. market_phase 표시

## 권장 UI 구조

- st.set_page_config(layout="wide")
- st.columns로 메인 영역 구성
- st.metric으로 시장 요약 표시
- plotly.express.treemap 또는 plotly.graph_objects로 테마 treemap 표시
- st.dataframe 또는 st.table로 대장주 Top 5 표시
- st.expander 또는 st.container로 뉴스/키워드 표시
- st.caption으로 timestamp 표시

## Treemap 규칙

- 사각형 크기: total_trading_value
- 색상: avg_change_pct
- 텍스트: theme_name, avg_change_pct, 대표 대장주 1~2개
- 한국 주식 색상 관례를 고려하되 Plotly 기본 scale이 더 안정적이면 과도한 커스텀은 피한다.

## 선택 테마 처리

Streamlit에서는 JS click event가 복잡할 수 있으므로 초기 구현에서는 다음 방식 중 하나를 선택한다.

1. st.selectbox로 선택 테마를 고르게 한다.
2. treemap은 전체 흐름 표시용으로 두고, 우측 Top 5는 selectbox 선택값에 따라 바꾼다.

초기 MVP에서는 selectbox 방식을 우선한다.

## 자동 새로고침

Streamlit 기본만으로는 무리하게 실시간 refresh를 만들지 않는다.

가능하면 수동 새로고침 버튼을 먼저 둔다.

- st.button("새로고침")
- st.cache_data(ttl=30) 사용 가능 여부 검토

자동 새로고침이 필요하면 별도 라이브러리 도입 전에 보고한다.

## 오류 처리

다음 상황을 처리한다.

- 데이터 파일 없음
- theme_map.csv 컬럼 불일치
- 더미 데이터 비어 있음
- 선택한 theme_id에 leaders 없음
- Plotly 미설치
- Kiwoom 관련 환경변수 없음

## 검증

```bash
python -m py_compile app.py src/*.py
pytest -q
streamlit run app.py
```

## 브라우저에서 확인할 것:

시장 요약 표시
treemap 표시
selectbox로 테마 변경
Top 5 변경
타임라인 표시
오류 없이 Render 배포 가능한 구조 유지
제한
Flask route/template/static 파일 생성 금지
실제 Kiwoom API 연결 금지
DB migration 금지
대규모 프론트엔드 프레임워크 도입 금지
---

## 작업 실행 정리

### 1. 사용자 요청

Streamlit 화면에서 주도테마 정보판 MVP를 실제로 표시하고, REQUEST_02 view-model을 사용해 시장 요약·테마 흐름·선택 테마 Top 5·타임라인 영역을 구성한다.

### 2. 작업 범위

- `app.py`에서 `get_market_summary()`, `get_theme_heatmap()`, `get_theme_leaders()`, `get_theme_timeline()` 호출
- `src/dashboard_components.py`에 시장 요약 metric, treemap/fallback heatmap, Top 5, timeline 렌더 함수 추가
- 기존 카드형 섹터맵/관전표 UI는 접힌 expander로 유지
- 수동 새로고침과 Streamlit cache 유지

### 3. 관련 파일 후보

- `app.py`
- `src/dashboard_components.py`
- `src/market_data.py` (기존 함수 재사용)
- `requests/REQUEST_03_market_theme_template.md`

### 4. 리스크

- Plotly가 requirements에 없으므로 미설치 환경에서는 table fallback으로 표시한다.
- 최근 5거래일 실제 히스토리 데이터는 아직 없으므로 단일 스냅샷을 지속성처럼 과장하지 않는다.
- Flask route/template/static, DB, 실제 Kiwoom 연결, 대규모 프론트엔드 의존성은 추가하지 않는다.

### 5. 검증 계획

```bash
python -m py_compile app.py src/*.py
pytest -q
streamlit run app.py
git diff --check
git status --short
git diff --stat
```

### 6. 완료 기준

- 시장 요약, 기준 시각, `market_phase`가 보인다.
- 테마 treemap 또는 fallback heatmap이 보인다.
- selectbox 선택에 따라 Top 5가 바뀐다.
- 타임라인 영역은 데이터 부재를 안전하게 안내한다.
- 관련 검증이 통과하고 관련 파일만 커밋한다.
