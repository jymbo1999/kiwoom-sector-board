"""운영용 universe 코드 파일과 sector_map.json 생성 스크립트.

사람이 관리하는 CSV 파일에서 universe 코드 리스트와 sector_map.json 을 생성한다.
외부 API 없이 로컬 CSV 기반으로 동작한다.

입력 CSV 필수 컬럼:
    code            종목코드 (6자리 미만은 zero-padding, 중복/잘못된 값 제외)

입력 CSV 선택 컬럼:
    name            종목명 (우선주/스팩/ETF 이름 패턴 감지에 사용)
    market_cap      시가총액 (정수, 시총 기준 내림차순 정렬에 사용)
    sector          대표 섹터명 (sector_map 생성에 사용)
    theme1          1차 테마 (sector_map 생성에 사용, sector 컬럼 없을 때)
    theme2          2차 테마 (--multi-sector 시 sector_map 에 포함)
    theme3          3차 테마 (--multi-sector 시 sector_map 에 포함)
    is_etf          ETF 여부 (1/true/yes → 기본 제외)
    is_spac         SPAC 여부
    is_preferred    우선주 여부
    is_managed      관리종목 여부

사용법::

    # 템플릿 CSV 생성
    python scripts/build_intraday_universe.py --write-template data/my_universe.csv

    # universe 코드 파일 + sector_map 생성 (기본 150종목)
    python scripts/build_intraday_universe.py --input data/theme_map.csv

    # limit 지정
    python scripts/build_intraday_universe.py --input data/theme_map.csv --limit 200

    # 출력 경로 직접 지정
    python scripts/build_intraday_universe.py --input data/theme_map.csv \\
        --output-codes data/universe_codes_150.txt \\
        --output-sector-map data/sector_map.json

    # dry-run (파일 쓰기 없이 결과 미리 보기)
    python scripts/build_intraday_universe.py --input data/theme_map.csv --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 상수 및 패턴
# ---------------------------------------------------------------------------

_PREFERRED_RE = re.compile(r"(?:우B?|우\(전환\)|우선주)$")
_SPAC_RE = re.compile(r"스팩\d*")

_CODE_ALIASES = ("code", "Code", "종목코드", "단축코드", "ticker", "Ticker")
_CAP_ALIASES = ("market_cap", "MarketCap", "Marcap", "시가총액", "상장시가총액")

_TEMPLATE_FIELDNAMES = ["code", "name", "market_cap", "sector"]
_TEMPLATE_ROWS = [
    {"code": "005930", "name": "삼성전자", "market_cap": "500000000000000", "sector": "반도체"},
    {"code": "000660", "name": "SK하이닉스", "market_cap": "100000000000000", "sector": "반도체"},
    {"code": "042660", "name": "한화오션", "market_cap": "10000000000000", "sector": "조선"},
    {"code": "000270", "name": "기아", "market_cap": "50000000000000", "sector": "자동차"},
    {"code": "068270", "name": "셀트리온", "market_cap": "30000000000000", "sector": "바이오"},
]


# ---------------------------------------------------------------------------
# 코드 normalize
# ---------------------------------------------------------------------------


def normalize_code(raw: str | None) -> str | None:
    """종목코드를 6자리 zero-padded 문자열로 normalize 한다.

    None, 비숫자, 빈 문자열, 7자리 이상 → None (제외 대상).
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s.isdigit():
        return None
    if len(s) > 6:
        return None
    return s.zfill(6)


# ---------------------------------------------------------------------------
# CSV 로드
# ---------------------------------------------------------------------------


def load_csv(path: Path) -> list[dict[str, str]]:
    """CSV 파일을 dict 리스트로 읽는다.

    인코딩은 utf-8 → utf-8-sig → cp949 순서로 시도한다.
    """
    for encoding in ("utf-8", "utf-8-sig", "cp949"):
        try:
            rows: list[dict[str, str]] = []
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
            return rows
        except UnicodeDecodeError:
            continue
    raise ValueError(f"CSV 파일 인코딩을 인식할 수 없습니다: {path}")


