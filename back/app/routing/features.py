"""Feature catalog loader for binary routing vectors."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent / "features.json"


@lru_cache(maxsize=4)
def _raw_cached(mtime_ns: int) -> dict[str, Any]:
    with _DATA.open(encoding="utf-8") as f:
        return json.load(f)


def _raw() -> dict[str, Any]:
    return _raw_cached(_DATA.stat().st_mtime_ns)


def catalog_version() -> str:
    return str((_raw().get("meta") or {}).get("version") or "0")


def feature_ids() -> list[str]:
    return [f["id"] for f in _raw()["features"]]


def feature_index() -> dict[str, int]:
    return {fid: i for i, fid in enumerate(feature_ids())}


def feature_dim() -> int:
    return len(feature_ids())


def feature_meta() -> list[dict[str, Any]]:
    return list(_raw()["features"])


def aliases() -> dict[str, str]:
    return dict(_raw().get("aliases") or {})


def lab_rules() -> list[dict[str, Any]]:
    return list(_raw().get("lab_rules") or [])


def vital_rules() -> list[dict[str, Any]]:
    return list(_raw().get("vital_rules") or [])


def empty_vector() -> list[int]:
    return [0] * feature_dim()


def vector_from_active(active: list[str] | set[str]) -> list[int]:
    idx = feature_index()
    vec = empty_vector()
    for fid in active:
        i = idx.get(fid)
        if i is not None:
            vec[i] = 1
    return vec


def active_from_vector(vec: list[int]) -> list[str]:
    ids = feature_ids()
    return [ids[i] for i, bit in enumerate(vec) if bit]
