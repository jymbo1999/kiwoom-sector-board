# REQUEST_02: 주도테마 정보판 — 더미 API와 서비스 레이어 구현

## 전제

REQUEST_01 분석 결과를 먼저 읽고 따른다.

이번 단계의 목표는 실제 주식 데이터 연동이 아니라, **더미 데이터 기반 API 구조**를 완성하는 것이다.

화면이 아직 없어도 된다.

## 목표

다음 API가 JSON을 반환하도록 구현한다.

1. `GET /api/market/summary`
2. `GET /api/market/themes/heatmap`
3. `GET /api/market/themes/<theme_id>/leaders`
4. `GET /api/market/themes/timeline?days=5`

라우팅 경로는 REQUEST_01 분석 결과에 따라 프로젝트 구조에 맞게 조정해도 된다.

단, 프론트엔드에서 쓰기 쉬운 형태로 일관되게 구성하라.

## 권장 파일 구조

프로젝트가 Flask 기반이면 아래 구조를 우선 검토하라.

```text
apps/market/
  __init__.py
  routes.py
  services.py
  dummy_data.py
  scoring.py
```

다만 실제 프로젝트 구조와 다르면 기존 패턴을 따른다.

## 더미 테마 목록

반드시 아래 테마를 포함하라.

- 반도체/MLCC
- 2차전지
- 제약/바이오
- 양자/광통신
- 신재생/SOFC
- OLED
- 로봇
- 방산
- 전선/전력설비

각 테마마다 최소 5개 종목을 넣어라.

## 데이터 설계 원칙

종목 하나가 여러 테마에 속할 수 있는 구조를 염두에 둔다.

예시:

```json
{
  "삼성전기": ["MLCC", "전장부품", "애플 밸류체인"],
  "주성엔지니어링": ["반도체 장비", "태양광 장비", "ALD"],
  "에코프로": ["2차전지", "양극재", "폐배터리"]
}
```

초기 구현에서는 DB 테이블을 만들지 말고, dummy data와 service layer로만 구성해도 된다.

## market_phase 설계

시장 시간대 구분값을 포함하라.

가능한 값:

- `pre_market`
- `regular_market`
- `after_market`
- `closed`

초기 구현에서는 서버 현재 시각 또는 단순 기본값으로 처리해도 된다.

중요한 것은 API 응답에 `market_phase` 필드가 존재하는 것이다.

## API 1: 시장 요약

### Endpoint

```http
GET /api/market/summary
```

### 반환 예시

```json
{
  "market_phase": "regular_market",
  "timestamp": "2026-05-22T09:12:00",
  "kospi_change_pct": 0.42,
  "kosdaq_change_pct": 1.15,
  "advance_count": 1248,
  "decline_count": 612,
  "limit_up_count": 18,
  "total_trading_value": 12400000000000,
  "top_themes": ["반도체/MLCC", "2차전지", "제약/바이오"]
}
```

## API 2: 테마 히트맵

### Endpoint

```http
GET /api/market/themes/heatmap
```

### 반환 예시

```json
[
  {
    "theme_id": "semiconductor_mlcc",
    "theme_name": "반도체/MLCC",
    "avg_change_pct": 12.4,
    "total_trading_value": 2100000000000,
    "advance_ratio": 0.82,
    "limit_up_count": 3,
    "theme_score": 88.2,
    "rank": 1,
    "previous_rank": 2,
    "persistence_score": 0.8,
    "leaders": ["삼화콘덴서", "주성엔지니어링"]
  }
]
```

## API 3: 특정 테마 대장주 Top 5

### Endpoint

```http
GET /api/market/themes/<theme_id>/leaders
```

### 반환 예시

```json
{
  "theme_id": "semiconductor_mlcc",
  "theme_name": "반도체/MLCC",
  "leaders": [
    {
      "rank": 1,
      "stock_code": "001820",
      "stock_name": "삼화콘덴서",
      "change_pct": 29.94,
      "price": 58500,
      "trading_value": 61000000000,
      "volume_ratio": 7.2,
      "market_cap": 608000000000,
      "is_limit_up": true,
      "leader_score": 92.1,
      "keywords": ["MLCC", "상한가", "수요회복"]
    }
  ]
}
```

## API 4: 테마 지속성 타임라인

### Endpoint

```http
GET /api/market/themes/timeline?days=5
```

### 반환 예시

```json
[
  {
    "date": "2026-05-18",
    "top_themes": ["반도체", "우주항공", "태양광"]
  },
  {
    "date": "2026-05-19",
    "top_themes": ["양자/보안", "방산", "백신"]
  }
]
```

## 점수 계산 함수

다음 함수는 service layer 또는 scoring module로 분리하라.

```python
def calculate_theme_score(theme_snapshot):
    """
    테마 점수를 계산한다.
    단순 상승률이 아니라 거래대금, 상승확산도, 상한가 수, 지속성을 함께 본다.
    """
    pass


def calculate_leader_score(stock_snapshot):
    """
    대장주 점수를 계산한다.
    상승률 1위가 아니라 거래대금과 장중 강도를 함께 본다.
    """
    pass


def format_trading_value(value):
    """
    거래대금을 조/억 단위로 포맷팅한다.
    """
    pass
```

초기에는 단순 가중합으로 충분하다.

### 테마 점수 예시

```python
theme_score = (
    avg_change_pct * 0.30
    + trading_value_score * 0.30
    + advance_ratio * 0.20
    + limit_up_count_score * 0.10
    + persistence_score * 0.10
)
```

### 대장주 점수 예시

```python
leader_score = (
    change_pct * 0.25
    + trading_value_score * 0.35
    + volume_spike_score * 0.15
    + intraday_strength_score * 0.15
    + theme_centrality_score * 0.10
)
```

## 검증

가능하면 다음을 수행하라.

```bash
python -m py_compile apps/market/routes.py
python -m py_compile apps/market/services.py
python -m py_compile apps/market/dummy_data.py
python -m py_compile apps/market/scoring.py
```

실제 파일 경로가 다르면 프로젝트에 맞게 수정해서 실행하라.

가능하면 Flask test client 또는 curl로 API JSON 응답도 확인하라.

## 완료 보고 형식

```markdown
## 완료 요약
- 구현한 API:
- 추가 파일:
- 수정 파일:
- 더미 데이터 위치:
- scoring 함수 위치:

## 검증 결과
- 실행한 명령:
- 성공/실패:
- 확인한 endpoint:

## 다음 단계
- REQUEST_03에서 템플릿 화면 생성
```

## 제한

- 실제 Kiwoom API 연결 금지.
- DB migration 금지.
- 화면 템플릿 구현은 하지 않는다.
- template 안에 dummy data를 직접 넣지 않는다.
- JS 파일에 더미 데이터를 하드코딩하지 않는다.
