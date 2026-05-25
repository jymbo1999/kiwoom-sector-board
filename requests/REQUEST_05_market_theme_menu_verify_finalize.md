# REQUEST_05: 주도테마 정보판 — 메뉴 연결, 최종 검증, 마무리

## 전제

REQUEST_01 ~ REQUEST_04 결과를 먼저 읽고 따른다.

이번 단계의 목표는 새 기능을 실제 사용 가능한 메뉴에 연결하고, 전체 검증을 마무리하는 것이다.

## 목표

다음을 완료한다.

1. 사이드바 또는 navigation 메뉴에 새 항목 추가
2. 새 페이지 URL 접근 확인
3. API endpoint JSON 응답 확인
4. JS console 오류 확인
5. 기존 페이지 깨짐 여부 확인
6. 최종 작업 요약 작성

## 메뉴명

기존 프로젝트 메뉴 톤에 맞는 이름을 사용하라.

후보:

- 주도테마 정보판
- 시장 테마 대시보드
- 테마 히트맵

개인적으로는 사용자가 바로 이해하기 쉬운 **주도테마 정보판**을 우선 추천한다.

## URL

REQUEST_03에서 만든 URL을 메뉴에 연결한다.

후보:

```text
/market/themes
```

단, 실제 구현된 URL을 사용하라.

## 메뉴 연결 위치

기존 sidebar/menu 구조를 확인하고 가장 자연스러운 위치에 추가하라.

예상 후보 파일:

```text
templates/includes/sidebar.html
templates/includes/navigation.html
templates/home/sidebar.html
```

실제 프로젝트 구조에 맞게 찾는다.

## 권한/로그인 구조

기존 페이지들이 로그인 필요 여부를 가지고 있으면 그대로 따른다.

- login_required decorator 사용 여부
- blueprint 권한 구조
- sidebar active 상태 처리
- current page highlight 처리

## 최종 검증 항목

### 1. Python syntax check

가능하면 관련 파일을 모두 검사한다.

예시:

```bash
python -m py_compile apps/market/routes.py
python -m py_compile apps/market/services.py
python -m py_compile apps/market/dummy_data.py
python -m py_compile apps/market/scoring.py
python -m py_compile apps/home/routes.py
```

실제 파일 경로에 맞게 수정하라.

### 2. Flask route import check

앱이 정상 import되는지 확인한다.

프로젝트에 기존 smoke test 방식이 있으면 그것을 우선 사용한다.

예시:

```bash
python -c "from apps import create_app; app = create_app(); print('ok')"
```

실제 앱 팩토리 구조가 다르면 맞게 조정하라.

### 3. API endpoint 확인

가능하면 curl 또는 test client로 확인한다.

```bash
curl http://127.0.0.1:5000/api/market/summary
curl http://127.0.0.1:5000/api/market/themes/heatmap
curl http://127.0.0.1:5000/api/market/themes/semiconductor_mlcc/leaders
curl "http://127.0.0.1:5000/api/market/themes/timeline?days=5"
```

서버 포트가 다르면 프로젝트 설정에 맞게 조정하라.

### 4. 브라우저 확인

다음을 확인한다.

- 메뉴에서 새 페이지로 이동 가능
- 상단 시장 요약 표시
- 테마 treemap 표시
- 테마 클릭 시 우측 Top 5 변경
- 하단 타임라인 표시
- 데이터 기준 시각 표시
- JS console error 없음
- 기존 페이지 레이아웃 깨짐 없음

## 최종 성공 기준

이번 작업의 성공 기준은 다음과 같다.

- `/market/themes` 또는 실제 지정 URL에 접속하면 정보판이 보인다.
- 테마 히트맵이 보인다.
- 테마를 클릭하면 우측 Top 5가 바뀐다.
- 상단 시장 요약이 보인다.
- 하단 최근 테마 흐름이 보인다.
- 데이터는 더미지만 나중에 실제 API로 교체하기 쉬운 구조다.
- 기존 기능을 깨지 않았다.

## 완료 보고 형식

작업이 끝나면 반드시 아래 형식으로 보고하라.

```markdown
## 완료 요약
- 구현한 기능:
- 추가/수정 파일:
- 새 URL:
- 새 API:
- 사용한 차트 라이브러리:
- 더미 데이터 위치:

## 검증 결과
- 실행한 명령:
- 성공/실패:
- 확인한 URL:
- 확인한 API:
- 브라우저 확인:
- 남은 문제:

## 다음 단계 제안
1. Kiwoom API 실시간 데이터 연결
2. 뉴스/공시 키워드 자동 수집
3. 테마 분류 DB화
4. 대장주 점수 고도화
5. 장전/장중/장후 모드 분리
```

## 제한

- 실제 Kiwoom API 연결은 하지 않는다.
- 외부 뉴스 API 연결은 하지 않는다.
- DB migration은 하지 않는다.
- 대규모 리팩토링 금지.
- 이 기능과 직접 관련 없는 파일 수정 금지.
- 기존 메뉴 구조를 망가뜨리지 않는다.
