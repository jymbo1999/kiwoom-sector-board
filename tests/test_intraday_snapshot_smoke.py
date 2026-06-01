"""run_intraday_snapshot_smoke.py 헬퍼 단위 테스트.

실전 WebSocket 접속 없이 순수 로직만 테스트한다.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

# ---------------------------------------------------------------------------
# smoke script에서 testable 함수 import (importlib)
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_intraday_snapshot_smoke.py"
_spec = importlib.util.spec_from_file_location("_smoke_script", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)   # type: ignore[arg-type]
sys.modules["_smoke_script"] = _mod
_spec.loader.exec_module(_mod)                  # type: ignore[union-attr]

parse_codes_str       = _mod.parse_codes_str
parse_codes_file      = _mod.parse_codes_file
apply_max_codes       = _mod.apply_max_codes
format_codes          = _mod.format_codes
get_fallback_sector_map = _mod.get_fallback_sector_map
load_sector_map_file  = _mod.load_sector_map_file
make_mock_real_message = _mod.make_mock_real_message
format_snapshot_summary = _mod.format_snapshot_summary
format_final_summary  = _mod.format_final_summary
snapshot_to_dict      = _mod.snapshot_to_dict

from src.intraday_snapshot_service import IntradaySnapshot, IntradaySnapshotService
from src.kiwoom_websocket import normalize_tick_rows


# ---------------------------------------------------------------------------
# 1. codes 문자열 파싱
# ---------------------------------------------------------------------------


def test_parse_codes_str_basic() -> None:
    result = parse_codes_str("005930,000660,035420")
    assert set(result) == {"005930", "000660", "035420"}


def test_parse_codes_str_skips_invalid() -> None:
    result = parse_codes_str("005930,INVALID,000660")
    assert "005930" in result
    assert "000660" in result
    assert not any("INVALID" in c for c in result)


# ---------------------------------------------------------------------------
# 2. codes-file 파싱
# ---------------------------------------------------------------------------


def test_parse_codes_file_basic(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("005930\n# 주석\n000660\n\n035420\n", encoding="utf-8")
    result = parse_codes_file(f)
    assert set(result) == {"005930", "000660", "035420"}


def test_parse_codes_file_skips_comments(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("# 전체 주석\n005930\n", encoding="utf-8")
    assert parse_codes_file(f) == ["005930"]


# ---------------------------------------------------------------------------
# 3. 6자리 zero-padding
# ---------------------------------------------------------------------------


def test_zero_pad_short_code() -> None:
    result = parse_codes_str("5930")
    assert "005930" in result


def test_zero_pad_from_file(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("5930\n", encoding="utf-8")
    assert parse_codes_file(f) == ["005930"]


# ---------------------------------------------------------------------------
# 4. 중복 제거
# ---------------------------------------------------------------------------


def test_dedup_codes_str() -> None:
    result = parse_codes_str("005930,005930,000660")
    assert result.count("005930") == 1
    assert len(result) == 2


def test_dedup_codes_file(tmp_path: Path) -> None:
    f = tmp_path / "codes.txt"
    f.write_text("005930\n005930\n000660\n", encoding="utf-8")
    result = parse_codes_file(f)
    assert result.count("005930") == 1


# ---------------------------------------------------------------------------
# 5. max-codes 적용
# ---------------------------------------------------------------------------


def test_apply_max_codes_limits() -> None:
    codes = ["000001", "000002", "000003", "000004"]
    assert apply_max_codes(codes, 2) == ["000001", "000002"]


def test_apply_max_codes_zero_means_no_limit() -> None:
    codes = ["000001", "000002", "000003"]
    assert apply_max_codes(codes, 0) == codes


# ---------------------------------------------------------------------------
# 6. exchange별 formatted code (krx/nxt/sor)
# ---------------------------------------------------------------------------


def test_format_codes_krx() -> None:
    assert format_codes(["000660"], "krx") == ["000660"]


def test_format_codes_nxt() -> None:
    assert format_codes(["000660"], "nxt") == ["000660_NX"]


def test_format_codes_sor() -> None:
    assert format_codes(["000660"], "sor") == ["000660_AL"]


# ---------------------------------------------------------------------------
# 7. 200개 초과 → websocket 차단 (subprocess)
# ---------------------------------------------------------------------------


def test_over_limit_blocked_websocket_subprocess() -> None:
    """201코드 + --provider websocket → rc=2, ERROR 메시지.
    --max-codes 201로 자르지 않도록 설정.
    """
    codes = ",".join(f"{i:06d}" for i in range(201))
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--provider", "websocket", "--exchange", "sor",
         "--codes", codes, "--max-codes", "201",
         "--allow-fallback-sector-map"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stdout


# ---------------------------------------------------------------------------
# 8. dry-run에서는 200개 초과도 차단하지 않고 WARNING 출력
# ---------------------------------------------------------------------------


def test_dry_run_over_limit_not_blocked() -> None:
    """201코드 + --dry-run → rc=0, WARNING 출력.
    --max-codes 201로 자르지 않도록 설정.
    """
    codes = ",".join(f"{i:06d}" for i in range(201))
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--dry-run", "--provider", "websocket", "--exchange", "sor",
         "--codes", codes, "--max-codes", "201"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "WARNING" in result.stdout
    assert "DRY RUN" in result.stdout


# ---------------------------------------------------------------------------
# 9. fallback sector_map 생성
# ---------------------------------------------------------------------------


def test_fallback_sector_map_has_expected_sectors() -> None:
    sm = get_fallback_sector_map()
    sectors = {s for sectors in sm.values() for s in sectors}
    assert "반도체" in sectors
    assert "조선" in sectors
    assert "바이오" in sectors
    assert len(sm) >= 5


def test_fallback_sector_map_no_credentials() -> None:
    sm = get_fallback_sector_map()
    text = json.dumps(sm)
    for key in ("token", "appkey", "secretkey"):
        assert key not in text.lower()


# ---------------------------------------------------------------------------
# 10. sector-map-file JSON 로드
# ---------------------------------------------------------------------------


def test_sector_map_file_load(tmp_path: Path) -> None:
    data = {"000660": ["반도체"], "005930": ["반도체", "대형주"]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    sm = load_sector_map_file(f)
    assert sm["000660"] == ["반도체"]
    assert sm["005930"] == ["반도체", "대형주"]


def test_sector_map_file_zero_pads_keys(tmp_path: Path) -> None:
    data = {"5930": ["반도체"]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    sm = load_sector_map_file(f)
    assert "005930" in sm


# ---------------------------------------------------------------------------
# 11. 잘못된 sector-map-file → 명확한 에러
# ---------------------------------------------------------------------------


def test_invalid_sector_map_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_sector_map_file(tmp_path / "nonexistent.json")


def test_invalid_sector_map_file_bad_json(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("this is not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_sector_map_file(f)


def test_invalid_sector_map_file_wrong_type(tmp_path: Path) -> None:
    f = tmp_path / "wrong.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_sector_map_file(f)


# ---------------------------------------------------------------------------
# 12. mock raw message 생성 → normalize 가능
# ---------------------------------------------------------------------------


def test_mock_raw_message_is_normalizable() -> None:
    msg = make_mock_real_message(
        base_code="000660", exchange="sor",
        price=70000, change_rate=0.5, acc_tv=1_000_000, trade_time="134501",
    )
    rows = normalize_tick_rows(msg)
    assert len(rows) == 1
    assert rows[0]["base_code"] == "000660"
    assert rows[0]["exchange"] == "sor"
    assert rows[0]["current_price"] == 70000
    assert rows[0]["trade_time"] == "134501"


def test_mock_raw_message_negative_change_rate() -> None:
    msg = make_mock_real_message("000660", "sor", 68000, -1.5, 2_000_000, "090001")
    rows = normalize_tick_rows(msg)
    assert len(rows) == 1
    assert rows[0]["change_rate"] == pytest.approx(-1.5)


# ---------------------------------------------------------------------------
# 13. mock stream → SnapshotService → ready
# ---------------------------------------------------------------------------


def test_mock_stream_into_service_reaches_ready() -> None:
    """mock 메시지를 서비스에 주입하면 status=ready에 도달한다."""
    sm = {"000660": ["반도체"], "005930": ["반도체"], "035420": ["인터넷/게임"]}
    svc = IntradaySnapshotService(sm)

    codes = list(sm.keys())
    acc_tv = {c: 1_000_000_000 for c in codes}
    times = ["134501", "134530", "134545"]

    for t in times:
        for c in codes:
            acc_tv[c] += 500_000_000
            msg = make_mock_real_message(c, "sor", 70000, 0.5, acc_tv[c], t)
            svc.ingest_raw_message(msg)

    snap = svc.get_snapshot()
    assert snap.status == "ready"
    assert snap.sector_count >= 1


# ---------------------------------------------------------------------------
# 14. summary formatter 출력 검증
# ---------------------------------------------------------------------------


def test_format_snapshot_summary_empty() -> None:
    svc = IntradaySnapshotService({})
    snap = svc.get_snapshot()
    out = format_snapshot_summary(snap)
    assert "[smoke]" in out
    assert "empty" in out


def test_format_snapshot_summary_ready() -> None:
    sm = {"000660": ["반도체"]}
    svc = IntradaySnapshotService(sm)
    svc.ingest_raw_message(make_mock_real_message("000660", "sor", 70000, 0.5, 1_000_000, "134501"))
    svc.ingest_raw_message(make_mock_real_message("000660", "sor", 70100, 0.6, 5_000_000, "134530"))
    snap = svc.get_snapshot()
    out = format_snapshot_summary(snap)
    assert "반도체" in out or "warming" in out or "empty" in out  # sector or hint


# ---------------------------------------------------------------------------
# 15. snapshot JSON serialization
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_is_json_serializable() -> None:
    svc = IntradaySnapshotService({})
    snap = svc.get_snapshot()
    d = snapshot_to_dict(snap)
    json_str = json.dumps(d)
    assert isinstance(json_str, str)
    assert "generated_at" in d
    assert "status" in d


# ---------------------------------------------------------------------------
# 16. JSONL에 credential 필드 없음
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_no_credentials() -> None:
    svc = IntradaySnapshotService({})
    snap = svc.get_snapshot()
    d = snapshot_to_dict(snap)
    text = json.dumps(d).lower()
    for key in ("token", "appkey", "secretkey"):
        assert key not in text


def test_dump_jsonl_no_credentials(tmp_path: Path) -> None:
    svc = IntradaySnapshotService({})
    snap = svc.get_snapshot()
    jsonl_path = tmp_path / "test.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(snapshot_to_dict(snap)) + "\n")
    content = jsonl_path.read_text(encoding="utf-8").lower()
    for key in ("token", "appkey", "secretkey"):
        assert key not in content


# ---------------------------------------------------------------------------
# 17. final summary formatter
# ---------------------------------------------------------------------------


def test_format_final_summary_contains_key_fields() -> None:
    svc = IntradaySnapshotService({})
    snap = svc.get_snapshot()
    stats = {
        "total_messages": 500,
        "total_ingested_rows": 480,
        "total_snapshots": 5,
        "final_status": "empty",
        "final_sector_count": 0,
        "elapsed_seconds": 30.0,
        "final_snapshot": snap,
    }
    out = format_final_summary(stats)
    assert "total_messages=500" in out
    assert "total_snapshots=5" in out
    assert "elapsed=30.0s" in out


def test_format_final_summary_hint_when_no_sectors() -> None:
    """sector_count=0이면 힌트를 출력한다."""
    svc = IntradaySnapshotService({})
    snap = svc.get_snapshot()
    stats = {
        "total_messages": 10, "total_ingested_rows": 8, "total_snapshots": 1,
        "final_status": "empty", "final_sector_count": 0,
        "elapsed_seconds": 5.0, "final_snapshot": snap,
    }
    out = format_final_summary(stats)
    assert "hint" in out.lower()


# ---------------------------------------------------------------------------
# 18. provider=mock dry-run subprocess
# ---------------------------------------------------------------------------


def test_dry_run_subprocess_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--dry-run", "--exchange", "sor", "--codes", "005930,000660"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "DRY RUN" in result.stdout
    assert "formatted_code_count=2" in result.stdout


def test_dry_run_shows_mapped_codes() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--dry-run", "--exchange", "sor", "--codes", "005930,000660"],
        capture_output=True, text=True, timeout=15,
    )
    assert "mapped_codes" in result.stdout


# ---------------------------------------------------------------------------
# 19. provider=mock 짧은 실행 subprocess
# ---------------------------------------------------------------------------


def test_mock_run_subprocess_exits_zero() -> None:
    """provider=mock으로 3초 실행해 정상 종료하는지 확인한다."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--provider", "mock", "--exchange", "sor",
         "--codes", "005930,000660,035420,000270,042660",
         "--allow-fallback-sector-map",
         "--listen-seconds", "3", "--summary-interval-seconds", "1"],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0
    assert "FINAL SUMMARY" in result.stdout


