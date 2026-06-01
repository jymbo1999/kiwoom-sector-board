"""scripts/build_intraday_universe.py 단위 테스트."""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# importlib 으로 스크립트 로드 (같은 패턴을 test_intraday_snapshot_smoke.py 에서 사용 중)
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_intraday_universe.py"
_spec = importlib.util.spec_from_file_location("_build_script", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)   # type: ignore[arg-type]
sys.modules["_build_script"] = _mod
_spec.loader.exec_module(_mod)                  # type: ignore[union-attr]

normalize_code     = _mod.normalize_code
load_csv           = _mod.load_csv
find_column        = _mod.find_column
FilterOptions      = _mod.FilterOptions
should_exclude     = _mod.should_exclude
apply_filters      = _mod.apply_filters
sort_by_market_cap = _mod.sort_by_market_cap
extract_codes      = _mod.extract_codes
build_sector_map   = _mod.build_sector_map
build_from_csv     = _mod.build_from_csv
write_universe_txt = _mod.write_universe_txt
write_sector_map_json = _mod.write_sector_map_json
write_template_csv = _mod.write_template_csv


# ---------------------------------------------------------------------------
# 1. normalize_code
# ---------------------------------------------------------------------------


def test_normalize_code_basic() -> None:
    assert normalize_code("005930") == "005930"
    assert normalize_code("000660") == "000660"


def test_normalize_code_zero_pads() -> None:
    assert normalize_code("5930") == "005930"
    assert normalize_code("1") == "000001"


def test_normalize_code_none_returns_none() -> None:
    assert normalize_code(None) is None


def test_normalize_code_empty_returns_none() -> None:
    assert normalize_code("") is None
    assert normalize_code("   ") is None


def test_normalize_code_non_numeric_returns_none() -> None:
    assert normalize_code("ABCDEF") is None
    assert normalize_code("00593A") is None


def test_normalize_code_seven_digits_returns_none() -> None:
    assert normalize_code("1234567") is None


def test_normalize_code_strips_whitespace() -> None:
    assert normalize_code("  5930 ") == "005930"


# ---------------------------------------------------------------------------
# 2. load_csv
# ---------------------------------------------------------------------------


def test_load_csv_basic(tmp_path: Path) -> None:
    f = tmp_path / "test.csv"
    f.write_text("code,name\n005930,삼성전자\n000660,SK하이닉스\n", encoding="utf-8")
    rows = load_csv(f)
    assert len(rows) == 2
    assert rows[0]["code"] == "005930"
    assert rows[1]["name"] == "SK하이닉스"


def test_load_csv_skips_blank_trailing_row(tmp_path: Path) -> None:
    f = tmp_path / "test.csv"
    f.write_text("code,name\n005930,삼성전자\n", encoding="utf-8")
    rows = load_csv(f)
    assert len(rows) == 1


def test_load_csv_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        load_csv(tmp_path / "nonexistent.csv")


# ---------------------------------------------------------------------------
# 3. find_column
# ---------------------------------------------------------------------------


def test_find_column_returns_first_match() -> None:
    assert find_column(["market_cap", "name", "code"], ("code", "Code")) == "code"


def test_find_column_returns_none_if_not_found() -> None:
    assert find_column(["name", "sector"], ("code", "Code")) is None


# ---------------------------------------------------------------------------
# 4. should_exclude / apply_filters
# ---------------------------------------------------------------------------


def test_exclude_etf_by_flag() -> None:
    row = {"code": "069500", "name": "KODEX 200", "is_etf": "1"}
    assert should_exclude(row, FilterOptions(exclude_etf=True))


def test_exclude_etf_by_name_pattern() -> None:
    row = {"code": "069500", "name": "KODEX 200 ETF"}
    assert should_exclude(row, FilterOptions(exclude_etf=True))


def test_exclude_preferred_by_name() -> None:
    row = {"code": "005935", "name": "삼성전자우"}
    assert should_exclude(row, FilterOptions(exclude_preferred=True))


def test_exclude_spac_by_name() -> None:
    row = {"code": "123456", "name": "하나스팩123"}
    assert should_exclude(row, FilterOptions(exclude_spac=True))


def test_exclude_managed_by_flag() -> None:
    row = {"code": "123456", "name": "어떤종목", "is_managed": "true"}
    assert should_exclude(row, FilterOptions(exclude_managed=True))


def test_no_exclude_if_flags_disabled() -> None:
    row = {"code": "069500", "name": "KODEX 200 ETF", "is_etf": "1"}
    opts = FilterOptions(exclude_etf=False, exclude_spac=False,
                         exclude_preferred=False, exclude_managed=False)
    assert not should_exclude(row, opts)


