"""Casebook loader — vectors built from active_features on load."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import features as feat

_CASES = Path(__file__).resolve().parent / "cases.json"


@lru_cache(maxsize=1)
def load_cases() -> list[dict[str, Any]]:
    if not _CASES.exists():
        return []
    with _CASES.open(encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("cases") if isinstance(data, dict) else data
    out: list[dict[str, Any]] = []
    for row in rows or []:
        case = dict(row)
        active = list(case.get("active_features") or [])
        case["active_features"] = active
        case["vector"] = feat.vector_from_active(active)
        out.append(case)
    return out


def reload_cases() -> list[dict[str, Any]]:
    load_cases.cache_clear()
    return load_cases()