def find_column(keys: list[str], candidates: tuple[str, ...]) -> str | None:
    """candidates 순서로 keys 안에서 첫 번째로 존재하는 컬럼명을 반환한다."""
    for c in candidates:
        if c in keys:
            return c
    return None


# ---------------------------------------------------------------------------
# 필터
# ---------------------------------------------------------------------------


@dataclass
class FilterOptions:
    """제외 필터 옵션."""

    exclude_etf: bool = True
    exclude_spac: bool = True
    exclude_preferred: bool = True
    exclude_managed: bool = True


def _truthy(val: Any) -> bool:
    """1 / true / yes 계열 → True."""
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val != 0
    return str(val).strip().lower() in ("1", "true", "yes", "y")


def should_exclude(row: dict[str, str], opts: FilterOptions) -> bool:
    """row 가 제외 조건에 해당하면 True 를 반환한다.

    flag 컬럼이 있으면 flag 를 우선 사용하고,
    없으면 name 패턴으로 감지한다.
    """
    if opts.exclude_etf and _truthy(row.get("is_etf", "0")):
        return True
    if opts.exclude_spac and _truthy(row.get("is_spac", "0")):
        return True
    if opts.exclude_preferred and _truthy(row.get("is_preferred", "0")):
        return True
    if opts.exclude_managed and _truthy(row.get("is_managed", "0")):
        return True

    name = str(row.get("name") or "").strip()
    if opts.exclude_preferred and _PREFERRED_RE.search(name):
        return True
    if opts.exclude_spac and _SPAC_RE.search(name):
        return True
    if opts.exclude_etf and "ETF" in name.upper():
        return True

    return False


def apply_filters(
    rows: list[dict[str, str]],
    opts: FilterOptions | None = None,
) -> list[dict[str, str]]:
    """필터 옵션에 따라 제외 대상 row 를 걸러낸다."""
    effective = opts if opts is not None else FilterOptions()
    return [r for r in rows if not should_exclude(r, effective)]


# ---------------------------------------------------------------------------
# 시총 정렬 + 코드 추출 + 중복 제거
# ---------------------------------------------------------------------------


