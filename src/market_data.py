from __future__ import annotations

from datetime import datetime, time
from typing import Any

import pandas as pd

from .config import Settings, load_settings
from .dummy_data import load_sample_prices
from .kiwoom_client import KiwoomApiError, KiwoomRestClient
from .sector_ranker import rank_sectors
from .theme_loader import load_theme_map


MARKET_SUMMARY_KEYS = [
    "timestamp",
    "market_phase",
    "data_mode",
    "effective_mock",
    "error_message",
    "theme_count",
    "stock_count",
    "top_theme",
    "top_theme_score",
    "avg_change_rate",
    "rising_ratio",
    "total_trade_value",
]

THEME_HEATMAP_COLUMNS = [
    "theme_id",
    "theme_name",
    "sector_score",
    "theme_score",
    "trade_value_sum",
    "total_trading_value",
    "market_cap",
    "rising_ratio",
    "stock_count",
    "top5_change_rate_mean",
    "leader_names",
    "badges",
]

THEME_LEADER_COLUMNS = [
    "rank",
    "theme_id",
    "theme_name",
    "code",
    "name",
    "change_rate",
    "current_price",
    "trade_value",
    "volume",
    "leader_score",
]

THEME_TIMELINE_COLUMNS = [
    "date",
    "rank_1_theme",
    "rank_2_theme",
    "rank_3_theme",
    "top_leader_stock",
    "top_leader_change_rate",
    "total_trading_value",
    "market_comment",
    "badges",
]

MARKET_MOVER_KEYS = [
    "ticker",
    "name",
    "market",
    "sector",
    "pct_change",
    "volume_rank",
    "trading_value",
]

MOCK_MARKET_MOVERS: list[dict[str, Any]] = [
    {
        "ticker": "000660",
        "name": "SK하이닉스",
        "market": "KOSPI",
        "sector": "반도체",
        "pct_change": 8.7,
        "volume_rank": 2,
        "trading_value": 684_200_000_000,
    },
    {
        "ticker": "064350",
        "name": "현대로템",
        "market": "KOSPI",
        "sector": "방산",
        "pct_change": 7.9,
        "volume_rank": 5,
        "trading_value": 312_800_000_000,
    },
    {
        "ticker": "042700",
        "name": "한미반도체",
        "market": "KOSPI",
        "sector": "반도체",
        "pct_change": 7.4,
        "volume_rank": 4,
        "trading_value": 278_500_000_000,
    },
    {
        "ticker": "247540",
        "name": "에코프로비엠",
        "market": "KOSDAQ",
        "sector": "2차전지",
        "pct_change": 6.8,
        "volume_rank": 7,
        "trading_value": 221_300_000_000,
    },
    {
        "ticker": "329180",
        "name": "HD현대중공업",
        "market": "KOSPI",
        "sector": "조선",
        "pct_change": 6.2,
        "volume_rank": 8,
        "trading_value": 198_400_000_000,
    },
    {
        "ticker": "207940",
        "name": "삼성바이오로직스",
        "market": "KOSPI",
        "sector": "바이오",
        "pct_change": 5.6,
        "volume_rank": 10,
        "trading_value": 174_600_000_000,
    },
    {
        "ticker": "277810",
        "name": "레인보우로보틱스",
        "market": "KOSDAQ",
        "sector": "로봇",
        "pct_change": 5.1,
        "volume_rank": 11,
        "trading_value": 143_900_000_000,
    },
    {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
        "sector": "AI",
        "pct_change": 4.8,
        "volume_rank": 1,
        "trading_value": 1_234_567_890_000,
    },
    {
        "ticker": "034020",
        "name": "두산에너빌리티",
        "market": "KOSPI",
        "sector": "원전",
        "pct_change": 4.3,
        "volume_rank": 3,
        "trading_value": 356_700_000_000,
    },
    {
        "ticker": "003670",
        "name": "포스코퓨처엠",
        "market": "KOSPI",
        "sector": "2차전지",
        "pct_change": 3.9,
        "volume_rank": 9,
        "trading_value": 166_200_000_000,
    },
    {
        "ticker": "012450",
        "name": "한화에어로스페이스",
        "market": "KOSPI",
        "sector": "방산",
        "pct_change": 3.5,
        "volume_rank": 6,
        "trading_value": 244_100_000_000,
    },
    {
        "ticker": "145020",
        "name": "휴젤",
        "market": "KOSDAQ",
        "sector": "바이오",
        "pct_change": 2.8,
        "volume_rank": 15,
        "trading_value": 88_300_000_000,
    },
]

