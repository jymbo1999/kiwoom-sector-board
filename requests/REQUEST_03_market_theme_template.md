# REQUEST_03: 주도테마 정보판 — 화면 템플릿 생성

## 전제

REQUEST_01, REQUEST_02 결과를 먼저 읽고 따른다.

이번 단계의 목표는 더미 API를 소비할 수 있는 **대시보드 페이지 템플릿**을 만드는 것이다.

아직 JS 렌더링이 완벽하지 않아도 되지만, HTML 구조는 최종 UI를 고려해 잡는다.

## 목표

새 페이지를 만든다.

후보 URL:

```text
/market/themes
```

단, REQUEST_01 분석 결과에서 더 자연스러운 URL이 있으면 그것을 따른다.

## 화면 구조

다음 구조를 기준으로 만든다.

```text
┌──────────────────────────────────────────────┐
│ 오늘 시장 요약: 지수 / 상승종목수 / 하락종목수 / 거래대금 / 상한가 │
├──────────────────────────────┬───────────────┤
│                              │ 선택 테마 정보 │
│      테마 히트맵 / 트리맵       │               │
│                              │ 대장주 Top 5   │
│  크기 = 거래대금              │ 등락률          │
│  색 = 평균등락률              │ 거래대금        │
│  진하기 = 상승 종목 비율       │ 거래량 증가율    │
│                              │ 뉴스 키워드      │
├──────────────────────────────┴───────────────┤
│ 최근 5거래일 테마 지속성 타임라인 / 순위 변화 │
└──────────────────────────────────────────────┘
```

## 필요한 영역

### 1. 상단 시장 요약 카드

표시할 자리만 만든다.

- KOSPI 등락률
- KOSDAQ 등락률
- 상승 종목 수
- 하락 종목 수
- 상한가 종목 수
- 전체 거래대금
- 가장 강한 테마 1~3개
- 데이터 기준 시각
- market phase 표시

HTML에는 JS가 채울 수 있도록 id 또는 data attribute를 둔다.

예시:

```html
<span id="market-phase"></span>
<span id="market-timestamp"></span>
```

### 2. 중앙 테마 히트맵 / 트리맵 영역

ECharts가 붙을 수 있는 container를 만든다.

예시:

```html
<div id="theme-treemap" class="theme-treemap"></div>
```

이 영역이 화면에서 가장 중요하게 보이도록 배치한다.

### 3. 우측 선택 테마 + 대장주 Top 5 패널

히트맵에서 테마를 클릭하면 JS가 내용을 채울 수 있도록 구조를 만든다.

필수 영역:

- 선택된 테마명
- 테마 평균 등락률
- 테마 거래대금
- 상승 종목 비율
- 대장주 Top 5 list
- 뉴스/재료 키워드

예시:

```html
<h3 id="selected-theme-name">테마 선택 대기</h3>
<div id="leader-list"></div>
<div id="theme-keywords"></div>
```

### 4. 하단 테마 지속성 타임라인

최근 5거래일 흐름을 표시할 영역을 만든다.

예시:

```html
<div id="theme-timeline"></div>
```

## 템플릿 구현 원칙

- 기존 base/layout template을 상속한다.
- 기존 프로젝트의 카드, grid, container 스타일을 최대한 따른다.
- 새 class는 prefix를 붙인다.

권장 prefix:

```text
market-theme-dashboard
market-theme-summary
market-theme-main
market-theme-treemap
market-theme-leader-panel
market-theme-timeline
```

## JS/CSS 연결

이번 단계에서 JS/CSS 파일을 실제로 만들지 않아도 되지만, 만들 예정 경로를 template에 연결해도 된다.

권장 후보:

```text
static/assets/js/market_theme_dashboard.js
static/assets/css/market_theme_dashboard.css
```

프로젝트의 기존 static 경로 규칙이 다르면 그 규칙을 따른다.

## ECharts 로딩

프로젝트 정책상 CDN 사용이 가능하면 template에 ECharts CDN을 추가할 수 있다.

예시:

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
```

다만 기존 프로젝트가 외부 CDN을 피하는 구조라면 static vendor 방식으로 계획만 남겨라.

## 라우트 연결

페이지 렌더링 route를 추가하라.

예시:

```python
@blueprint.route("/market/themes")
def market_theme_dashboard():
    return render_template("home/market_theme_dashboard.html")
```

실제 blueprint 이름과 template 경로는 프로젝트에 맞게 조정하라.

## 검증

가능하면 다음을 수행하라.

```bash
python -m py_compile apps/home/routes.py
python -m py_compile apps/market/routes.py
```

그리고 Flask 앱에서 새 URL이 200으로 뜨는지 확인하라.

## 완료 보고 형식

```markdown
## 완료 요약
- 새 페이지 URL:
- 추가 template:
- 수정 route:
- 연결 예정 JS:
- 연결 예정 CSS:

## 검증 결과
- 실행한 명령:
- 성공/실패:
- 새 페이지 렌더링 여부:

## 다음 단계
- REQUEST_04에서 JS 렌더링과 ECharts treemap 구현
```

## 제한

- 이 단계에서는 복잡한 JS 구현을 하지 않는다.
- dummy data를 template 안에 직접 박지 않는다.
- 기존 layout을 깨지 않는다.
- 사이드바 메뉴 연결은 REQUEST_05에서 처리한다.