def sort_by_market_cap(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """market_cap 컬럼이 있으면 내림차순 정렬한다. 없으면 원래 순서를 유지한다."""
    if not rows:
        return rows
    cap_col = find_column(list(rows[0]), _CAP_ALIASES)
    if cap_col is None:
        return rows

    def _key(r: dict[str, str]) -> int:
        try:
            return int(float(str(r.get(cap_col) or "0").replace(",", "")))
        except (ValueError, TypeError):
            return 0

    return sorted(rows, key=_key, reverse=True)


def extract_codes(rows: list[dict[str, str]]) -> list[str]:
    """rows 에서 정규화된 6자리 코드를 순서 보존 중복 제거하여 반환한다."""
    seen: dict[str, None] = {}
    for row in rows:
        code_col = find_column(list(row), _CODE_ALIASES)
        raw = row.get(code_col or "code", "")
        code = normalize_code(raw)
        if code and code not in seen:
            seen[code] = None
    return list(seen)


# ---------------------------------------------------------------------------
# sector_map 생성
# ---------------------------------------------------------------------------


def _detect_sector_columns(row: dict[str, str]) -> list[str]:
    """row 에서 섹터 컬럼 목록을 우선순위 순으로 반환한다.

    우선순위: sector → theme1/theme2/theme3.
    """
    keys = list(row)
    if "sector" in keys:
        return ["sector"]
    themes = [c for c in ("theme1", "theme2", "theme3") if c in keys]
    return themes


def build_sector_map(
    rows: list[dict[str, str]],
    *,
    multi_sector: bool = False,
) -> dict[str, list[str]]:
    """rows 에서 base_code → 섹터명 리스트 dict 를 만든다.

    multi_sector=False 이면 첫 번째 섹터 컬럼만 사용한다.
    multi_sector=True 이면 theme1/theme2/theme3 모두 포함한다.
    sector 정보가 없는 코드는 sector_map 에서 제외된다.
    """
    result: dict[str, list[str]] = {}
    for row in rows:
        code_col = find_column(list(row), _CODE_ALIASES)
        raw = row.get(code_col or "code", "")
        code = normalize_code(raw)
        if not code:
            continue

        sec_cols = _detect_sector_columns(row)
        if not sec_cols:
            continue
        if not multi_sector:
            sec_cols = sec_cols[:1]

        sectors = [str(row.get(c) or "").strip() for c in sec_cols]
        sectors = [s for s in sectors if s]
        if sectors and code not in result:
            result[code] = sectors

    return result


# ---------------------------------------------------------------------------
# 파일 출력
# ---------------------------------------------------------------------------


def write_universe_txt(codes: list[str], path: Path) -> None:
    """종목코드 리스트를 텍스트 파일(한 줄에 하나)로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for code in codes:
            f.write(code + "\n")


def write_sector_map_json(sector_map: dict[str, list[str]], path: Path) -> None:
    """sector_map 을 JSON 파일로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sector_map, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_template_csv(path: Path) -> None:
    """예시 템플릿 CSV 를 생성한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_TEMPLATE_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_TEMPLATE_ROWS)


# ---------------------------------------------------------------------------
# 파이프라인
# ---------------------------------------------------------------------------


@dataclass
class BuildResult:
    """build_from_csv() 결과."""

    codes: list[str]
    sector_map: dict[str, list[str]]
    total_input: int
    excluded_count: int
    duplicate_count: int
    warnings: list[str] = field(default_factory=list)


def build_from_csv(
    rows: list[dict[str, str]],
    limit: int = 150,
    filter_opts: FilterOptions | None = None,
    multi_sector: bool = False,
) -> BuildResult:
    """CSV rows 에서 universe 코드 리스트와 sector_map 을 생성한다."""
    opts = filter_opts if filter_opts is not None else FilterOptions()
    warnings: list[str] = []

    total_input = len(rows)

    # 1. 필터
    filtered = apply_filters(rows, opts)
    excluded_count = total_input - len(filtered)

    # 2. 시총 정렬
    sorted_rows = sort_by_market_cap(filtered)

    # 3. 코드 추출 + 중복 제거
    all_codes = extract_codes(sorted_rows)
    duplicate_count = len(filtered) - len(all_codes)

    # 4. limit 적용
    codes = all_codes[:limit] if limit > 0 else all_codes

    # 5. sector_map 생성 (전체 filtered rows 기반)
    sector_map = build_sector_map(sorted_rows, multi_sector=multi_sector)

    # 6. 매핑 누락 경고
    unmapped = [c for c in codes if c not in sector_map]
    if unmapped:
        sample = unmapped[:10]
        warnings.append(
            f"sector_map 에 매핑되지 않은 코드 {len(unmapped)}개: {sample}"
            + ("..." if len(unmapped) > 10 else "")
        )

    return BuildResult(
        codes=codes,
        sector_map=sector_map,
        total_input=total_input,
        excluded_count=excluded_count,
        duplicate_count=duplicate_count,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="운영용 universe 코드 파일과 sector_map.json 생성 스크립트."
    )
    p.add_argument("--input", "-i", default="", help="입력 CSV 파일 경로.")
    p.add_argument("--limit", type=int, default=150, help="출력할 최대 종목 수 (기본 150).")
    p.add_argument(
        "--output-codes", dest="output_codes", default="",
        help="universe 코드 파일 출력 경로. 미지정 시 data/universe_codes_{limit}.txt.",
    )
    p.add_argument(
        "--output-sector-map", dest="output_sector_map", default="",
        help="sector_map 출력 경로. 미지정 시 data/sector_map.json.",
    )
    p.add_argument(
        "--multi-sector", dest="multi_sector", action="store_true", default=False,
        help="theme1/theme2/theme3 를 모두 sector_map 에 포함한다.",
    )
    p.add_argument(
        "--no-filter-preferred", dest="filter_preferred", action="store_false", default=True,
        help="우선주 필터링을 비활성화한다.",
    )
    p.add_argument(
        "--no-filter-etf", dest="filter_etf", action="store_false", default=True,
        help="ETF 필터링을 비활성화한다.",
    )
    p.add_argument(
        "--no-filter-spac", dest="filter_spac", action="store_false", default=True,
        help="SPAC 필터링을 비활성화한다.",
    )
    p.add_argument(
        "--no-filter-managed", dest="filter_managed", action="store_false", default=True,
        help="관리종목 필터링을 비활성화한다.",
    )
    p.add_argument(
        "--write-template", dest="write_template", default="",
        help="예시 템플릿 CSV 를 지정한 경로에 생성하고 종료한다.",
    )
    p.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=False,
        help="파일을 실제로 쓰지 않고 결과를 미리 보여준다.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # ---- 템플릿 생성 ----
    if args.write_template:
        path = Path(args.write_template)
        write_template_csv(path)
        print(f"[build] 템플릿 CSV 생성 완료: {path}")
        return 0

    # ---- 입력 파일 확인 ----
    if not args.input:
        print(
            "[build] ERROR: --input 파일을 지정하세요. "
            "또는 --write-template 으로 템플릿을 생성하세요."
        )
        return 2

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[build] ERROR: 입력 파일이 없습니다: {input_path}")
        return 2

    # ---- CSV 로드 ----
    try:
        rows = load_csv(input_path)
    except Exception as exc:
        print(f"[build] ERROR: CSV 로드 실패: {exc}")
        return 2

    if not rows:
        print("[build] ERROR: CSV 가 비어 있습니다.")
        return 2

    # ---- 빌드 ----
    filter_opts = FilterOptions(
        exclude_etf=args.filter_etf,
        exclude_spac=args.filter_spac,
        exclude_preferred=args.filter_preferred,
        exclude_managed=args.filter_managed,
    )
    result = build_from_csv(
        rows,
        limit=args.limit,
        filter_opts=filter_opts,
        multi_sector=args.multi_sector,
    )

    # ---- 출력 경로 결정 ----
    data_dir = PROJECT_ROOT / "data"
    codes_path = (
        Path(args.output_codes) if args.output_codes
        else data_dir / f"universe_codes_{len(result.codes)}.txt"
    )
    sector_map_path = (
        Path(args.output_sector_map) if args.output_sector_map
        else data_dir / "sector_map.json"
    )

    # ---- 결과 출력 ----
    print("[build] ===== build result =====")
    print(f"  input:             {input_path}  ({result.total_input} rows)")
    print(f"  excluded:          {result.excluded_count}")
    print(f"  duplicates:        {result.duplicate_count}")
    print(f"  codes:             {len(result.codes)}")
    print(f"  sector_map:        {len(result.sector_map)} 종목")
    print(f"  output_codes:      {codes_path}")
    print(f"  output_sector_map: {sector_map_path}")
    for w in result.warnings:
        print(f"  [warn] {w}")

    if args.dry_run:
        print("[build] dry-run: 파일을 쓰지 않습니다.")
        print(f"  codes[:10]: {result.codes[:10]}")
        sample = dict(list(result.sector_map.items())[:5])
        print(f"  sector_map sample: {sample}")
        return 0

    # ---- 파일 쓰기 ----
    write_universe_txt(result.codes, codes_path)
    write_sector_map_json(result.sector_map, sector_map_path)
    print(f"[build] 완료: {codes_path}  ({len(result.codes)} 종목)")
    print(f"[build] 완료: {sector_map_path}  ({len(result.sector_map)} 종목)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
