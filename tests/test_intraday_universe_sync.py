"""src/intraday_universe_sync.py 단위 테스트."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.intraday_universe_sync import (
    generate_sector_map_from_theme_map,
    generate_universe_codes,
    validate_universe_consistency,
    write_sector_map_json,
    write_universe_txt,
)


# ---------------------------------------------------------------------------
# CSV fixture helpers
# ---------------------------------------------------------------------------


def _write_theme_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["code", "name", "theme1", "theme2", "theme3"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


# ---------------------------------------------------------------------------
# 1. generate_sector_map_from_theme_map — 기본 동작
# ---------------------------------------------------------------------------


def test_sector_map_basic(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "name": "삼성전자", "theme1": "반도체", "theme2": "메모리", "theme3": ""},
        {"code": "042660", "name": "한화오션", "theme1": "조선", "theme2": "", "theme3": ""},
    ])
    sm = generate_sector_map_from_theme_map(f)
    assert sm["005930"] == ["반도체"]
    assert sm["042660"] == ["조선"]


def test_sector_map_theme1_only_is_default(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체", "theme2": "메모리", "theme3": "AI반도체"},
    ])
    sm = generate_sector_map_from_theme_map(f)
    # theme1 만 포함, theme2/theme3 제외
    assert sm["005930"] == ["반도체"]
    assert len(sm["005930"]) == 1


def test_sector_map_multi_sector(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체", "theme2": "메모리", "theme3": "AI반도체"},
    ])
    sm = generate_sector_map_from_theme_map(f, theme1_only=False)
    assert sm["005930"] == ["반도체", "메모리", "AI반도체"]


def test_sector_map_multi_sector_empty_theme3(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체", "theme2": "메모리", "theme3": ""},
    ])
    sm = generate_sector_map_from_theme_map(f, theme1_only=False)
    assert sm["005930"] == ["반도체", "메모리"]


# ---------------------------------------------------------------------------
# 2. generate_sector_map_from_theme_map — 검증 정책
# ---------------------------------------------------------------------------


def test_sector_map_excludes_empty_theme1(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체"},
        {"code": "000001", "theme1": ""},   # 제외
    ])
    sm = generate_sector_map_from_theme_map(f)
    assert "005930" in sm
    assert "000001" not in sm


def test_sector_map_code_is_zero_padded(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [{"code": "5930", "theme1": "반도체"}])
    sm = generate_sector_map_from_theme_map(f)
    assert "005930" in sm
    assert "5930" not in sm


def test_sector_map_deduplicates_code(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체"},
        {"code": "005930", "theme1": "대형주"},  # 중복 → 첫 번째만
    ])
    sm = generate_sector_map_from_theme_map(f)
    assert sm["005930"] == ["반도체"]


def test_sector_map_skips_non_numeric_code(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "ABCDEF", "theme1": "반도체"},
        {"code": "005930", "theme1": "반도체"},
    ])
    sm = generate_sector_map_from_theme_map(f)
    assert "ABCDEF" not in sm
    assert "005930" in sm


def test_sector_map_skips_seven_digit_code(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "1234567", "theme1": "반도체"},
    ])
    sm = generate_sector_map_from_theme_map(f)
    assert len(sm) == 0


# ---------------------------------------------------------------------------
# 3. generate_universe_codes
# ---------------------------------------------------------------------------


def test_universe_codes_basic(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체"},
        {"code": "000660", "theme1": "반도체"},
        {"code": "042660", "theme1": "조선"},
    ])
    codes = generate_universe_codes(f)
    assert codes == ["005930", "000660", "042660"]


def test_universe_codes_excludes_empty_theme1(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체"},
        {"code": "000001", "theme1": ""},
    ])
    codes = generate_universe_codes(f)
    assert "005930" in codes
    assert "000001" not in codes


def test_universe_codes_zero_pads(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [{"code": "5930", "theme1": "반도체"}])
    codes = generate_universe_codes(f)
    assert "005930" in codes


def test_universe_codes_deduplicates(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "005930", "theme1": "반도체"},
        {"code": "005930", "theme1": "대형주"},
    ])
    codes = generate_universe_codes(f)
    assert codes.count("005930") == 1


def test_universe_codes_preserves_order(tmp_path: Path) -> None:
    f = tmp_path / "tm.csv"
    _write_theme_csv(f, [
        {"code": "042660", "theme1": "조선"},
        {"code": "005930", "theme1": "반도체"},
        {"code": "000660", "theme1": "반도체"},
    ])
    codes = generate_universe_codes(f)
    assert codes == ["042660", "005930", "000660"]


# ---------------------------------------------------------------------------
# 4. validate_universe_consistency
# ---------------------------------------------------------------------------


def test_validate_consistency_ok() -> None:
    sm = {"005930": ["반도체"], "042660": ["조선"]}
    codes = ["005930", "042660"]
    ok, issues = validate_universe_consistency(sm, codes)
    assert ok is True
    assert issues == []


def test_validate_consistency_in_sm_not_in_universe() -> None:
    sm = {"005930": ["반도체"], "000001": ["기타"]}
    codes = ["005930"]
    ok, issues = validate_universe_consistency(sm, codes)
    assert ok is False
    assert any("sector_map" in i for i in issues)


def test_validate_consistency_in_universe_not_in_sm() -> None:
    sm = {"005930": ["반도체"]}
    codes = ["005930", "000001"]
    ok, issues = validate_universe_consistency(sm, codes)
    assert ok is False
    assert any("universe" in i for i in issues)


def test_validate_consistency_set_input() -> None:
    sm = {"005930": ["반도체"]}
    ok, _ = validate_universe_consistency(sm, {"005930"})
    assert ok is True


# ---------------------------------------------------------------------------
# 5. write helpers
# ---------------------------------------------------------------------------


def test_write_sector_map_json(tmp_path: Path) -> None:
    out = tmp_path / "sm.json"
    sm = {"005930": ["반도체"], "042660": ["조선"]}
    write_sector_map_json(sm, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == sm


def test_write_universe_txt(tmp_path: Path) -> None:
    out = tmp_path / "codes.txt"
    write_universe_txt(["005930", "000660"], out)
    lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    assert lines == ["005930", "000660"]


def test_write_universe_txt_with_comment(tmp_path: Path) -> None:
    out = tmp_path / "codes.txt"
    write_universe_txt(["005930"], out, comment="generated from theme_map.csv")
    content = out.read_text(encoding="utf-8")
    assert "# generated from theme_map.csv" in content
    assert "005930" in content


# ---------------------------------------------------------------------------
# 6. 실제 data/theme_map.csv 와 data/sector_map.json 일관성 검증
# ---------------------------------------------------------------------------


def test_data_files_are_consistent() -> None:
    """data/ 디렉토리의 3개 파일이 일치하는지 자동 검증한다."""
    import csv as _csv
    import json as _json
    from pathlib import Path as _Path

    project_root = _Path(__file__).resolve().parents[1]
    theme_map_path = project_root / "data" / "theme_map.csv"
    sector_map_path = project_root / "data" / "sector_map.json"
    universe_path = project_root / "data" / "universe_codes_150.txt"

    if not all(p.exists() for p in [theme_map_path, sector_map_path, universe_path]):
        pytest.skip("data 파일이 없어서 일관성 검증 생략")

    sm_from_csv = generate_sector_map_from_theme_map(theme_map_path)
    codes_from_csv = generate_universe_codes(theme_map_path)

    sm_from_json = _json.loads(sector_map_path.read_text(encoding="utf-8"))
    codes_from_txt = [
        l.strip().zfill(6)
        for l in universe_path.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]

    # sector_map.json 과 theme_map.csv(theme1_only) 일치 확인
    ok1, issues1 = validate_universe_consistency(sm_from_csv, set(sm_from_json.keys()))
    assert ok1, f"sector_map.json vs theme_map.csv 불일치: {issues1}"

    # universe_codes_150.txt 와 theme_map.csv 일치 확인
    ok2, issues2 = validate_universe_consistency(sm_from_json, codes_from_txt)
    assert ok2, f"universe_codes_150.txt vs sector_map.json 불일치: {issues2}"