THEME_HISTORY: list[dict] = [
    {
        "date": "2026-05-22",
        "weekday": "금",
        "themes": [
            {
                "theme": "반도체/MLCC 등",
                "reason": "미 필라델피아 반도체지수 강세 및 메모리 사이클 기대감 지속, 삼성전기·삼화콘덴서 실적 개선 전망",
                "leaders": [
                    {"name": "미래산업", "change": 29.89},
                    {"name": "피델릭스", "change": 29.95},
                    {"name": "삼화콘덴서", "change": 29.94},
                    {"name": "주성엔지니어링", "change": 20.95},
                    {"name": "삼성전기", "change": 11.30},
                ],
            },
            {
                "theme": "2차전지 관련주",
                "reason": "미국 IRA 보조금 재협상 기대 및 전기차 판매 회복세, 양극재·분리막 업체 수혜 전망",
                "leaders": [
                    {"name": "에코프로비엠", "change": 18.45},
                    {"name": "포스코퓨처엠", "change": 14.32},
                    {"name": "LG에너지솔루션", "change": 9.87},
                    {"name": "삼성SDI", "change": 8.21},
                    {"name": "엘앤에프", "change": 22.10},
                ],
            },
            {
                "theme": "제약/바이오",
                "reason": "국내 제약사 임상 3상 성공 소식 및 미 FDA 승인 기대감, 바이오시밀러 수출 모멘텀",
                "leaders": [
                    {"name": "셀트리온", "change": 7.45},
                    {"name": "한미약품", "change": 12.30},
                    {"name": "유한양행", "change": 6.78},
                    {"name": "보령", "change": 15.22},
                    {"name": "HLB", "change": 19.95},
                ],
            },
            {
                "theme": "양자/광통신 등",
                "reason": "미국 양자컴퓨팅 국가전략 발표 및 AI 데이터센터 광통신 수요 급증",
                "leaders": [
                    {"name": "우리로", "change": 29.82},
                    {"name": "이노와이어리스", "change": 25.14},
                    {"name": "쏠리드", "change": 21.33},
                    {"name": "RFHIC", "change": 18.60},
                    {"name": "오이솔루션", "change": 16.45},
                ],
            },
            {
                "theme": "신재생/SOFC",
                "reason": "정부 수소경제 로드맵 발표 및 고체산화물연료전지(SOFC) 상용화 가속, 태양광 REC 가격 상승",
                "leaders": [
                    {"name": "두산퓨얼셀", "change": 24.50},
                    {"name": "에스퓨얼셀", "change": 29.90},
                    {"name": "엘케이씨", "change": 18.70},
                    {"name": "한화솔루션", "change": 8.35},
                    {"name": "OCI홀딩스", "change": 11.20},
                ],
            },
            {
                "theme": "OLED(유기 발광 다이오드)",
                "reason": "애플 아이패드·맥북 OLED 패널 채택 확대 및 폴더블폰 수요 증가, 소재·장비 수혜",
                "leaders": [
                    {"name": "덕산네오룩스", "change": 22.75},
                    {"name": "피엔에이치테크", "change": 29.87},
                    {"name": "LG디스플레이", "change": 9.42},
                    {"name": "삼성디스플레이", "change": 7.80},
                    {"name": "이녹스첨단소재", "change": 15.33},
                ],
            },
        ],
    },
    {
        "date": "2026-05-21",
        "weekday": "목",
        "themes": [
            {
                "theme": "반도체 관련주",
                "reason": "HBM 공급망 확대 및 AI 서버용 메모리 수요 증가, 엔비디아 실적 호조 영향",
                "leaders": [
                    {"name": "SK하이닉스", "change": 8.90},
                    {"name": "한미반도체", "change": 18.45},
                    {"name": "테크윙", "change": 14.32},
                    {"name": "ISC", "change": 12.10},
                    {"name": "리노공업", "change": 9.67},
                ],
            },
            {
                "theme": "로봇 관련주",
                "reason": "테슬라 옵티머스 로봇 양산 일정 공개 및 국내 협동로봇 수출 계약 체결 소식",
                "leaders": [
                    {"name": "레인보우로보틱스", "change": 24.15},
                    {"name": "에스피지", "change": 19.88},
                    {"name": "티로보틱스", "change": 29.93},
                    {"name": "로보스타", "change": 16.40},
                    {"name": "현대로보틱스", "change": 11.25},
                ],
            },
            {
                "theme": "전선/전력설비",
                "reason": "미국 전력망 현대화 투자 확대 및 국내 송배전 설비 교체 수요 급증, 전선주 수주 호조",
                "leaders": [
                    {"name": "LS전선아시아", "change": 21.30},
                    {"name": "대한전선", "change": 18.75},
                    {"name": "가온전선", "change": 15.60},
                    {"name": "일진전기", "change": 12.45},
                    {"name": "서울전선", "change": 9.80},
                ],
            },
            {
                "theme": "지주사",
                "reason": "대기업 지주사 자사주 매입 및 배당 확대 정책 발표, 밸류업 프로그램 수혜 기대",
                "leaders": [
                    {"name": "SK", "change": 7.35},
                    {"name": "LG", "change": 6.42},
                    {"name": "한화", "change": 5.80},
                    {"name": "CJ", "change": 8.15},
                    {"name": "두산", "change": 9.30},
                ],
            },
        ],
    },
    {
        "date": "2026-05-20",
        "weekday": "수",
        "themes": [
            {
                "theme": "광통신/통신장비",
                "reason": "AI 데이터센터 광트랜시버 수요 폭발 및 글로벌 통신사 5G 투자 재개 신호",
                "leaders": [
                    {"name": "오이솔루션", "change": 29.95},
                    {"name": "우리로", "change": 27.40},
                    {"name": "쏠리드", "change": 22.15},
                    {"name": "이노와이어리스", "change": 19.80},
                    {"name": "코위버", "change": 16.55},
                ],
            },
            {
                "theme": "일부 반도체 관련주",
                "reason": "차량용 반도체 공급 부족 완화 기대 및 파운드리 가동률 회복세",
                "leaders": [
                    {"name": "DB하이텍", "change": 12.40},
                    {"name": "하나마이크론", "change": 15.67},
                    {"name": "네패스아크", "change": 18.90},
                    {"name": "SFA반도체", "change": 11.20},
                    {"name": "코아시아", "change": 9.45},
                ],
            },
            {
                "theme": "MLCC(적층세라믹콘덴서)",
                "reason": "전기차·AI 서버 탑재 MLCC 수요 증가 및 일본 무라타 공급 축소로 국내 업체 반사이익",
                "leaders": [
                    {"name": "삼화콘덴서", "change": 29.94},
                    {"name": "삼성전기", "change": 14.85},
                    {"name": "아모텍", "change": 22.30},
                    {"name": "태양유전", "change": 18.10},
                    {"name": "에스에이엠티", "change": 12.65},
                ],
            },
            {
                "theme": "백신/진단키트",
                "reason": "신종 호흡기 바이러스 확산 우려 및 WHO 권고에 따른 진단키트 수요 증가",
                "leaders": [
                    {"name": "씨젠", "change": 19.45},
                    {"name": "SD바이오센서", "change": 16.30},
                    {"name": "휴마시스", "change": 29.87},
                    {"name": "에스디바이오센서", "change": 14.20},
                    {"name": "바이오노트", "change": 11.55},
                ],
            },
        ],
    },
    {
        "date": "2026-05-19",
        "weekday": "화",
        "themes": [
            {
                "theme": "양자/보안",
                "reason": "국가 사이버보안 강화 법안 통과 및 양자암호통신 국가망 적용 확대 발표",
                "leaders": [
                    {"name": "드림시큐리티", "change": 29.91},
                    {"name": "케이씨에스", "change": 24.60},
                    {"name": "이니텍", "change": 18.45},
                    {"name": "시큐브", "change": 15.30},
                    {"name": "솔트룩스", "change": 12.80},
                ],
            },
            {
                "theme": "방산주",
                "reason": "유럽 재무장 수요 급증 및 폴란드·루마니아 K2 전차 추가 계약 기대, NATO 방산 협력 확대",
                "leaders": [
                    {"name": "한화에어로스페이스", "change": 11.75},
                    {"name": "LIG넥스원", "change": 14.20},
                    {"name": "현대로템", "change": 16.85},
                    {"name": "한국항공우주", "change": 9.40},
                    {"name": "풍산", "change": 8.65},
                ],
            },
            {
                "theme": "백신/진단키트 등",
                "reason": "해외 입국자 급증 및 바이러스 변이 확산 경보에 따른 진단키트 선제 수요",
                "leaders": [
                    {"name": "씨젠", "change": 22.30},
                    {"name": "SD바이오센서", "change": 18.75},
                    {"name": "휴마시스", "change": 25.40},
                    {"name": "래피젠", "change": 14.60},
                    {"name": "진매트릭스", "change": 11.25},
                ],
            },
            {
                "theme": "엔터/음원/음반",
                "reason": "K-POP 글로벌 음반 판매 신기록 및 대형 기획사 해외 투어 흥행 소식",
                "leaders": [
                    {"name": "하이브", "change": 8.95},
                    {"name": "에스엠", "change": 12.40},
                    {"name": "와이지엔터테인먼트", "change": 15.70},
                    {"name": "JYP Ent.", "change": 10.35},
                    {"name": "드림어스컴퍼니", "change": 19.80},
                ],
            },
        ],
    },
    {
        "date": "2026-05-18",
        "weekday": "월",
        "themes": [
            {
                "theme": "반도체 관련주",
                "reason": "미국 대중 반도체 수출 규제 완화 신호 및 D램 현물가 반등, 반도체 장비 수주 재개",
                "leaders": [
                    {"name": "SK하이닉스", "change": 6.45},
                    {"name": "원익IPS", "change": 14.30},
                    {"name": "유진테크", "change": 18.55},
                    {"name": "피에스케이", "change": 12.70},
                    {"name": "HPSP", "change": 10.40},
                ],
            },
            {
                "theme": "우주항공",
                "reason": "한국형 발사체 누리호 상업 발사 성공 및 글로벌 위성통신 시장 참여 확대 기대",
                "leaders": [
                    {"name": "한국항공우주", "change": 15.80},
                    {"name": "AP위성", "change": 29.88},
                    {"name": "켄코아에어로스페이스", "change": 22.45},
                    {"name": "쎄트렉아이", "change": 18.30},
                    {"name": "인텔리안테크", "change": 14.15},
                ],
            },
            {
                "theme": "태양광",
                "reason": "정부 재생에너지 3020 계획 재확인 및 미국 태양광 설치 보조금 확대, 모듈 수출 증가",
                "leaders": [
                    {"name": "OCI홀딩스", "change": 12.35},
                    {"name": "한화솔루션", "change": 9.80},
                    {"name": "신성이엔지", "change": 18.60},
                    {"name": "에스에너지", "change": 15.25},
                    {"name": "다음에너지", "change": 21.40},
                ],
            },
            {
                "theme": "손해/생명보험",
                "reason": "보험업 자본 규제 완화 및 배당 확대 기대, 실손보험 제도 개편에 따른 수익성 개선 전망",
                "leaders": [
                    {"name": "삼성화재", "change": 6.75},
                    {"name": "DB손해보험", "change": 8.40},
                    {"name": "현대해상", "change": 7.15},
                    {"name": "삼성생명", "change": 5.90},
                    {"name": "한화생명", "change": 7.35},
                ],
            },
        ],
    },
    {
        "date": "2026-05-15",
        "weekday": "금",
        "themes": [
            {
                "theme": "일부 로봇/LG그룹",
                "reason": "LG전자 로봇 사업부 독립 법인 설립 소식 및 LG 계열사 전반 동반 상승",
                "leaders": [
                    {"name": "LG전자", "change": 9.45},
                    {"name": "LG이노텍", "change": 12.30},
                    {"name": "LG화학", "change": 7.85},
                    {"name": "로보스타", "change": 18.60},
                    {"name": "엔젤로보틱스", "change": 24.15},
                ],
            },
            {
                "theme": "개별 이슈",
                "reason": "특정 종목 개별 공시(M&A, 신사업 진출, 계약 체결 등)에 따른 단발성 테마 형성",
                "leaders": [
                    {"name": "종목A", "change": 29.95},
                    {"name": "종목B", "change": 22.40},
                    {"name": "종목C", "change": 18.75},
                ],
            },
        ],
    },
]


