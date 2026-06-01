"""sector_map JSON 파일 로더.

운영용 sector_map.json 을 읽어 intraday 파이프라인에 공급한다.

형식::

    {
        "005930": ["반도체", "대형주"],
        "000660": ["반도체"],
        "042660": ["조선"]
    }

코드 key 는 6자리 zero-padded 문자열로 normalize 된다.
value 가 list 가 아닌 entry 는 strict=False 면 warnings 에 누적하고 건너뛴다.
strict=True 면 SectorMapLoadError 를 raise 한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class SectorMapLoadError(ValueError):
    """sector_map 로드 실패 (JSON 파싱 실패, 형식 오류, invalid entry).

    FileNotFoundError 는 이 클래스가 아닌 표준 FileNotFoundError 로 전파된다.
    """


@dataclass
class SectorMapLoadResult:
    """sector_map 로드 결과."""

    sector_map: dict[str, list[str]]
    """코드(6자리) → 섹터명 리스트."""

    warnings: list[str] = field(default_factory=list)
    """non-critical 경고 목록. strict=False 시 invalid entry 정보가 담긴다."""


def load_sector_map(
    path: "Path | str",
    *,
    strict: bool = False,
) -> SectorMapLoadResult:
    """sector_map JSON 파일을 읽어 SectorMapLoadResult 를 반환한다.

    Args:
        path:   sector_map.json 경로.
        strict: True 이면 invalid entry 에서 SectorMapLoadError 를 raise 한다.
                False 이면 warnings 에 누적하고 해당 entry 는 건너뛴다.

    Raises:
        FileNotFoundError:  파일이 없을 때.
        SectorMapLoadError: JSON 파싱 실패, 최상위 타입 오류,
                            strict=True 이고 invalid entry 가 있을 때.
    """
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise  # 표준 FileNotFoundError 그대로 전파

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SectorMapLoadError(
            f"sector_map 파일이 유효한 JSON 이 아닙니다: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise SectorMapLoadError(
            f"sector_map 파일은 JSON object 형식이어야 합니다 (실제: {type(data).__name__})"
        )

    result: dict[str, list[str]] = {}
    warnings: list[str] = []

    for raw_code, value in data.items():
        code = str(raw_code).strip().zfill(6)

        if not isinstance(value, list):
            msg = (
                f"[sector_map] {raw_code!r}: value 가 list 가 아닙니다 "
                f"(실제: {type(value).__name__}, 무시됨)"
            )
            if strict:
                raise SectorMapLoadError(msg)
            warnings.append(msg)
            continue

        sectors: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                sectors.append(item.strip())
            else:
                msg = (
                    f"[sector_map] {raw_code!r}: non-string 또는 빈 sector 항목 무시됨: {item!r}"
                )
                if strict:
                    raise SectorMapLoadError(msg)
                warnings.append(msg)

        result[code] = sectors

    return SectorMapLoadResult(sector_map=result, warnings=warnings)
