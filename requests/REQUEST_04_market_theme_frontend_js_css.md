# REQUEST_04: 주도테마 정보판 — Render 배포 준비와 최종 검증

## 1. 사용자 요청

- 기존 Streamlit 주도테마 정보판을 Render Web Service에 배포 가능한 상태로 정리한다.
- 실제 Kiwoom API 연결 없이 더미 데이터로 treemap, 선택 테마 대장주 Top 5, 최근 테마 타임라인 영역이 확인 가능해야 한다.
- 민감정보를 코드에 넣지 않고 향후 Kiwoom 실시간 데이터로 교체하기 쉬운 구조를 유지한다.

## 2. 작업 범위

- Render Build/Start Command 문서화
- `requirements.txt` 의존성과 실제 코드 사용 일치 확인
- 환경변수 이름과 mock/dummy 실행 방법 정리
- 기존 Streamlit 구조 유지 및 Flask/DB 추가 금지
- 최종 검증 명령 실행

## 3. 관련 파일 후보

- `requirements.txt`
- `README.md`
- `.env.example`
- `.gitignore`
- `app.py`
- `src/config.py`
- `src/dashboard_components.py`
- `src/market_data.py`

## 4. 리스크

- `plotly` 누락 시 Render에서 treemap 대신 fallback 표가 표시될 수 있음
- README 환경변수와 실제 코드 환경변수가 다르면 Render 설정자가 혼동할 수 있음
- 실제 Kiwoom API 키/시크릿을 커밋하면 안 됨
- 실제 과거 데이터가 없어 타임라인은 MVP 안내/스키마 중심으로 표시됨

## 5. 검증 계획

```bash
python3 -m py_compile app.py src/*.py
python3 -m pytest -q
git diff --check
git status --short
git diff --stat
```

가능하면 로컬 smoke:

```bash
streamlit run app.py
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

## 6. 완료 기준

- Streamlit 앱이 더미 데이터 기본값으로 실행 가능
- Render Build Command와 Start Command가 문서화됨
- `plotly` 포함 의존성이 실제 UI 코드와 일치
- `KIWOOM_APP_KEY`, `KIWOOM_APP_SECRET`, `KIWOOM_ACCOUNT_NO`, `USE_DUMMY_DATA` 관련 안내가 README에 있음
- 기존 `KIWOOM_SECRET_KEY`, `KIWOOM_USE_MOCK` 사용자도 깨지지 않음
- 실제 Kiwoom API 연결, DB, Flask 구조, 민감정보 커밋 없음
