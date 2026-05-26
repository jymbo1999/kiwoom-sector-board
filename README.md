# kiwoom-sector-board

키움증권 REST API 기반으로 매일 아침 한국 주식시장 장 시작 후 "오늘의 주도섹터"와 "섹터별 대장주 TOP 5"를 확인하는 로컬 Streamlit 대시보드입니다.

이 프로젝트는 자동매매가 아닌 조회 전용 MVP입니다. 주문 API, 매수/매도 버튼, 계좌정보 출력 기능은 구현하지 않습니다.

## 주요 기능

- 키움 REST API 접근토큰 발급 구조
- 국내주식 현재가/등락률/거래량/거래대금 REST polling 조회 구조
- `theme_map.csv` 기반 다중 테마 매핑
- 섹터 강도 점수 계산
- 섹터별 대장주 TOP 5 선정
- API 실패 또는 Mock/Dummy 모드에서 `sample_prices.csv` fallback
- Streamlit + Plotly treemap 기반 테마 흐름 표시
- 향후 WebSocket 실시간화가 쉽도록 Kiwoom adapter 분리

## macOS Apple Silicon 설치

Python 3.11 환경을 권장합니다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## Render 배포 설정

Render Web Service 기준 설정값입니다.

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

실제 Kiwoom API 연결 전에는 환경변수 `USE_DUMMY_DATA=true`를 유지하면 `data/sample_prices.csv`로 화면을 확인할 수 있습니다.

## .env / Render 환경변수

`.env.example`을 `.env`로 복사한 뒤 값을 채웁니다. Render에서는 같은 이름을 Environment Variables에 등록합니다.

```dotenv
KIWOOM_APP_KEY=
KIWOOM_APP_SECRET=
KIWOOM_BASE_URL=
KIWOOM_ACCOUNT_NO=
USE_DUMMY_DATA=true
```

호환을 위해 기존 이름도 계속 지원합니다.

```dotenv
KIWOOM_SECRET_KEY=
KIWOOM_USE_MOCK=true
```

- `KIWOOM_APP_KEY`: 향후 Kiwoom REST API App Key입니다.
- `KIWOOM_APP_SECRET`: 향후 Kiwoom REST API Secret입니다. 기존 `KIWOOM_SECRET_KEY`도 fallback으로 읽습니다.
- `KIWOOM_ACCOUNT_NO`: 이번 조회 전용 MVP에서는 사용하지 않으며, 화면에도 출력하지 않습니다. 향후 계좌 기반 조회 확장 대비용 자리입니다.
- `USE_DUMMY_DATA`: `true`이면 실제 API를 호출하지 않고 더미 데이터로 실행합니다. 기존 `KIWOOM_USE_MOCK`도 fallback으로 읽습니다.
- `KIWOOM_BASE_URL`: 비워두면 더미 모드에서는 `https://mockapi.kiwoom.com`, 실제 모드에서는 `https://api.kiwoom.com` 기본값을 사용합니다.

민감정보는 README, 코드, 커밋에 넣지 말고 `.env` 또는 Render 환경변수에만 저장합니다.

## Dummy/Mock 모드 실행

첫 실행은 Dummy/Mock 모드가 기본입니다.

```dotenv
USE_DUMMY_DATA=true
```

이 경우 키움 API를 호출하지 않고 `data/sample_prices.csv`를 사용합니다. 샘플 데이터는 화면과 계산 로직 검증용 임의 데이터이며 투자 추천이 아닙니다.

## 실제 API 모드 전환

키움 REST API 사용신청 후 App Key와 Secret을 `.env` 또는 Render 환경변수에 입력하고 Dummy 모드를 끕니다.

```dotenv
KIWOOM_APP_KEY=your_app_key
KIWOOM_APP_SECRET=your_secret
KIWOOM_BASE_URL=https://api.kiwoom.com
USE_DUMMY_DATA=false
```

모의투자 도메인을 사용할 때는 `KIWOOM_BASE_URL=https://mockapi.kiwoom.com`로 설정합니다.

## 키움 REST API 구현 메모

공식 가이드 기준으로 OAuth 접근토큰 발급은 `POST /oauth2/token`이며, 주식기본정보요청은 `api-id: ka10001`, `POST /api/dostk/stkinfo`, body `{"stk_cd": "005930"}` 형식입니다.

키움 응답 필드는 `cur_prc`, `flu_rt`, `trde_qty`처럼 약어를 사용하므로 `src/kiwoom_client.py`에서 앱 표준 컬럼으로 정규화합니다. 실제 운영 전에는 다운로드한 최신 공식 명세서로 `trde_prica`, `open_pric` 등 세부 필드명을 재확인해야 하며, 코드에 TODO와 명확한 예외처리를 남겼습니다.

## 섹터 점수

섹터 점수는 다음 요소를 사용합니다.

```text
sector_score =
  top5_change_rate_mean * 0.45
  + normalized_trade_value_sum * 0.30
  + rising_ratio * 20 * 0.15
  + limit_up_count * 2.0
```

대장주 점수는 다음 요소를 사용합니다.

```text
leader_score =
  change_rate_rank_score * 0.45
  + trade_value_rank_score * 0.35
  + open_to_current_strength * 0.10
  + theme_representative_score * 0.10
```

MVP에서 `theme_representative_score`는 1.0 고정입니다. 향후 `theme_map.csv`에 대표성 점수 컬럼을 추가할 수 있도록 확장할 예정입니다.

## 향후 WebSocket 실시간화 계획

1차 MVP는 REST polling 방식입니다. 다음 단계에서는 `src/kiwoom_client.py` 옆에 WebSocket adapter를 추가하고, `market_data.py`가 동일한 표준 DataFrame 컬럼을 반환하도록 맞춰 Streamlit 화면과 랭킹 로직을 그대로 재사용합니다.

## 검증

```bash
python3 -m py_compile app.py src/*.py
python3 -m pytest -q
git diff --check
git status --short
```
