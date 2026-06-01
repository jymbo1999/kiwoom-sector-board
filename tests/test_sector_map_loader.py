"""src/sector_map_loader.py 단위 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sector_map_loader import (
    SectorMapLoadError,
    SectorMapLoadResult,
    load_sector_map,
)


# ---------------------------------------------------------------------------
# 1. 정상 로드
# ---------------------------------------------------------------------------


def test_load_valid_sector_map(tmp_path: Path) -> None:
    data = {"000660": ["반도체"], "005930": ["반도체", "대형주"]}
    f = tmp_path / "sector_map.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f)
    assert res.sector_map["000660"] == ["반도체"]
    assert res.sector_map["005930"] == ["반도체", "대형주"]
    assert res.warnings == []


def test_load_returns_sector_map_load_result_type(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text('{"000660": ["반도체"]}', encoding="utf-8")
    res = load_sector_map(f)
    assert isinstance(res, SectorMapLoadResult)


# ---------------------------------------------------------------------------
# 2. 코드 key zero-padding
# ---------------------------------------------------------------------------


def test_short_code_is_zero_padded(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text('{"5930": ["반도체"]}', encoding="utf-8")
    res = load_sector_map(f)
    assert "005930" in res.sector_map
    assert "5930" not in res.sector_map


def test_already_six_digit_code_unchanged(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text('{"000660": ["반도체"]}', encoding="utf-8")
    res = load_sector_map(f)
    assert "000660" in res.sector_map


def test_code_with_spaces_stripped_and_padded(tmp_path: Path) -> None:
    data = {"  5930 ": ["반도체"]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f)
    assert "005930" in res.sector_map


# ---------------------------------------------------------------------------
# 3. 파일 없음 → FileNotFoundError
# ---------------------------------------------------------------------------


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_sector_map(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# 4. JSON 파싱 실패 → SectorMapLoadError(ValueError)
# ---------------------------------------------------------------------------


def test_bad_json_raises_sector_map_load_error(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("this is not json", encoding="utf-8")
    with pytest.raises(SectorMapLoadError):
        load_sector_map(f)


def test_bad_json_is_also_value_error(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        load_sector_map(f)


# ---------------------------------------------------------------------------
# 5. 최상위 타입 오류 → SectorMapLoadError
# ---------------------------------------------------------------------------


def test_top_level_list_raises_error(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SectorMapLoadError, match="JSON object"):
        load_sector_map(f)


def test_top_level_string_raises_error(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text('"just a string"', encoding="utf-8")
    with pytest.raises(SectorMapLoadError):
        load_sector_map(f)


# ---------------------------------------------------------------------------
# 6. non-list value: strict=False → warning + skip, strict=True → raises
# ---------------------------------------------------------------------------


def test_non_list_value_strict_false_produces_warning(tmp_path: Path) -> None:
    data = {"000660": "반도체"}  # string, not list
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f, strict=False)
    assert "000660" not in res.sector_map
    assert len(res.warnings) == 1
    assert "000660" in res.warnings[0]


def test_non_list_value_strict_true_raises(tmp_path: Path) -> None:
    data = {"000660": "반도체"}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SectorMapLoadError, match="list"):
        load_sector_map(f, strict=True)


def test_non_list_value_int_strict_false_produces_warning(tmp_path: Path) -> None:
    data = {"000660": 12345}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f, strict=False)
    assert "000660" not in res.sector_map
    assert res.warnings


def test_non_list_value_null_strict_false_produces_warning(tmp_path: Path) -> None:
    data = {"000660": None}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f, strict=False)
    assert "000660" not in res.sector_map
    assert res.warnings


# ---------------------------------------------------------------------------
# 7. non-string sector item: strict=False → warning, strict=True → raises
# ---------------------------------------------------------------------------


def test_non_string_sector_item_strict_false_warning(tmp_path: Path) -> None:
    data = {"000660": ["반도체", 123, None]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f, strict=False)
    # "반도체" 는 유효하게 남아야 한다
    assert res.sector_map.get("000660") == ["반도체"]
    assert len(res.warnings) == 2  # 123 and None


def test_non_string_sector_item_strict_true_raises(tmp_path: Path) -> None:
    data = {"000660": ["반도체", 999]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SectorMapLoadError):
        load_sector_map(f, strict=True)


def test_empty_string_sector_item_is_ignored(tmp_path: Path) -> None:
    data = {"000660": ["반도체", "", "  "]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f, strict=False)
    # 빈 문자열은 경고도 아니고 조용히 제외
    assert res.sector_map["000660"] == ["반도체"]


# ---------------------------------------------------------------------------
# 8. 복합 케이스: 유효 entry + 무효 entry 혼재 (strict=False)
# ---------------------------------------------------------------------------


def test_mixed_valid_invalid_entries(tmp_path: Path) -> None:
    data = {
        "000660": ["반도체"],
        "005930": "잘못된값",       # non-list → warning
        "042660": ["조선", "방산"],
    }
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    res = load_sector_map(f, strict=False)
    assert res.sector_map["000660"] == ["반도체"]
    assert "005930" not in res.sector_map
    assert res.sector_map["042660"] == ["조선", "방산"]
    assert len(res.warnings) == 1
    assert "005930" in res.warnings[0]


# ---------------------------------------------------------------------------
# 9. 빈 파일 / 빈 object
# ---------------------------------------------------------------------------


def test_empty_object_returns_empty_map(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text("{}", encoding="utf-8")
    res = load_sector_map(f)
    assert res.sector_map == {}
    assert res.warnings == []


# ---------------------------------------------------------------------------
# 10. Path 또는 str 모두 허용
# ---------------------------------------------------------------------------


def test_accepts_str_path(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text('{"000660": ["반도체"]}', encoding="utf-8")
    res = load_sector_map(str(f))
    assert "000660" in res.sector_map


# ---------------------------------------------------------------------------
# 11. warnings 필드가 list 임을 확인
# ---------------------------------------------------------------------------


def test_warnings_field_is_list(tmp_path: Path) -> None:
    f = tmp_path / "sm.json"
    f.write_text('{"000660": ["반도체"]}', encoding="utf-8")
    res = load_sector_map(f)
    assert isinstance(res.warnings, list)
