from __future__ import annotations

import io
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

_log = logging.getLogger(__name__)

_KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
}
_KIND_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://kind.krx.co.kr",
}


def get_last_trading_date() -> date:
    """KRX 리소스 번들 API로 가장 최근 거래일 반환 (공휴일 자동 처리).

    data.krx.co.kr의 max_work_dt 필드를 사용해 공휴일·주말을 자동으로 건너뜀.
    """
    url = (
        "http://data.krx.co.kr/comm/bldAttendant/executeForResourceBundle.cmd"
        "?baseName=krx.mdc.i18n.component&key=B128.bld"
    )
    resp = requests.get(url, headers=_KRX_HEADERS, timeout=10)
    resp.raise_for_status()
    date_str: str = resp.json()["result"]["output"][0]["max_work_dt"]
    return datetime.strptime(date_str, "%Y%m%d").date()


def _fetch_sector_map_from_kind() -> pd.DataFrame:
    """kind.krx.co.kr에서 KOSPI+KOSDAQ 전체 상장사 업종 매핑을 반환.

    Returns DataFrame columns: code (6자리), sector (KSIC 업종명)
    """
    frames: list[pd.DataFrame] = []
    for mkt_id in ("stockMkt", "kosdaqMkt"):
        url = (
            f"http://kind.krx.co.kr/corpgeneral/corpList.do"
            f"?method=download&searchType=13&marketType={mkt_id}"
        )
        resp = requests.get(url, headers=_KIND_HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "euc-kr"
        df = pd.read_html(io.StringIO(resp.text), header=0)[0]
        frames.append(df)
        _log.info("[krx] kind.krx %s: %d종목", mkt_id, len(df))

    combined = pd.concat(frames, ignore_index=True)
    combined["종목코드"] = combined["종목코드"].astype(str).str.zfill(6)
    result = (
        combined[["종목코드", "업종"]]
        .rename(columns={"종목코드": "code", "업종": "sector"})
        .dropna(subset=["sector"])
        .drop_duplicates(subset="code")
        .reset_index(drop=True)
    )
    return result


def _load_or_refresh_sector_map(cache_path: Path, max_age_days: int = 7) -> pd.DataFrame:
    """섹터 맵 캐시 로드. 만료됐거나 없으면 kind.krx.co.kr에서 재수집."""
    if cache_path.exists():
        age_days = (date.today() - datetime.fromtimestamp(cache_path.stat().st_mtime).date()).days
        if age_days < max_age_days:
            df = pd.read_csv(cache_path, dtype={"code": str})
            _log.info("[krx] 섹터 캐시 로드: %d건 (age=%dd, %s)", len(df), age_days, cache_path.name)
            return df

    _log.info("[krx] 섹터 캐시 만료 또는 없음 — kind.krx.co.kr 재수집...")
    df = _fetch_sector_map_from_kind()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    _log.info("[krx] 섹터 캐시 저장: %d건 → %s", len(df), cache_path)
    return df


def fetch_krx_snapshot(
    trade_date: date,
    sector_cache_path: Path | None = None,
) -> pd.DataFrame:
    """전 거래일 기준 KRX 전체 종목(KOSPI+KOSDAQ) OHLCV + 공식 업종 반환.

    fdr.StockListing('KRX')는 시장이 닫힌 시간대(04:00 KST)에 호출하면
    직전 거래일의 종가·등락률 데이터를 반환한다.

    Parameters
    ----------
    trade_date : 스냅샷 레이블용 거래일 (DB 저장에만 사용, 실제 조회 날짜 아님)
    sector_cache_path : 업종 캐시 CSV 경로 (None이면 data/sector_cache.csv)

    Returns
    -------
    DataFrame columns:
        code, name, sector, market,
        open_price, current_price, volume, trade_value, change_rate
    """
    import FinanceDataReader as fdr
    from .config import DATA_DIR

    cache_path = sector_cache_path or (DATA_DIR / "sector_cache.csv")

    _log.info("[krx] OHLCV 수집 (fdr.StockListing KRX)...")
    ohlcv_df = fdr.StockListing("KRX")
    _log.info("[krx] OHLCV: %d종목", len(ohlcv_df))

    sector_df = _load_or_refresh_sector_map(cache_path)

    ohlcv_df["Code"] = ohlcv_df["Code"].astype(str).str.zfill(6)
    sector_df["code"] = sector_df["code"].astype(str).str.zfill(6)

    # map 방식으로 병합 (컬럼 중복 방지)
    sector_lookup = sector_df.set_index("code")["sector"]
    merged = ohlcv_df.copy()
    merged["sector"] = merged["Code"].map(sector_lookup).fillna("기타").astype(str).str.strip()
    merged.loc[merged["sector"] == "", "sector"] = "기타"

    rename_map = {
        "Code": "code",
        "Name": "name",
        "Market": "market",
        "Open": "open_price",
        "Close": "current_price",
        "Volume": "volume",
        "Amount": "trade_value",
        "ChagesRatio": "change_rate",
    }
    merged = merged.rename(columns=rename_map)

    for col in ("open_price", "current_price", "volume", "trade_value", "change_rate"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)

    # 거래 없는 종목 (상장폐지·거래정지) 제거
    merged = merged[merged["current_price"] > 0].copy()

    keep_cols = [
        "code", "name", "sector", "market",
        "open_price", "current_price", "volume", "trade_value", "change_rate",
    ]
    result = merged[[c for c in keep_cols if c in merged.columns]].reset_index(drop=True)

    _log.info(
        "[krx] 완료: %d종목, %d섹터 (거래일: %s)",
        len(result),
        result["sector"].nunique() if "sector" in result.columns else 0,
        trade_date,
    )
    return result
