"""Extract specialist referral recommendations from protocol text."""

from __future__ import annotations

import re
from typing import Any

# (token, display label, specialty regex) — more specific first
_SPECIALISTS: list[tuple[str, str, str]] = [
    (
        "рекомендация_гастроэнтеролога",
        "гастроэнтеролог",
        r"гастро[эе]нтеролог\w*|гастроэтеролог\w*",
    ),
    (
        "рекомендация_гинеколога",
        "гинеколог",
        r"гинеколог\w*",
    ),
    (
        "рекомендация_маммолога",
        "маммолог",
        r"мам+олог\w*",
    ),
    (
        "рекомендация_уролога",
        "уролог",
        r"уролог\w*",
    ),
    (
        "рекомендация_эндокринолога",
        "эндокринолог",
        r"эндокринолог\w*",
    ),
    (
        "рекомендация_сосудистого_хирурга",
        "сосудистый хирург / флеболог",
        r"сосудист\w*\s+хирург\w*|флеболог\w*",
    ),
    (
        "рекомендация_хирурга",
        "хирург",
        r"хирургическ\w*\s+профиль\w*|хирург\w*",
    ),
    (
        "рекомендация_невролога",
        "невролог",
        r"невролог\w*",
    ),
]

DISCLAIMER_REC = re.compile(
    r"(?i)рекомендуется\s+консультация\s+специалиста|не\s+являются?\s+(клиническим\s+)?диагнозом|"
    r"интерпретац\w+\s+результат\w+.*лечащ",
)
# backwards-compatible alias
_DISCLAIMER_REC = DISCLAIMER_REC

_REC_CONTEXT = re.compile(r"(?i)рекоменд\w*|консультац\w+|наблюден\w+")


def _specialty_hits(blob: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    vascular = bool(re.search(r"(?i)сосудист\w*\s+хирург|флеболог", blob))
    for token, label, pat in _SPECIALISTS:
        if token in seen:
            continue
        if not re.search(pat, blob, flags=re.I):
            continue
        if token == "рекомендация_хирурга" and vascular:
            # skip if only vascular surgeon / phlebologist matched «хирург»
            if not re.search(r"(?i)хирургическ\w*\s+профиль", blob):
                # strip vascular phrases and see if хирург remains
                stripped = re.sub(r"(?i)сосудист\w*\s+хирург\w*|флеболог\w*", " ", blob)
                if not re.search(r"(?i)хирург", stripped):
                    continue
        found.append((token, label))
        seen.add(token)
    return found


_CONSULT_SNIPPET = re.compile(
    r"(?i)(?:консультац\w*|наблюден\w*|конс\.?)\s+"
    r"(?:врача[-\s]?)?"
    r"(?:гастро[эе]нтеролог\w*|гастроэтеролог\w*|гинеколог\w*|мам+олог\w*|"
    r"уролог\w*|эндокринолог\w*|невролог\w*|флеболог\w*|"
    r"сосудист\w*\s+хирург\w*|хирург\w*)"
    r"(?:\s*\([^)]{0,40}\))?"
)


def _referral_snippets(blob: str) -> list[str]:
    """Keep only short «консультация X» phrases — not the whole diagnosis dump."""
    out: list[str] = []
    for m in _CONSULT_SNIPPET.finditer(blob or ""):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" .;,:")
        if s and s not in out:
            out.append(s[:120])
    if out:
        return out
    # Fallback: text after «Рекомендовано:/Рекомендации:» if short enough
    m = re.search(
        r"(?i)рекоменд(?:овано|ована|ации|ация)\s*[:\-—]\s*(.+)$",
        (blob or "").strip(),
    )
    if m:
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        if 0 < len(body) <= 160 and _specialty_hits(body):
            return [body]
    return []


def extract_recommendation(text: str) -> dict[str, Any]:
    """Detect named specialist referrals; ignore bare «консультация специалиста»."""
    snippets: list[str] = []
    specialists: list[str] = []
    tokens: dict[str, int] = {}
    seen_labels: set[str] = set()

    candidates: list[str] = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for m in re.finditer(r"(?i)рекоменд\w*[^\n.]{0,220}", text or ""):
        candidates.append(m.group(0).strip())

    for raw in candidates:
        is_disclaimer = bool(DISCLAIMER_REC.search(raw))
        hits = _specialty_hits(raw)
        if is_disclaimer and not hits:
            continue
        if not _REC_CONTEXT.search(raw):
            continue
        if not hits:
            continue
        for snip in _referral_snippets(raw):
            if len(snippets) >= 6:
                break
            # skip near-duplicates («Консультация эндокринолога» vs «… (ФИО)»)
            key = re.sub(r"\s*\([^)]*\)\s*", "", snip).lower()
            if any(key == re.sub(r"\s*\([^)]*\)\s*", "", s).lower() for s in snippets):
                # prefer the longer variant (with name)
                for i, s in enumerate(snippets):
                    if key == re.sub(r"\s*\([^)]*\)\s*", "", s).lower() and len(snip) > len(s):
                        snippets[i] = snip
                continue
            if snip not in snippets:
                snippets.append(snip)
        for token, label in hits:
            tokens[token] = 1
            if label not in seen_labels:
                specialists.append(label)
                seen_labels.add(label)

    return {
        "present": bool(tokens),
        "text": "; ".join(snippets[:4]) if snippets else None,
        "specialists": specialists,
        "tokens": tokens,
    }


def recommendation_token_names() -> frozenset[str]:
    return frozenset(t for t, _, _ in _SPECIALISTS)


def specialist_label(token: str) -> str | None:
    for t, lab, _ in _SPECIALISTS:
        if t == token:
            return lab
    return None


def labels_for_tokens(token_names: list[str] | set[str]) -> list[str]:
    out: list[str] = []
    for t, lab, _ in _SPECIALISTS:
        if t in token_names and lab not in out:
            out.append(lab)
    return out