def test_mock_run_produces_snapshot_output() -> None:
    """mock 실행 출력에 snapshot 헤더가 포함되는지 확인한다."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--provider", "mock", "--exchange", "sor",
         "--codes", "005930,000660,035420",
         "--allow-fallback-sector-map",
         "--listen-seconds", "2", "--summary-interval-seconds", "1"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "snapshot" in result.stdout


# ---------------------------------------------------------------------------
# 20. min_total_trade_value가 높으면 warming/empty 힌트 출력
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 21. --sector-map-file 미지정 + --allow-fallback-sector-map 없음 → rc=2
# ---------------------------------------------------------------------------


def test_no_sector_map_file_exits_2_without_allow_fallback() -> None:
    """--sector-map-file 없이 --allow-fallback-sector-map 도 없으면 rc=2, ERROR 메시지."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--provider", "mock", "--exchange", "sor",
         "--codes", "005930,000660"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "ERROR" in result.stdout
    assert "sector-map-file" in result.stdout


def test_allow_fallback_flag_enables_run_without_sector_map_file() -> None:
    """--allow-fallback-sector-map 플래그가 있으면 --sector-map-file 없이도 실행된다."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--provider", "mock", "--exchange", "sor",
         "--codes", "005930,000660,035420",
         "--allow-fallback-sector-map",
         "--listen-seconds", "2", "--summary-interval-seconds", "1"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "WARNING" in result.stdout  # fallback 사용 경고 출력


def test_allow_fallback_flag_shows_warning_message() -> None:
    """--allow-fallback-sector-map 사용 시 WARNING 메시지가 출력된다."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH),
         "--dry-run", "--exchange", "sor",
         "--codes", "005930",
         "--allow-fallback-sector-map"],
        capture_output=True, text=True, timeout=15,
    )
    # dry-run 또는 allow-fallback 경로 모두 WARNING 포함
    assert "WARNING" in result.stdout or "NOTE" in result.stdout


