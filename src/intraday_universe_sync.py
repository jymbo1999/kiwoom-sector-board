"""theme_map.csv → sector_map.json / universe_codes_*.txt 생성 및 검증 유틸.

기본 정책:
  - theme1 컬럼만 섹터로 사용한다 (theme1_only=True 기본값).
  - code 는 6자리 문자열로 normalize 한다.
  - theme1 이 비어 있는 row 는 제외한다.
  - 중복 코드는 첫 번째 항목만 사용한다 (순서 보존).

사용 예::

    from src.intraday_universe_sync import (
        generate_sector_map_from_theme_map,
        generate_universe_codes,
        validate_universe_consistency,
    )

    sm   = generate_sector_map_from_theme_map(Path("data/theme_map.csv"))
    codes = generate_universe_codes(Path("data/theme_map.csv"))
    ok, issues = validate_universe_consistency(sm, codes)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# sector_map 생성
# ---------------------------------------------------------------------------


def generate_sector_map_from_theme_map(
    csv_path: "Path | str",
    *,
    theme1_only: bool = True,
) -> dict[str, list[str]]:
    """theme_map.csv 에서 sector_map dict 를 생성한다.

    Args:
        csv_path:    theme_map.csv 경로.
        theme1_only: True(기본) 이면 theme1 만 사용.
                     False 이면 theme1/theme2/theme3 모두 포함 (비어 있는 항목 제외).

    Returns:
        {"000660": ["반도체"], ...} 형식의 dict.
        code key 는 6자리 zero-padded 문자열.
    """
    result: dict[str, list[str]] = {}
    for row in _iter_theme_csv(csv_path):
        code = row["code"]
        theme1 = row["theme1"]
        if not theme1:
            continue

        if theme1_only:
            sectors = [theme1]
        else:
            sectors = [theme1]
            for col in ("theme2", "theme3"):
                t = row.get(col, "").strip()
                if t:
                    sectors.append(t)

        if code not in result:  # 첫 번째 항목만 사용
            result[code] = sectors

    return result


# ---------------------------------------------------------------------------
# universe code 리스트 생성
# ---------------------------------------------------------------------------


def generate_universe_codes(csv_path: "Path | str") -> list[str]:
    """theme_map.csv 에서 universe code 리스트를 생성한다.

    theme1 이 비어 있는 row 는 제외한다 (sector_map 과 동일 정책).
    중복 제거 후 CSV 순서 보존.

    Returns:
        ["005930", "000660", ...] 형식의 6자리 코드 리스트.
    """
    seen: dict[str, None] = {}
    for row in _iter_theme_csv(csv_path):
        code = row["code"]
        if not row["theme1"]:
            continue
        if code not in seen:
            seen[code] = None
    return list(seen)


# ---------------------------------------------------------------------------
# 일관성 검증
# ---------------------------------------------------------------------------


def validate_universe_consistency(
    sector_map: dict[str, list[str]],
    universe_codes: "list[str] | set[str]",
) -> tuple[bool, list[str]]:
    """sector_map 과 universe_codes 의 코드 집합이 일치하는지 검증한다.

    Returns:
        (ok, issues) —
          ok=True 이면 완전히 일치.
          issues 는 불일치 내역 문자열 리스트 (비어 있으면 일치).
    """
    sm_codes = set(sector_map.keys())
    u_codes = set(universe_codes)

    issues: list[str] = []
    in_sm_not_u = sm_codes - u_codes
    in_u_not_sm = u_codes - sm_codes

    if in_sm_not_u:
        sample = sorted(in_sm_not_u)[:10]
        issues.append(
            f"sector_map에 있지만 universe에 없는 코드 ({len(in_sm_not_u)}개): {sample}"
        )
    if in_u_not_sm:
        sample = sorted(in_u_not_sm)[:10]
        issues.append(
            f"universe에 있지만 sector_map에 없는 코드 ({len(in_u_not_sm)}개): {sample}"
        )

    return (len(issues) == 0), issues


# ---------------------------------------------------------------------------
# 파일 저장 헬퍼
# ---------------------------------------------------------------------------


def write_sector_map_json(sector_map: dict[str, list[str]], path: "Path | str") -> None:
    """sector_map 을 JSON 파일로 저장한다."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(sector_map, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_universe_txt(codes: list[str], path: "Path | str", *, comment: str = "") -> None:
    """universe 코드 리스트를 텍스트 파일(한 줄에 하나)로 저장한다."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if comment:
            for line in comment.splitlines():
                f.write(f"# {line}\n")
        for code in codes:
            f.write(code + "\n")


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _iter_theme_csv(csv_path: "Path | str"):
    """theme_map.csv 를 row dict 로 yield 한다. code 는 6자리로 normalize."""
    for encoding in ("utf-8", "utf-8-sig", "cp949"):
        try:
            with open(csv_path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_code = str(row.get("code") or "").strip()
                    if not raw_code.isdigit() or len(raw_code) > 6:
                        continue
                    yield {
                        "code": raw_code.zfill(6),
                        "name": str(row.get("name") or "").strip(),
                        "theme1": str(row.get("theme1") or "").strip(),
                        "theme2": str(row.get("theme2") or "").strip(),
                        "theme3": str(row.get("theme3") or "").strip(),
                    }
            return  # encoding 성공
        except UnicodeDecodeError:
            continue
    raise ValueError(f"CSV 파일 인코딩을 인식할 수 없습니다: {csv_path}")
