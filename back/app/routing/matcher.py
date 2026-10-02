"""Nearest-case matcher: max dot product, tie-break min sum(c)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import features as feat
from .cases import load_cases


@dataclass
class MatchResult:
    case: dict[str, Any]
    score: int
    case_weight: int
    query_active: list[str]
    case_active: list[str]
    features_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_case_id": self.case.get("id"),
            "matched_case_title": self.case.get("title"),
            "match_score": self.score,
            "case_weight": self.case_weight,
            "query_active": self.query_active,
            "vector_active": self.query_active,
            "case_active": self.case_active,
            "features_version": self.features_version,
            "epicrisis_snippet": self.case.get("epicrisis_snippet") or "",
        }


_FALLBACK_CASE = {
    "id": "case-fallback-routine",
    "title": "Плановый / неспецифический",
    "active_features": [],
    "routing": {
        "priority": "routine",
        "department": "Терапия",
        "specialists": ["Терапевт"],
        "required_tests": ["ОАК", "Биохимия"],
        "reasoning": [
            "Совпадений с кейсбуком нет (score=0)",
            "Фоллбэк: плановый терапевтический маршрут",
        ],
    },
    "epicrisis_snippet": "Неспецифические жалобы без острых маркеров.",
}


def _dot(a: list[int], b: list[int]) -> int:
    return sum(x * y for x, y in zip(a, b, strict=False))


def match_vector(query_vec: list[int], query_active: list[str] | None = None) -> MatchResult:
    cases = load_cases()
    q_active = query_active if query_active is not None else feat.active_from_vector(query_vec)
    best: dict[str, Any] | None = None
    best_score = -1
    best_weight = 10**9

    for case in cases:
        cvec = case.get("vector") or feat.vector_from_active(case.get("active_features") or [])
        score = _dot(query_vec, cvec)
        weight = sum(cvec)
        if score > best_score or (score == best_score and weight < best_weight):
            best = case
            best_score = score
            best_weight = weight

    if best is None or best_score <= 0:
        return MatchResult(
            case=_FALLBACK_CASE,
            score=0,
            case_weight=0,
            query_active=q_active,
            case_active=[],
            features_version=feat.catalog_version(),
        )

    return MatchResult(
        case=best,
        score=best_score,
        case_weight=best_weight,
        query_active=q_active,
        case_active=list(best.get("active_features") or []),
        features_version=feat.catalog_version(),
    )
