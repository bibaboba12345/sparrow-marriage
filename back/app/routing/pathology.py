"""Simple pathology highlighter: evaluate rules against nonzero protocol tokens."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_SEVERITY_RANK = {"pathology": 3, "suspicious": 2, "normal": 1}

_THRESHOLD_RE = re.compile(
    r"^(?P<key>[A-Za-zА-Яа-яЁё0-9_]+)\s*(?P<op>>=|<=|>|<|==|=)\s*(?P<val>-?\d+(?:[.,]\d+)?)$"
)


def _rules_path() -> Path:
    return Path(__file__).resolve().parent / "pathology_rules.json"


@lru_cache(maxsize=1)
def load_pathology_rules() -> list[dict[str, Any]]:
    path = _rules_path()
    mtime = path.stat().st_mtime
    return _load_rules_at(str(path), mtime)


@lru_cache(maxsize=2)
def _load_rules_at(path_str: str, _mtime: float) -> list[dict[str, Any]]:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        return []
    out = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        expr = r.get("expr") or []
        if not isinstance(expr, list) or not expr:
            continue
        sev = str(r.get("severity") or "suspicious")
        out.append(
            {
                "id": str(r.get("id") or expr[0]),
                "severity": sev,
                "expr": [str(x) for x in expr],
                "label": str(r.get("label") or r.get("id") or expr[0]),
            }
        )
    return out


def _is_nonzero(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0 and not (isinstance(value, float) and value != value)
    if isinstance(value, str):
        t = value.strip()
        if not t or t in {"0", "false", "null", "None"}:
            return False
        return True
    return True


def _expr_keys(term: str) -> list[str]:
    m = _THRESHOLD_RE.match(term.strip())
    if m:
        return [m.group("key")]
    return [term.strip()]


def _get_num(bag: dict[str, Any], key: str) -> float | None:
    if key not in bag or bag[key] is None:
        return None
    v = bag[key]
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip().replace(",", ".")
        s = re.sub(r"[^\d.\-]+", "", s)
        if not s:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _term_true(term: str, bag: dict[str, Any]) -> bool:
    t = term.strip()
    m = _THRESHOLD_RE.match(t)
    if m:
        key = m.group("key")
        op = m.group("op")
        if op == "=":
            op = "=="
        thr = float(m.group("val").replace(",", "."))
        num = _get_num(bag, key)
        if num is None:
            return False
        if op == ">=":
            return num >= thr
        if op == "<=":
            return num <= thr
        if op == ">":
            return num > thr
        if op == "<":
            return num < thr
        if op == "==":
            return num == thr
        return False
    return key_in_nonzero(t, bag)


def key_in_nonzero(key: str, bag: dict[str, Any]) -> bool:
    return key in bag and _is_nonzero(bag[key])


@lru_cache(maxsize=1)
def normal_only_token_keys() -> frozenset[str]:
    """Tokens that appear only in severity=normal rules (anatomical variants, «норма»)."""
    path = _rules_path()
    mtime = path.stat().st_mtime
    return _normal_only_token_keys_at(str(path), mtime)


@lru_cache(maxsize=2)
def _normal_only_token_keys_at(path_str: str, _mtime: float) -> frozenset[str]:
    normal: set[str] = set()
    abnormal: set[str] = set()
    for rule in _load_rules_at(path_str, _mtime):
        bucket = normal if rule["severity"] == "normal" else abnormal
        for term in rule["expr"]:
            for k in _expr_keys(term):
                if k in {"age_years", "height_cm", "weight_kg"}:
                    continue
                bucket.add(k)
    return frozenset(normal - abnormal)


def is_normal_token(token_name: str) -> bool:
    return token_name in normal_only_token_keys()


def evaluate_pathology(
    clinical_tokens: dict[str, Any] | None,
    patient: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Walk rules that share ≥1 nonzero key with P; fire when full AND holds.
    Returns matched rules + by_token severity map (pathology > suspicious).
    """
    P: dict[str, Any] = {}
    if isinstance(clinical_tokens, dict):
        for k, v in clinical_tokens.items():
            if _is_nonzero(v):
                P[k] = v
    if isinstance(patient, dict):
        for k in ("age_years", "height_cm", "weight_kg"):
            if k in patient and patient[k] is not None:
                P[k] = patient[k]

    nonzero_keys = set(P.keys())
    rules = load_pathology_rules()
    matched: list[dict[str, Any]] = []
    by_token: dict[str, str] = {}
    candidates = 0

    for rule in rules:
        sev = rule["severity"]
        if sev == "normal":
            continue
        expr = rule["expr"]
        keys_in_rule: set[str] = set()
        for term in expr:
            keys_in_rule.update(_expr_keys(term))
        if not keys_in_rule & nonzero_keys:
            continue
        candidates += 1
        if not all(_term_true(term, P) for term in expr):
            continue
        matched.append(
            {
                "id": rule["id"],
                "severity": sev,
                "expr": expr,
                "label": rule["label"],
            }
        )
        for term in expr:
            for k in _expr_keys(term):
                if k not in nonzero_keys and k not in ("age_years",):
                    # only color tokens present in clinical P
                    if k not in P:
                        continue
                if k in ("age_years", "height_cm", "weight_kg"):
                    continue
                if k not in P:
                    continue
                prev = by_token.get(k)
                if prev is None or _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(prev, 0):
                    by_token[k] = sev

    matched.sort(key=lambda r: (-_SEVERITY_RANK.get(r["severity"], 0), r["id"]))
    return {
        "matched": matched,
        "by_token": by_token,
        "candidates_checked": candidates,
    }