def load_market_prices(settings: Settings, codes: list[str]) -> tuple[pd.DataFrame, str | None, bool]:
    if settings.use_mock:
        return load_sample_prices(settings.sample_prices_path), None, True

    client = KiwoomRestClient(
        base_url=settings.base_url,
        app_key=settings.app_key,
        secret_key=settings.secret_key,
    )
    try:
        return client.fetch_current_prices(codes), None, False
    except KiwoomApiError as exc:
        fallback = load_sample_prices(settings.sample_prices_path)
        return fallback, f"키움 API 조회에 실패해 샘플 데이터로 화면을 표시합니다: {exc}", True


def _empty_dataframe(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _get_market_phase(reference_time: datetime | None = None) -> str:
    current = reference_time or datetime.now()
    current_time = current.time()
    if time(8, 0) <= current_time < time(9, 0):
        return "pre_market"
    if time(9, 0) <= current_time < time(15, 30):
        return "regular_market"
    if time(15, 30) <= current_time < time(18, 0):
        return "after_market"
    return "closed"


def _load_ranked_snapshot() -> tuple[Settings, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None, bool]:
    settings = load_settings()
    theme_map = load_theme_map(settings.theme_map_path)
    codes = theme_map["code"].dropna().astype(str).drop_duplicates().tolist()
    prices, error_message, effective_mock = load_market_prices(settings, codes)
    sectors, leaders = rank_sectors(prices, theme_map, top_n=5)
    return settings, theme_map, prices, sectors, leaders, error_message, effective_mock


def _data_mode(settings: Settings, effective_mock: bool) -> str:
    if effective_mock:
        return "mock"
    if settings.use_mock:
        return "mock"
    return "kiwoom_rest"


def get_market_summary() -> dict[str, Any]:
    """Return stable market/theme summary values for Streamlit view models."""

    settings, theme_map, prices, sectors, _leaders, error_message, effective_mock = _load_ranked_snapshot()
    top_sector = sectors.iloc[0] if not sectors.empty else None

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "market_phase": _get_market_phase(),
        "data_mode": _data_mode(settings, effective_mock),
        "effective_mock": bool(effective_mock),
        "error_message": error_message,
        "theme_count": int(sectors["sector"].nunique()) if "sector" in sectors else 0,
        "stock_count": int(theme_map["code"].dropna().astype(str).nunique()) if "code" in theme_map else 0,
        "top_theme": None if top_sector is None else str(top_sector["sector"]),
        "top_theme_score": None if top_sector is None else float(top_sector["sector_score"]),
        "avg_change_rate": float(pd.to_numeric(prices["change_rate"], errors="coerce").mean()) if not prices.empty else 0.0,
        "rising_ratio": float((pd.to_numeric(prices["change_rate"], errors="coerce") > 0).mean()) if not prices.empty else 0.0,
        "total_trade_value": float(pd.to_numeric(prices["trade_value"], errors="coerce").fillna(0).sum()) if not prices.empty else 0.0,
    }
    return {key: summary[key] for key in MARKET_SUMMARY_KEYS}