def test_apply_filters_removes_etf(tmp_path: Path) -> None:
    rows = [
        {"code": "005930", "name": "삼성전자"},
        {"code": "069500", "name": "KODEX ETF", "is_etf": "1"},
    ]
    result = apply_filters(rows, FilterOptions(exclude_etf=True))
    assert len(result) == 1
    assert result[0]["code"] == "005930"


def test_apply_filters_default_opts_removes_preferred() -> None:
    rows = [
        {"code": "005930", "name": "삼성전자"},
        {"code": "005935", "name": "삼성전자우"},
    ]
    result = apply_filters(rows)
    codes = [r["code"] for r in result]
    assert "005930" in codes
    assert "005935" not in codes


# ---------------------------------------------------------------------------
# 5. sort_by_market_cap
# ---------------------------------------------------------------------------


def test_sort_by_market_cap_descending() -> None:
    rows = [
        {"code": "000001", "market_cap": "1000"},
        {"code": "000002", "market_cap": "5000"},
        {"code": "000003", "market_cap": "3000"},
    ]
    sorted_rows = sort_by_market_cap(rows)
    caps = [r["market_cap"] for r in sorted_rows]
    assert caps == ["5000", "3000", "1000"]


def test_sort_by_market_cap_preserves_order_if_no_column() -> None:
    rows = [
        {"code": "000001", "name": "A"},
        {"code": "000002", "name": "B"},
    ]
    result = sort_by_market_cap(rows)
    assert [r["code"] for r in result] == ["000001", "000002"]


def test_sort_by_market_cap_handles_empty() -> None:
    assert sort_by_market_cap([]) == []


def test_sort_by_market_cap_handles_non_numeric_cap() -> None:
    rows = [
        {"code": "000001", "market_cap": "bad"},
        {"code": "000002", "market_cap": "1000"},
    ]
    # 예외 없이 정렬됨 (bad → 0으로 처리)
    result = sort_by_market_cap(rows)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 6. extract_codes
# ---------------------------------------------------------------------------


def test_extract_codes_basic() -> None:
    rows = [{"code": "005930"}, {"code": "000660"}]
    assert extract_codes(rows) == ["005930", "000660"]


def test_extract_codes_deduplicates() -> None:
    rows = [{"code": "005930"}, {"code": "005930"}, {"code": "000660"}]
    result = extract_codes(rows)
    assert result.count("005930") == 1
    assert len(result) == 2


def test_extract_codes_zero_pads() -> None:
    rows = [{"code": "5930"}]
    assert extract_codes(rows) == ["005930"]


def test_extract_codes_skips_invalid() -> None:
    rows = [{"code": "ABCDEF"}, {"code": "005930"}]
    result = extract_codes(rows)
    assert result == ["005930"]


def test_extract_codes_skips_empty() -> None:
    rows = [{"code": ""}, {"code": "005930"}]
    assert extract_codes(rows) == ["005930"]


def test_extract_codes_preserves_order() -> None:
    rows = [{"code": "000003"}, {"code": "000001"}, {"code": "000002"}]
    assert extract_codes(rows) == ["000003", "000001", "000002"]


# ---------------------------------------------------------------------------
# 7. build_sector_map
# ---------------------------------------------------------------------------


def test_build_sector_map_sector_column() -> None:
    rows = [
        {"code": "005930", "sector": "반도체"},
        {"code": "000660", "sector": "반도체"},
        {"code": "042660", "sector": "조선"},
    ]
    sm = build_sector_map(rows)
    assert sm["005930"] == ["반도체"]
    assert sm["042660"] == ["조선"]


def test_build_sector_map_theme1_column() -> None:
    rows = [
        {"code": "005930", "theme1": "반도체", "theme2": "메모리"},
    ]
    sm = build_sector_map(rows, multi_sector=False)
    assert sm["005930"] == ["반도체"]


def test_build_sector_map_multi_sector() -> None:
    rows = [
        {"code": "005930", "theme1": "반도체", "theme2": "메모리", "theme3": "HBM"},
    ]
    sm = build_sector_map(rows, multi_sector=True)
    assert sm["005930"] == ["반도체", "메모리", "HBM"]


def test_build_sector_map_skips_no_sector_column() -> None:
    rows = [{"code": "005930", "name": "삼성전자"}]
    sm = build_sector_map(rows)
    assert "005930" not in sm