# ---------------------------------------------------------------------------
# 22. load_sector_map_file wrapper: non-list value → warning 출력
# ---------------------------------------------------------------------------


def test_sector_map_file_warns_on_non_list_value(tmp_path: Path, capsys) -> None:
    """load_sector_map_file 에서 non-list value 는 경고를 출력하고 entry 를 건너뛴다."""
    data = {"000660": "반도체_잘못된형식", "005930": ["반도체"]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    sm = load_sector_map_file(f)
    assert "000660" not in sm       # non-list entry 제외
    assert sm["005930"] == ["반도체"]  # 유효 entry 보존
    captured = capsys.readouterr()
    assert "warn" in captured.out.lower()
    assert "000660" in captured.out


def test_sector_map_file_no_warnings_for_valid_file(tmp_path: Path, capsys) -> None:
    """모든 entry 가 유효하면 경고 없이 로드된다."""
    data = {"000660": ["반도체"], "042660": ["조선", "방산"]}
    f = tmp_path / "sm.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    sm = load_sector_map_file(f)
    assert sm["000660"] == ["반도체"]
    assert sm["042660"] == ["조선", "방산"]
    captured = capsys.readouterr()
    assert "warn" not in captured.out.lower()


# ---------------------------------------------------------------------------
# 23. min_total_trade_value 가 높으면 warming/empty 힌트 출력
# ---------------------------------------------------------------------------


def test_high_min_trade_value_shows_hint() -> None:
    """min_total_trade_value를 극도로 높게 설정하면 sector_views=0 + 힌트 출력."""
    sm = {"000660": ["반도체"]}
    svc = IntradaySnapshotService(sm, min_total_trade_value=999_999_999_999_999)
    svc.ingest_raw_message(
        make_mock_real_message("000660", "sor", 70000, 0.5, 1_000_000, "134501")
    )
    svc.ingest_raw_message(
        make_mock_real_message("000660", "sor", 70100, 0.6, 5_000_000, "134530")
    )
    snap = svc.get_snapshot()
    assert snap.sector_count == 0
    stats = {
        "total_messages": 2, "total_ingested_rows": 2, "total_snapshots": 1,
        "final_status": snap.status, "final_sector_count": 0,
        "elapsed_seconds": 5.0, "final_snapshot": snap,
    }
    out = format_final_summary(stats)
    assert "hint" in out.lower()
    assert "min_total_trade_value" in out