def get_market_movers(date: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Return mock Korean market mover candidates sorted by pct_change desc.

    The date argument is reserved for the future real-data implementation.
    """

    del date
    try:
        normalized_limit = max(0, int(limit))
    except (TypeError, ValueError):
        normalized_limit = 30

    movers = sorted(
        MOCK_MARKET_MOVERS,
        key=lambda item: float(item.get("pct_change", 0.0)),
        reverse=True,
    )
    return [
        {key: mover[key] for key in MARKET_MOVER_KEYS}
        for mover in movers[:normalized_limit]
    ]


def get_theme_heatmap() -> pd.DataFrame:
    """Return one stable row per theme/sector for future Streamlit or Plotly rendering."""

    _settings, _theme_map, _prices, sectors, leaders, _error_message, _effective_mock = _load_ranked_snapshot()
    if sectors.empty:
        return _empty_dataframe(THEME_HEATMAP_COLUMNS)

    heatmap = sectors.copy()
    heatmap["theme_id"] = heatmap["sector"].astype(str)
    heatmap["theme_name"] = heatmap["sector"].astype(str)
    heatmap["theme_score"] = pd.to_numeric(heatmap["sector_score"], errors="coerce").fillna(0.0)
    heatmap["total_trading_value"] = pd.to_numeric(heatmap["trade_value_sum"], errors="coerce").fillna(0.0)
    # market_cap: real data = sum of constituent stock market caps.
    # Mock fallback uses theme_score * stock_count so the distribution differs from trading value.
    _ts = pd.to_numeric(heatmap["theme_score"], errors="coerce").fillna(1.0).clip(lower=0.1)
    _sc = pd.to_numeric(heatmap["stock_count"], errors="coerce").fillna(1.0)
    heatmap["market_cap"] = (_ts * _sc * 100_000_000_000).round()

    leader_names = (
        leaders.sort_values(["sector", "rank"])
        .groupby("sector")["name"]
        .apply(lambda names: ", ".join(names.astype(str).head(5)))
    )
    heatmap["leader_names"] = heatmap["sector"].map(leader_names).fillna("")

    _cr = pd.to_numeric(heatmap["top5_change_rate_mean"], errors="coerce").fillna(0.0)
    _tv = heatmap["total_trading_value"]
    _tv_q75 = float(_tv.quantile(0.75)) if len(_tv) > 1 else 0.0
    heatmap["badges"] = [
        ",".join(b for b in (
            "급등" if _cr.iat[i] >= 10.0 else "",
            "거래대금 TOP" if _tv_q75 > 0 and float(_tv.iat[i]) >= _tv_q75 else "",
        ) if b)
        for i in range(len(heatmap))
    ]

    return heatmap[THEME_HEATMAP_COLUMNS].reset_index(drop=True)


def get_theme_leaders(theme_id: str | None) -> pd.DataFrame:
    """Return Top 5 leaders for a theme id, or an empty stable frame when missing."""

    if not theme_id:
        return _empty_dataframe(THEME_LEADER_COLUMNS)

    _settings, _theme_map, _prices, _sectors, leaders, _error_message, _effective_mock = _load_ranked_snapshot()
    if leaders.empty or "sector" not in leaders:
        return _empty_dataframe(THEME_LEADER_COLUMNS)

    selected = leaders[leaders["sector"].astype(str) == str(theme_id)].sort_values("rank").head(5).copy()
    if selected.empty:
        return _empty_dataframe(THEME_LEADER_COLUMNS)

    selected["theme_id"] = selected["sector"].astype(str)
    selected["theme_name"] = selected["sector"].astype(str)
    return selected[THEME_LEADER_COLUMNS].reset_index(drop=True)


_MOCK_DAILY_TV = [
    1_250_000_000_000,
    1_080_000_000_000,
    950_000_000_000,
    870_000_000_000,
    790_000_000_000,
]


def compute_badges_from_history(history: list[dict]) -> dict[str, list[str]]:
    """Return {theme_name: [badge, ...]} for today's themes from recent THEME_HISTORY.

    Rules (max 2 per theme):
    - NEW: in today's top-3 but not yesterday's top-3
    - N일 연속: in the first 3 positions for N consecutive days
    - 거래대금 급증: today's avg leader change_rate >= 20%
    """
    if not history:
        return {}

    daily_top3: list[set[str]] = [
        {t["theme"] for t in day["themes"][:3]}
        for day in history[:5]
    ]
    today_themes = [t["theme"] for t in history[0]["themes"]]
    today_top3 = daily_top3[0]
    yesterday_top3 = daily_top3[1] if len(daily_top3) > 1 else set()

    result: dict[str, list[str]] = {}
    for theme_name in today_themes:
        b: list[str] = []

        consecutive = 0
        for top3 in daily_top3:
            if theme_name in top3:
                consecutive += 1
            else:
                break

        if consecutive >= 3:
            b.append("3일 연속")
        elif consecutive >= 2:
            b.append("2일 연속")
        elif theme_name in today_top3 and theme_name not in yesterday_top3:
            b.append("NEW")

        today_theme = next((t for t in history[0]["themes"] if t["theme"] == theme_name), None)
        if today_theme:
            leaders = today_theme.get("leaders", [])
            if leaders:
                avg_change = sum(float(ldr.get("change", 0)) for ldr in leaders) / len(leaders)
                if avg_change >= 20.0:
                    b.append("거래대금 급증")

        if b:
            result[theme_name] = b[:2]

    return result


def get_theme_timeline(days: int = 5) -> pd.DataFrame:
    """Return date-by-date theme flow derived from THEME_HISTORY.

    Replace the body of this function with a real API call when live data is available.
    """
    history = get_theme_history()[:days]
    if not history:
        return _empty_dataframe(THEME_TIMELINE_COLUMNS)

    badges_map = compute_badges_from_history(history)
    rows: list[dict] = []

    for i, day in enumerate(history):
        themes = day["themes"]
        rank1 = themes[0]["theme"] if len(themes) > 0 else ""
        rank2 = themes[1]["theme"] if len(themes) > 1 else ""
        rank3 = themes[2]["theme"] if len(themes) > 2 else ""

        top_leader_stock, top_leader_change = "", 0.0
        if themes:
            leaders = themes[0].get("leaders", [])
            if leaders:
                best = max(leaders, key=lambda ldr: float(ldr.get("change", 0)))
                top_leader_stock = best["name"]
                top_leader_change = float(best.get("change", 0))

        next_rank1 = (
            history[i + 1]["themes"][0]["theme"]
            if i + 1 < len(history) and history[i + 1]["themes"]
            else ""
        )
        if next_rank1 and rank1 == next_rank1:
            comment = f"{rank1} 주도 지속"
        elif top_leader_change >= 25.0:
            comment = f"{rank1} 급등 주도"
        elif len(themes) >= 5:
            comment = "다수 테마 동반 상승"
        else:
            comment = "신규 테마 부상"

        rows.append({
            "date": day["date"],
            "rank_1_theme": rank1,
            "rank_2_theme": rank2,
            "rank_3_theme": rank3,
            "top_leader_stock": top_leader_stock,
            "top_leader_change_rate": top_leader_change,
            "total_trading_value": _MOCK_DAILY_TV[i] if i < len(_MOCK_DAILY_TV) else 500_000_000_000,
            "market_comment": comment,
            "badges": " ".join(badges_map.get(rank1, [])),
        })

    return pd.DataFrame(rows, columns=THEME_TIMELINE_COLUMNS)


def get_theme_history() -> list[dict]:
    """Return date-by-date sector history with theme_count added to each entry."""

    return [
        {
            "date": day["date"],
            "weekday": day["weekday"],
            "theme_count": len(day["themes"]),
            "themes": day["themes"],
        }
        for day in THEME_HISTORY
    ]


def get_theme_history_table() -> list[dict]:
    """Return a flat row list suitable for direct table rendering.

    Each row is one (date, theme) pair. Leaders are formatted as "종목명 +29.89%".
    Missing leader slots are filled with "-".
    """

    rows = []
    for day in get_theme_history():
        for theme_data in day["themes"]:
            row: dict = {
                "date": day["date"],
                "weekday": day["weekday"],
                "theme": theme_data["theme"],
                "reason": theme_data.get("reason", ""),
            }
            leaders = theme_data.get("leaders", [])
            for i in range(1, 6):
                if i <= len(leaders):
                    leader = leaders[i - 1]
                    row[f"leader_{i}"] = f"{leader['name']} {float(leader['change']):+.2f}%"
                else:
                    row[f"leader_{i}"] = "-"
            rows.append(row)
    return rows


def get_today_featured_themes() -> list[dict]:
    """Return themes for the most recent date in THEME_HISTORY (2026-05-22 기준)."""

    history = get_theme_history()
    if not history:
        return []
    return history[0]["themes"]
