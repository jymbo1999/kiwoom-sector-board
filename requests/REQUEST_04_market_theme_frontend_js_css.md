## REQUEST_04 — Render 배포/마무리

```markdown
# REQUEST_04: 주도테마 정보판 — Render 배포 준비와 최종 검증

## 전제

REQUEST_01 ~ REQUEST_03 결과를 먼저 읽고 따른다.

이번 단계의 목표는 Streamlit 앱을 Render에 배포 가능한 상태로 정리하고 최종 검증하는 것이다.

## 확인할 파일

- requirements.txt
- README.md
- app.py
- src/config.py
- .gitignore

## Render 설정

Render Web Service 기준:

Build Command:

```bash
pip install -r requirements.txt

Start Command:

streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```


requirements.txt 확인

다음 의존성이 실제 코드 사용과 일치하는지 확인한다.

streamlit
pandas
plotly
requests
python-dotenv
pytest

사용하지 않는 무거운 패키지는 추가하지 않는다.

환경변수

실제 Kiwoom API 연결은 아직 하지 않는다.

다만 나중을 위해 다음 값이 필요한지 README에만 정리한다.

KIWOOM_APP_KEY
KIWOOM_APP_SECRET
KIWOOM_ACCOUNT_NO
USE_DUMMY_DATA

민감정보는 절대 코드에 넣지 않는다.

최종 검증
python -m py_compile app.py src/*.py
pytest -q
git diff --check
git status --short

가능하면 로컬에서:

streamlit run app.py
최종 성공 기준
Streamlit 앱이 실행된다.
주도테마 정보판이 보인다.
더미 데이터로 테마 treemap이 표시된다.
선택한 테마의 대장주 Top 5가 표시된다.
최근 테마 타임라인이 표시된다.
실제 Kiwoom API 없이도 Render에 배포 가능하다.
나중에 Kiwoom 실시간 데이터로 교체하기 쉬운 구조다.
제한
실제 Kiwoom API 연결 금지
DB 추가 금지
Flask 구조 추가 금지
민감정보 커밋 금지
대규모 리팩토링 금지

---