def test_build_sector_map_skips_empty_sector() -> None:
    rows = [{"code": "005930", "sector": ""}]
    sm = build_sector_map(rows)
    assert "005930" not in sm


def test_build_sector_map_zero_pads_code() -> None:
    rows = [{"code": "5930", "sector": "반도체"}]
    sm = build_sector_map(rows)
    assert "005930" in sm
    assert "5930" not in sm


def test_build_sector_map_no_duplicate_code_on_same_input() -> None:
    rows = [
        {"code": "005930", "sector": "반도체"},
        {"code": "005930", "sector": "대형주"},  # 중복 코드 — 첫 번째만 사용
    ]
    sm = build_sector_map(rows)
    assert sm["005930"] == ["반도체"]


# ---------------------------------------------------------------------------
# 8. build_from_csv 파이프라인
# ---------------------------------------------------------------------------


def _make_rows(n: int) -> list[dict[str, str]]:
    return [
        {
            "code": f"{i:06d}",
            "name": f"종목{i}",
            "market_cap": str((n - i) * 1_000_000_000_000),
            "sector": "테스트섹터",
        }
        for i in range(1, n + 1)
    ]


def test_build_from_csv_limit() -> None:
    rows = _make_rows(50)
    result = build_from_csv(rows, limit=10)
    assert len(result.codes) == 10


def test_build_from_csv_limit_larger_than_rows() -> None:
    rows = _make_rows(5)
    result = build_from_csv(rows, limit=200)
    assert len(result.codes) == 5


def test_build_from_csv_limit_zero_means_all() -> None:
    rows = _make_rows(20)
    result = build_from_csv(rows, limit=0)
    assert len(result.codes) == 20


def test_build_from_csv_deduplicates() -> None:
    rows = [
        {"code": "005930", "sector": "반도체"},
        {"code": "005930", "sector": "반도체"},  # 중복
        {"code": "000660", "sector": "반도체"},
    ]
    result = build_from_csv(rows, limit=10)
    assert len(result.codes) == 2
    assert result.duplicate_count == 1


def test_build_from_csv_excludes_preferred() -> None:
    rows = [
        {"code": "005930", "name": "삼성전자", "sector": "반도체"},
        {"code": "005935", "name": "삼성전자우", "sector": "반도체"},
    ]
    result = build_from_csv(rows, limit=10)
    assert "005935" not in result.codes
    assert result.excluded_count == 1


def test_build_from_csv_sector_map_built() -> None:
    rows = [
        {"code": "005930", "sector": "반도체"},
        {"code": "042660", "sector": "조선"},
    ]
    result = build_from_csv(rows, limit=10)
    assert result.sector_map["005930"] == ["반도체"]
    assert result.sector_map["042660"] == ["조선"]


def test_build_from_csv_warns_unmapped_codes() -> None:
    rows = [
        {"code": "005930"},  # sector 없음
    ]
    result = build_from_csv(rows, limit=10)
    assert len(result.warnings) > 0
    assert any("sector_map" in w for w in result.warnings)


def test_build_from_csv_total_input_count() -> None:
    rows = _make_rows(20)
    result = build_from_csv(rows, limit=10)
    assert result.total_input == 20


def test_build_from_csv_sorts_by_market_cap() -> None:
    """market_cap 역순 정렬 후 limit 적용 → 가장 큰 종목이 포함된다."""
    rows = [
        {"code": "000001", "market_cap": "1000", "sector": "A"},
        {"code": "000002", "market_cap": "9000", "sector": "A"},
        {"code": "000003", "market_cap": "5000", "sector": "A"},
    ]
    result = build_from_csv(rows, limit=2)
    assert "000002" in result.codes  # 가장 큰 시총
    assert "000003" in result.codes
    assert "000001" not in result.codes  # 가장 작은 시총 → 제외


# ---------------------------------------------------------------------------
# 9. write_universe_txt / write_sector_map_json
# ---------------------------------------------------------------------------


