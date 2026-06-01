"""Tests for bulk WebSocket smoke test helpers.

Imports testable functions from scripts/test_kiwoom_ws_bulk.py using a
unique importlib module name to avoid pytest collection conflicts.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

# ---------------------------------------------------------------------------
# Import helpers from the bulk script with a unique module name
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "test_kiwoom_ws_bulk.py"
_spec = importlib.util.spec_from_file_location("_kiwoom_ws_bulk_script", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
# Register before exec_module so @dataclass can resolve cls.__module__ via sys.modules.
sys.modules["_kiwoom_ws_bulk_script"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

parse_codes_file = _mod.parse_codes_file
validate_codes = _mod.validate_codes
apply_max_codes = _mod.apply_max_codes
format_bulk_codes = _mod.format_bulk_codes
build_reg_groups = _mod.build_reg_groups
format_reg_summary = _mod.format_reg_summary
BulkTickAccumulator = _mod.BulkTickAccumulator

from src.kiwoom_websocket import KiwoomRawMessage


# ---------------------------------------------------------------------------
# parse_codes_file
# ---------------------------------------------------------------------------


def test_parse_codes_file_basic(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("000660\n005930\n", encoding="utf-8")

    codes = parse_codes_file(f)

    assert codes == ["000660", "005930"]


def test_parse_codes_file_deduplicates(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("000660\n000660\n005930\n", encoding="utf-8")

    codes = parse_codes_file(f)

    assert codes.count("000660") == 1
    assert len(codes) == 2


def test_parse_codes_file_skips_blank_and_comments(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("# 삼성전자\n000660\n\n# SK하이닉스\n000660\n", encoding="utf-8")

    codes = parse_codes_file(f)

    assert codes == ["000660"]


def test_parse_codes_file_zero_pads_short_code(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("5930\n", encoding="utf-8")

    codes = parse_codes_file(f)

    assert codes == ["005930"]


def test_parse_codes_file_excludes_non_numeric(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("000660\nABCDEF\n1234567\n", encoding="utf-8")

    codes = parse_codes_file(f)

    assert "000660" in codes
    assert not any("ABCDEF" in c for c in codes)
    assert not any(len(c) > 6 for c in codes)
    captured = capsys.readouterr()
    assert "skipping invalid code" in captured.out


# ---------------------------------------------------------------------------
# validate_codes
# ---------------------------------------------------------------------------


def test_validate_codes_accepts_valid() -> None:
    valid, invalid = validate_codes(["000660", "005930"])

    assert valid == ["000660", "005930"]
    assert invalid == []


def test_validate_codes_deduplicates() -> None:
    valid, _ = validate_codes(["000660", "000660", "005930"])

    assert valid.count("000660") == 1
    assert len(valid) == 2


def test_validate_codes_zero_pads() -> None:
    valid, _ = validate_codes(["5930"])

    assert "005930" in valid


def test_validate_codes_rejects_non_numeric() -> None:
    valid, invalid = validate_codes(["000660", "ABCDEF"])

    assert "000660" in valid
    assert "ABCDEF" in invalid


def test_validate_codes_rejects_too_long() -> None:
    _, invalid = validate_codes(["1234567"])

    assert "1234567" in invalid


# ---------------------------------------------------------------------------
# apply_max_codes
# ---------------------------------------------------------------------------


def test_apply_max_codes_limits() -> None:
    codes = ["000660", "005930", "035720", "000080"]

    assert apply_max_codes(codes, 2) == ["000660", "005930"]


def test_apply_max_codes_zero_means_no_limit() -> None:
    codes = ["000660", "005930", "035720"]

    assert apply_max_codes(codes, 0) == codes


def test_apply_max_codes_larger_than_list() -> None:
    codes = ["000660", "005930"]

    assert apply_max_codes(codes, 100) == codes


# ---------------------------------------------------------------------------
# format_bulk_codes
# ---------------------------------------------------------------------------


def test_format_bulk_codes_krx_no_suffix() -> None:
    result = format_bulk_codes(["000660", "005930"], "krx")

    assert result == ["000660", "005930"]


def test_format_bulk_codes_nxt_suffix() -> None:
    result = format_bulk_codes(["000660"], "nxt")

    assert result == ["000660_NX"]


def test_format_bulk_codes_sor_suffix() -> None:
    result = format_bulk_codes(["000660"], "sor")

    assert result == ["000660_AL"]


def test_format_bulk_codes_all_triples_count() -> None:
    base = ["000660", "005930"]
    result = format_bulk_codes(base, "all")

    assert len(result) == len(base) * 3


def test_format_bulk_codes_all_contains_all_exchanges() -> None:
    result = format_bulk_codes(["000660"], "all")

    assert "000660" in result       # krx
    assert "000660_NX" in result    # nxt
    assert "000660_AL" in result    # sor


def test_format_bulk_codes_all_order_is_krx_nxt_sor() -> None:
    result = format_bulk_codes(["000660"], "all")

    assert result == ["000660", "000660_NX", "000660_AL"]


# ---------------------------------------------------------------------------
# BulkTickAccumulator
# ---------------------------------------------------------------------------


def _make_real_msg(item: str, price: str = "+72000") -> KiwoomRawMessage:
    payload = json.dumps({
        "trnm": "REAL",
        "data": [{"item": item, "type": "0B", "name": "주식체결", "10": price}],
    })
    return KiwoomRawMessage(raw=payload, received_at="2026-06-01T13:00:00")


def test_accumulator_counts_message_and_rows() -> None:
    acc = BulkTickAccumulator()
    rows = acc.add_message(_make_real_msg("000660"))

    assert rows == 1
    assert acc.total_messages == 1
    assert acc.total_rows == 1


def test_accumulator_counts_by_item() -> None:
    acc = BulkTickAccumulator()
    acc.add_message(_make_real_msg("000660"))
    acc.add_message(_make_real_msg("000660"))
    acc.add_message(_make_real_msg("005930"))

    assert acc.rows_by_item["000660"] == 2
    assert acc.rows_by_item["005930"] == 1


def test_accumulator_counts_by_exchange() -> None:
    acc = BulkTickAccumulator()
    acc.add_message(_make_real_msg("000660"))       # krx
    acc.add_message(_make_real_msg("000660_NX"))    # nxt
    acc.add_message(_make_real_msg("000660_AL"))    # sor

    assert acc.rows_by_exchange.get("krx") == 1
    assert acc.rows_by_exchange.get("nxt") == 1
    assert acc.rows_by_exchange.get("sor") == 1


def test_accumulator_top_items() -> None:
    acc = BulkTickAccumulator()
    for _ in range(3):
        acc.add_message(_make_real_msg("000660"))
    acc.add_message(_make_real_msg("005930"))

    top = acc.top_items(2)

    assert top[0] == ("000660", 3)
    assert top[1] == ("005930", 1)


def test_accumulator_unique_base_codes_strips_suffix() -> None:
    acc = BulkTickAccumulator()
    acc.add_message(_make_real_msg("000660"))
    acc.add_message(_make_real_msg("000660_NX"))
    acc.add_message(_make_real_msg("000660_AL"))

    # 세 아이템 모두 같은 base code
    assert acc.unique_base_codes() == {"000660"}


def test_accumulator_multi_row_message() -> None:
    """단일 REAL 메시지에 data row가 여러 개일 때 각 row를 별도로 집계한다."""
    payload = json.dumps({
        "trnm": "REAL",
        "data": [
            {"item": "000660", "type": "0B", "name": "주식체결", "10": "+72000"},
            {"item": "005930", "type": "0B", "name": "주식체결", "10": "+55000"},
        ],
    })
    msg = KiwoomRawMessage(raw=payload, received_at="2026-06-01T13:00:00")
    acc = BulkTickAccumulator()

    rows = acc.add_message(msg)

    assert rows == 2
    assert acc.total_rows == 2
    assert acc.total_messages == 1
    assert acc.rows_by_item["000660"] == 1
    assert acc.rows_by_item["005930"] == 1


def test_accumulator_mock_flat_message() -> None:
    """mock provider의 flat REAL 메시지(data 배열 없음)도 정상 집계된다."""
    payload = json.dumps({
        "provider": "mock",
        "trnm": "REAL",
        "type": "0B",
        "code": "000660",
        "name": "SK하이닉스",
        "current_price": 70000,
        "change_rate": 0.5,
    })
    msg = KiwoomRawMessage(raw=payload, received_at="2026-06-01T13:00:00")
    acc = BulkTickAccumulator()

    rows = acc.add_message(msg)

    assert rows == 1
    assert acc.rows_by_item.get("000660") == 1
    assert acc.rows_by_exchange.get("krx") == 1


# ---------------------------------------------------------------------------
# build_reg_groups — REG 그룹 청킹 (Kiwoom 그룹당 200종목 제한)
# ---------------------------------------------------------------------------


def _make_codes(n: int, suffix: str = "_AL") -> list[str]:
    return [f"{i:06d}{suffix}" for i in range(n)]


def test_build_reg_groups_199_is_single_group() -> None:
    codes = _make_codes(199)
    groups = build_reg_groups(codes, 200)
    assert len(groups) == 1
    assert groups[0][0] == "1"
    assert len(groups[0][1]) == 199


def test_build_reg_groups_200_is_single_group() -> None:
    codes = _make_codes(200)
    groups = build_reg_groups(codes, 200)
    assert len(groups) == 1
    assert len(groups[0][1]) == 200


def test_build_reg_groups_201_splits_200_1() -> None:
    codes = _make_codes(201)
    groups = build_reg_groups(codes, 200)
    assert len(groups) == 2
    assert groups[0][0] == "1"
    assert groups[1][0] == "2"
    assert len(groups[0][1]) == 200
    assert len(groups[1][1]) == 1


def test_build_reg_groups_300_splits_200_100() -> None:
    codes = _make_codes(300)
    groups = build_reg_groups(codes, 200)
    assert len(groups) == 2
    assert groups[0][1] == codes[:200]
    assert groups[1][1] == codes[200:]
    assert len(groups[1][1]) == 100


def test_build_reg_groups_401_splits_200_200_1() -> None:
    codes = _make_codes(401)
    groups = build_reg_groups(codes, 200)
    assert len(groups) == 3
    assert len(groups[0][1]) == 200
    assert len(groups[1][1]) == 200
    assert len(groups[2][1]) == 1


def test_build_reg_groups_custom_batch_size() -> None:
    codes = _make_codes(10, suffix="")
    groups = build_reg_groups(codes, 3)
    assert len(groups) == 4   # 3+3+3+1
    assert len(groups[0][1]) == 3
    assert len(groups[3][1]) == 1
    assert [g[0] for g in groups] == ["1", "2", "3", "4"]


def test_build_reg_groups_invalid_batch_size_raises() -> None:
    with pytest.raises(ValueError):
        build_reg_groups(_make_codes(5), 0)


# ---------------------------------------------------------------------------
# format_reg_summary
# ---------------------------------------------------------------------------


def test_format_reg_summary_single_ok() -> None:
    assert format_reg_summary({"1": True}, 1) == "OK"


def test_format_reg_summary_single_failed() -> None:
    assert format_reg_summary({"1": False}, 1) == "FAILED"


def test_format_reg_summary_single_none() -> None:
    assert format_reg_summary({"1": None}, 1) == "N/A"


def test_format_reg_summary_multi_all_ok() -> None:
    result = format_reg_summary({"1": True, "2": True}, 2)
    assert result == "OK groups=2/2"


def test_format_reg_summary_multi_partial() -> None:
    result = format_reg_summary({"1": True, "2": False}, 2)
    assert "PARTIAL" in result
    assert "groups=1/2" in result
    assert "failed_groups=2" in result


def test_format_reg_summary_multi_all_failed() -> None:
    result = format_reg_summary({"1": False, "2": False}, 2)
    assert result == "FAILED groups=0/2"


def test_format_reg_summary_empty() -> None:
    assert format_reg_summary({}, 0) == "N/A"


# ---------------------------------------------------------------------------
# dry-run — WebSocket 연결 없이 청킹 계획 출력
# ---------------------------------------------------------------------------


def test_dry_run_shows_chunk_plan() -> None:
    """--dry-run은 WebSocket 연결 없이 REG 분할 계획을 출력하고 종료(rc=0)한다."""
    codes = ",".join(f"{i:06d}" for i in range(10))
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--dry-run", "--exchange", "sor",
            "--codes", codes,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    out = result.stdout
    assert result.returncode == 0, f"non-zero exit: {result.stderr}"
    assert "DRY RUN" in out
    assert "formatted_code_count = 10" in out
    assert "reg_batch_size       = 200" in out
    assert "reg_group_count      = 1" in out   # 10 codes → single group
    assert "REG group 1" in out


def test_dry_run_300_codes_shows_two_groups(tmp_path: Path) -> None:
    """300종목 dry-run → group 1(200) + group 2(100) 계획 출력."""
    codes_file = tmp_path / "codes.txt"
    codes_file.write_text("\n".join(f"{i:06d}" for i in range(300)), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--dry-run", "--exchange", "sor",
            "--codes-file", str(codes_file),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    out = result.stdout
    assert result.returncode == 0, f"non-zero exit: {result.stderr}"
    assert "formatted_code_count = 300" in out
    assert "reg_group_count      = 2" in out
    assert "REG group 1: 200 items" in out
    assert "REG group 2: 100 items" in out


def test_dry_run_300_codes_shows_over_limit_warning(tmp_path: Path) -> None:
    """300종목 dry-run → 200 상한 초과 경고 출력."""
    codes_file = tmp_path / "codes.txt"
    codes_file.write_text("\n".join(f"{i:06d}" for i in range(300)), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--dry-run", "--exchange", "sor",
            "--codes-file", str(codes_file),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "WARNING" in result.stdout


# ---------------------------------------------------------------------------
# 200종목 상한 차단 (provider=websocket)
# ---------------------------------------------------------------------------


def test_websocket_200_codes_allowed() -> None:
    """200종목 + provider=websocket → 상한 이내이므로 limit 차단 없음.
    dry-run으로 WebSocket 연결 없이 확인 (실전 연결 시도 금지).
    """
    codes = ",".join(f"{i:06d}" for i in range(200))
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--dry-run",
            "--provider", "websocket",
            "--exchange", "sor",
            "--codes", codes,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "ERROR: formatted_code_count=200" not in result.stdout
    # 200종목은 상한 이내이므로 WARNING도 없어야 함
    assert "[WARNING] formatted_code_count=200" not in result.stdout


def test_websocket_201_codes_blocked() -> None:
    """201종목 + provider=websocket → 200 상한 초과로 즉시 차단 (rc=2)."""
    codes = ",".join(f"{i:06d}" for i in range(201))
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--provider", "websocket",
            "--exchange", "sor",
            "--codes", codes,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stdout
    assert "formatted_code_count=201" in result.stdout


def test_websocket_300_codes_blocked() -> None:
    """300종목 + provider=websocket → 차단."""
    codes = ",".join(f"{i:06d}" for i in range(300))
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--provider", "websocket",
            "--exchange", "sor",
            "--codes", codes,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stdout


def test_websocket_201_codes_experimental_not_blocked() -> None:
    """201종목 + --allow-over-200-experimental + dry-run → 차단 없이 WARNING 출력.
    dry-run으로 WebSocket 연결 없이 확인 (실전 연결 시도 금지).
    """
    codes = ",".join(f"{i:06d}" for i in range(201))
    result = subprocess.run(
        [
            sys.executable, str(_SCRIPT_PATH),
            "--dry-run",
            "--provider", "websocket",
            "--exchange", "sor",
            "--codes", codes,
            "--allow-over-200-experimental",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    # limit 차단이 아닌 dry-run 정상 완료
    assert result.returncode == 0
    # 실험 플래그 사용 시 WARNING이 출력되어야 함
    assert "WARNING" in result.stdout
    assert "실패 가능성" in result.stdout
