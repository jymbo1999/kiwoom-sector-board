# REQUEST_01: 주도테마 정보판 — 프로젝트 구조 분석만 수행

## 목표

현재 프로젝트 구조를 먼저 읽고, “주도섹터/테마 + 섹터별 대장주 Top 5 정보판”을 어디에, 어떤 방식으로 붙일지 분석한다.

이 단계에서는 **코드를 수정하지 않는다.**

최종 기능 목표는 다음 화면이다.

- 상단: 오늘 시장 요약
- 중앙: 테마/섹터 히트맵 또는 트리맵
- 우측: 선택된 테마의 대장주 Top 5
- 하단: 최근 며칠간 테마 지속성 타임라인
- 보조 영역: 뉴스/공시/재료 키워드

## 반드시 확인할 것

### 1. 프론트엔드 구조

다음을 확인하라.

- Flask template 기반인지
- React/Vite/Next.js 등이 있는지
- 기존 dashboard template이 있는지
- template inheritance 구조
- sidebar/menu 구조
- static JS/CSS 구조
- 기존 UI 스타일과 색상 체계

### 2. 시각화 라이브러리 사용 여부

프로젝트에서 이미 사용 중인 차트 라이브러리가 있는지 확인하라.

- Chart.js
- Plotly
- Apache ECharts
- D3
- Recharts
- 기타

이미 쓰는 라이브러리가 있으면 그것을 우선 검토하라.

없다면, 이번 기능은 **Apache ECharts treemap**을 1순위 후보로 판단하라.

이유:

- treemap 구현이 쉽다.
- Flask template에서도 CDN으로 붙이기 쉽다.
- tooltip, click event, color mapping 구현이 쉽다.
- 금융형 대시보드에 적합하다.

### 3. 백엔드 구조

다음을 확인하라.

- Flask route 구조
- Blueprint 사용 여부
- API endpoint 구조
- DB 모델 구조
- service layer가 있는지
- 기존 stock 관련 코드가 있는지
- Kiwoom API, pykrx, yfinance, FinanceDataReader, OpenDART, 뉴스 API 연결 코드가 있는지

### 4. 데이터 저장 방식

다음을 확인하라.

- SQLite인지
- PostgreSQL인지
- 기존 stock 관련 테이블이 있는지
- 없다면 이번 초기 구현은 DB 없이 dummy service로 가능한지

## 분석해야 할 기능 구조

이번 기능은 다음 질문에 답해야 한다.

1. 오늘 시장에서 가장 강한 테마는 무엇인가?
2. 그 테마 안에서 진짜 대장주는 무엇인가?
3. 이 테마가 오늘 처음 뜬 것인가, 며칠째 이어지는가?
4. 상승률만 높은 종목인지, 거래대금까지 동반된 진짜 주도주인지?
5. 관련 뉴스/재료는 무엇인가?

## 추천 URL 후보

기존 라우팅 규칙을 보고 가장 자연스러운 URL을 제안하라.

후보:

- `/market/themes`
- `/dashboard/market-themes`
- `/theme-dashboard`

## 추천 메뉴명 후보

기존 사이드바 톤에 맞춰 메뉴명을 제안하라.

후보:

- 주도테마 정보판
- 시장 테마 대시보드
- 테마 히트맵

## 산출물

작업 후 아래 형식으로 보고하라.

```markdown
## 분석 결과

### 프로젝트 구조 요약
- 프론트엔드:
- 백엔드:
- 라우팅 방식:
- 템플릿 구조:
- static 구조:
- DB 구조:

### 기존 차트 라이브러리
- 발견 여부:
- 추천 라이브러리:
- 이유:

### 수정 예정 파일
- 새로 만들 파일:
- 수정할 파일:

### 권장 구현 구조
- URL:
- Blueprint 또는 route 위치:
- template 위치:
- JS 위치:
- CSS 위치:
- dummy data 위치:

### 주의할 점
- 기존 기능과 충돌 가능성:
- 인증/로그인 관련 고려:
- 배포 환경 관련 고려:
```

## 제한

- 코드 수정 금지.
- 파일 생성 금지.
- 분석만 수행.
- 대규모 리팩토링 제안 금지.
- 기존 프로젝트 구조를 우선한다.