def test_write_universe_txt(tmp_path: Path) -> None:
    out = tmp_path / "codes.txt"
    write_universe_txt(["005930", "000660", "042660"], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == ["005930", "000660", "042660"]


def test_write_sector_map_json_is_valid_json(tmp_path: Path) -> None:
    out = tmp_path / "sector_map.json"
    sm = {"005930": ["반도체"], "042660": ["조선"]}
    write_sector_map_json(sm, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == sm


def test_write_sector_map_json_creates_parent_dir(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "deep" / "sector_map.json"
    write_sector_map_json({"005930": ["반도체"]}, out)
    assert out.exists()


# ---------------------------------------------------------------------------
# 10. write_template_csv
# ---------------------------------------------------------------------------


def test_write_template_csv_creates_file(tmp_path: Path) -> None:
    out = tmp_path / "template.csv"
    write_template_csv(out)
    assert out.exists()


def test_write_template_csv_has_required_columns(tmp_path: Path) -> None:
    out = tmp_path / "template.csv"
    write_template_csv(out)
    rows = load_csv(out)
    assert len(rows) >= 1
    assert "code" in rows[0]
    assert "name" in rows[0]
    assert "sector" in rows[0]


def test_write_template_csv_codes_are_valid(tmp_path: Path) -> None:
    out = tmp_path / "template.csv"
    write_template_csv(out)
    rows = load_csv(out)
    for row in rows:
        code = normalize_code(row["code"])
        assert code is not None and len(code) == 6


# ---------------------------------------------------------------------------
# 11. CLI subprocess 테스트
# ---------------------------------------------------------------------------


def test_cli_write_template_subprocess(tmp_path: Path) -> None:
    out = tmp_path / "tmpl.csv"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--write-template", str(out)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert out.exists()
    assert "템플릿 CSV 생성 완료" in result.stdout


def test_cli_dry_run_subprocess(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "code,name,market_cap,sector\n"
        "005930,삼성전자,500000000000000,반도체\n"
        "000660,SK하이닉스,100000000000000,반도체\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--input", str(csv_path), "--dry-run"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout
    assert "codes" in result.stdout


def test_cli_generates_output_files(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "code,name,market_cap,sector\n"
        "005930,삼성전자,500000000000000,반도체\n"
        "000660,SK하이닉스,100000000000000,반도체\n"
        "042660,한화오션,10000000000000,조선\n",
        encoding="utf-8",
    )
    codes_out = tmp_path / "codes.txt"
    sm_out = tmp_path / "sector_map.json"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--input", str(csv_path),
         "--output-codes", str(codes_out),
         "--output-sector-map", str(sm_out),
         "--limit", "3"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert codes_out.exists()
    assert sm_out.exists()
    codes = codes_out.read_text(encoding="utf-8").splitlines()
    assert len(codes) == 3
    sm = json.loads(sm_out.read_text(encoding="utf-8"))
    assert "005930" in sm


def test_cli_no_input_exits_2() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stdout


def test_cli_missing_input_file_exits_2(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--input", str(tmp_path / "nonexistent.csv")],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stdout


def test_cli_limit_option(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    rows = "\n".join(
        f"{i:06d},종목{i},{i * 1_000_000_000_000},섹터A"
        for i in range(1, 21)
    )
    csv_path.write_text(f"code,name,market_cap,sector\n{rows}\n", encoding="utf-8")
    codes_out = tmp_path / "codes.txt"
    subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--input", str(csv_path),
         "--output-codes", str(codes_out),
         "--output-sector-map", str(tmp_path / "sm.json"),
         "--limit", "5"],
        capture_output=True, text=True, timeout=15,
    )
    codes = codes_out.read_text(encoding="utf-8").splitlines()
    assert len(codes) == 5


# ---------------------------------------------------------------------------
# 12. theme_map.csv 형식 호환 (기존 data/theme_map.csv 구조)
# ---------------------------------------------------------------------------


def test_theme_map_csv_format(tmp_path: Path) -> None:
    csv_path = tmp_path / "theme_map.csv"
    csv_path.write_text(
        "code,name,theme1,theme2,theme3\n"
        "005930,삼성전자,반도체,메모리,AI반도체\n"
        "000660,SK하이닉스,반도체,메모리,HBM\n"
        "042660,한화오션,조선,방산,\n",
        encoding="utf-8",
    )
    rows = load_csv(csv_path)
    result = build_from_csv(rows, limit=10)
    # theme1 이 sector 로 사용되어 sector_map 에 매핑돼야 한다
    assert result.sector_map.get("005930") == ["반도체"]
    assert result.sector_map.get("042660") == ["조선"]
    assert len(result.warnings) == 0  # 모두 매핑됨


def test_theme_map_csv_multi_sector(tmp_path: Path) -> None:
    csv_path = tmp_path / "theme_map.csv"
    csv_path.write_text(
        "code,name,theme1,theme2,theme3\n"
        "005930,삼성전자,반도체,메모리,AI반도체\n",
        encoding="utf-8",
    )
    rows = load_csv(csv_path)
    result = build_from_csv(rows, limit=10, multi_sector=True)
    assert result.sector_map["005930"] == ["반도체", "메모리", "AI반도체"]
