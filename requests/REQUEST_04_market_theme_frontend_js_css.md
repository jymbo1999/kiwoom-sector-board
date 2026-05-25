# REQUEST_04: 주도테마 정보판 — JS 렌더링, ECharts Treemap, CSS 구현

## 전제

REQUEST_01, REQUEST_02, REQUEST_03 결과를 먼저 읽고 따른다.

이번 단계의 목표는 대시보드 화면이 실제로 동작하도록 만드는 것이다.

즉, 더미 API를 호출해서 다음이 보이게 한다.

- 상단 시장 요약
- 중앙 테마 treemap
- 우측 선택 테마 대장주 Top 5
- 하단 테마 지속성 타임라인
- 자동 새로고침

## 목표 파일

프로젝트 구조에 맞게 조정하되, 후보는 다음과 같다.

```text
static/assets/js/market_theme_dashboard.js
static/assets/css/market_theme_dashboard.css
```

## JS 동작 흐름

페이지 로드 시 다음 순서로 동작하게 하라.

1. `/api/market/summary` 호출
2. `/api/market/themes/heatmap` 호출
3. 받은 데이터로 ECharts treemap 렌더링
4. 가장 점수가 높은 테마를 기본 선택
5. 선택된 테마에 대해 `/api/market/themes/<theme_id>/leaders` 호출
6. 우측 Top 5 패널 업데이트
7. `/api/market/themes/timeline?days=5` 호출
8. 하단 타임라인 렌더링
9. 일정 주기로 자동 새로고침

## 자동 새로고침

market_phase에 따라 나중에 다르게 설정할 수 있도록 구조를 만든다.

기본값은 30초로 둔다.

향후 기준:

- `pre_market`: 60초
- `regular_market`: 10~30초
- `after_market`: 60초
- `closed`: 수동 새로고침만

초기 구현에서는 30초 통일도 가능하다.

## ECharts treemap 규칙

각 사각형은 하나의 테마를 의미한다.

표현 규칙:

- 크기: `total_trading_value`
- 색상: `avg_change_pct`
- opacity 또는 진하기: `advance_ratio`
- 내부 텍스트: 테마명, 평균등락률, 대표 대장주 1~2개

## 한국 주식 색상 규칙

한국 주식 사용자 기준으로 표현한다.

- 상승: 빨강 계열
- 하락: 파랑 계열
- 보합: 중립 회색 계열

단, 기존 프로젝트 CSS 변수나 색상 체계가 있으면 그것을 우선 사용한다.

## Treemap 클릭 이벤트

사용자가 특정 테마를 클릭하면 다음을 수행한다.

1. 선택 테마 상태 저장
2. `/api/market/themes/<theme_id>/leaders` 호출
3. 우측 패널 갱신
4. 선택된 테마가 시각적으로 구분되게 처리

## 우측 대장주 Top 5 표시 항목

각 종목에 대해 다음을 표시한다.

- 순위
- 종목명
- 종목코드
- 등락률
- 현재가
- 거래대금
- 거래량 증가율
- 시가총액
- 상한가 여부
- leader_score
- 키워드

예시 표시:

```text
1. 삼화콘덴서 +29.94%
   거래대금 610억 | 상한가 | MLCC
```

## 거래대금 포맷

JS 또는 API 응답에서 다음 단위로 읽기 쉽게 표시하라.

- 억
- 조

가능하면 backend `format_trading_value`가 있으면 그것을 활용한다.

없으면 frontend에 안전한 formatter를 둔다.

## 타임라인 렌더링

다음 형태 중 프로젝트에 맞는 간단한 방식을 선택한다.

### 텍스트형

```text
05/18  반도체 → 우주항공 → 태양광
05/19  양자/보안 → 방산 → 백신
```

### 압축 막대형

```text
반도체     █ █ █ █ █
2차전지    ░ ░   █
로봇        ░ █
```

초기에는 텍스트형으로 충분하다.

## CSS 원칙

대시보드 전용 class prefix를 사용해 기존 페이지와 충돌하지 않게 하라.

권장 prefix:

```text
.market-theme-dashboard
.market-theme-summary
.market-theme-main
.market-theme-treemap
.market-theme-leader-panel
.market-theme-timeline
```

## 디자인 원칙

- 한 화면에서 오늘의 주도 테마가 즉시 보여야 한다.
- 단순 표보다 카드/히트맵 중심으로 구성한다.
- 데스크톱 정보판 우선이다.
- 글자는 너무 작게 만들지 않는다.
- 숫자에는 단위를 붙인다.
- API 실패 시 빈 화면이 아니라 오류 메시지 또는 fallback 메시지를 보여준다.

## 오류 처리

다음 상황을 처리하라.

- API 응답 실패
- leaders API에서 theme_id를 찾지 못함
- ECharts가 로드되지 않음
- heatmap data가 빈 배열임
- timeline data가 빈 배열임

## 검증

가능하면 다음을 수행하라.

- 새 페이지 접속
- 브라우저 console error 확인
- treemap 표시 확인
- 테마 클릭 시 우측 Top 5 변경 확인
- 자동 새로고침이 중복 timer를 만들지 않는지 확인
- 기존 페이지 CSS 깨짐 여부 확인

가능한 명령:

```bash
python -m py_compile apps/market/routes.py
python -m py_compile apps/market/services.py
```

## 완료 보고 형식

```markdown
## 완료 요약
- 구현한 JS 기능:
- 구현한 CSS:
- 사용한 차트 라이브러리:
- API 호출 흐름:

## 검증 결과
- 실행한 명령:
- 성공/실패:
- 브라우저 확인 항목:
- 남은 문제:

## 다음 단계
- REQUEST_05에서 메뉴 연결, 최종 검증, 문서화
```

## 제한

- 실제 주식 API 연결 금지.
- 대규모 프론트엔드 프레임워크 도입 금지.
- 기존 CSS를 광범위하게 수정하지 않는다.
- 기존 페이지 레이아웃을 깨지 않는다.
