"""Map structured important-tokens + free-text complaints → binary deviation vector."""

from __future__ import annotations

import re
from typing import Any

from . import features as feat

# Split free-text complaints into short phrases for token list / matching.
_SPLIT_RE = re.compile(
    r"[,;/\n|]+|"
    r"\s+[—–-]\s+|"
    r"(?<=[.!?])\s+|"
    r"\bжалоб[аыуе]?\b\s*[:\-–]?\s*|"
    r"\bпредъявляет\b\s*|"
    r"\bбеспокоит(?:ся)?\b\s*|"
    r"\bотмечает\b\s*",
    re.IGNORECASE,
)

# Short aliases need word-ish boundaries to avoid false hits ("окс" in longer words).
_SHORT_ALIAS_MAX = 4


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def _parse_number(raw: str) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", ".")
    text = text.replace(">", "").replace("<", "").replace("≈", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_ref_range(ref: str | None) -> tuple[float | None, float | None]:
    if not ref:
        return None, None
    text = str(ref).replace(",", ".").replace("—", "-").replace("–", "-")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"[<>]=?\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        v = float(m.group(1))
        if "<" in text:
            return None, v
        if ">" in text:
            return v, None
    return None, None


def _alias_hits(blob: str) -> list[tuple[str, str]]:
    """Return (needle, feature_id) matches; longest needles first."""
    n = _norm(blob)
    if not n:
        return []
    items = sorted(feat.aliases().items(), key=lambda kv: len(kv[0]), reverse=True)
    hits: list[tuple[str, str]] = []
    claimed: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in claimed)

    for needle, fid in items:
        nn = _norm(needle)
        if not nn:
            continue
        start = 0
        while True:
            pos = n.find(nn, start)
            if pos < 0:
                break
            end = pos + len(nn)
            # word-ish boundary for short / latin codes
            if len(nn) <= _SHORT_ALIAS_MAX or re.fullmatch(r"[a-z0-9+\-]+", nn):
                left_ok = pos == 0 or not n[pos - 1].isalnum()
                right_ok = end >= len(n) or not n[end].isalnum()
                if not (left_ok and right_ok):
                    start = pos + 1
                    continue
            if not overlaps(pos, end):
                hits.append((needle, fid))
                claimed.append((pos, end))
                break
            start = pos + 1
    return hits


def _activate_aliases(blob: str, active: set[str], matched: list[dict[str, str]] | None = None) -> None:
    for needle, fid in _alias_hits(blob):
        active.add(fid)
        if matched is not None:
            matched.append({"token": needle, "feature": fid})


def split_complaint_tokens(text: str) -> list[str]:
    """Split free-text complaints into short phrases."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = _SPLIT_RE.split(raw)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        t = re.sub(r"\s+", " ", (p or "").strip(" .·•"))
        if len(t) < 2:
            continue
        key = _norm(t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def extract_vitals_from_text(text: str) -> dict[str, str]:
    """Pull vital signs mentioned in free text."""
    n = _norm(text)
    vitals: dict[str, str] = {}

    m = re.search(
        r"(?:температур[аыуе]?\s*(?:тела)?|t\s*[°º]?\s*[cс]?|лихорадк[ауие]?)\s*[:=]?\s*(\d+[.,]\d+|\d{2}(?:[.,]\d+)?)",
        n,
    )
    if m:
        vitals["temp"] = m.group(1).replace(",", ".")

    m = re.search(r"(?:spo2|сат(?:ураци[яи])?|сатурация)\s*[:=]?\s*(\d{2,3})\s*%?", n)
    if m:
        vitals["spo2"] = m.group(1)

    m = re.search(r"(?:чсс|пульс|heart\s*rate|hr)\s*[:=]?\s*(\d{2,3})", n)
    if m:
        vitals["hr"] = m.group(1)

    m = re.search(r"(?:чдд|чд|частота\s*дыхани)\s*[:=]?\s*(\d{1,2})", n)
    if m:
        vitals["rr"] = m.group(1)

    m = re.search(
        r"(?:ад|а/?д|давлени[ея]|blood\s*pressure|bp)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})",
        n,
    )
    if m:
        vitals["bp"] = f"{m.group(1)}/{m.group(2)}"

    return vitals


def extract_labs_from_text(text: str) -> list[dict[str, str]]:
    """Heuristic lab mentions with numeric values in free text."""
    n = _norm(text)
    labs: list[dict[str, str]] = []
    patterns = [
        (r"(тропон(?:ин)?(?:\s*[iіtнт]+)?)\s*[:=]?\s*([\d.,]+)", "тропонин"),
        (r"(глюкоз[аыуе]?|glucose)\s*[:=]?\s*([\d.,]+)", "глюкоза"),
        (r"(hba1c|гликированн\w*)\s*[:=]?\s*([\d.,]+)", "hba1c"),
        (r"(срб|c-реактив\w*|crp)\s*[:=]?\s*([\d.,]+)", "срб"),
        (r"(д-?\s*димер|d-?dimer)\s*[:=]?\s*([\d.,]+)", "д-димер"),
        (r"(креатинин)\s*[:=]?\s*([\d.,]+)", "креатинин"),
        (r"(лейкоцит\w*|wbc)\s*[:=]?\s*([\d.,]+)", "лейкоциты"),
        (r"(гемоглобин|hgb|hb)\s*[:=]?\s*([\d.,]+)", "гемоглобин"),
        (r"(прокальцитонин|pct)\s*[:=]?\s*([\d.,]+)", "прокальцитонин"),
    ]
    for pat, name in patterns:
        m = re.search(pat, n)
        if m:
            labs.append({"name": name, "value": m.group(2).replace(",", "."), "ref_range": None})
    return labs


def _match_lab(name: str, value: str, ref_range: str | None, active: set[str]) -> None:
    n = _norm(name)
    num = _parse_number(value)
    if num is None:
        if any(k in n for k in ("белок", "protein")) and _norm(value) not in {
            "",
            "отриц",
            "отр",
            "neg",
            "negative",
            "-",
            "не обнар",
        }:
            if not re.search(r"отриц|отр|neg|не обнар|^-$", _norm(value)):
                active.add("lab_urine_protein")
        return

    lo, hi = _parse_ref_range(ref_range)
    for rule in feat.lab_rules():
        if not any(alias in n for alias in rule["names"]):
            continue
        direction = rule["direction"]
        thr = float(rule["threshold"])
        if lo is not None and hi is not None:
            if direction == "high" and num > hi:
                active.add(rule["feature"])
            elif direction == "low" and num < lo:
                active.add(rule["feature"])
        else:
            if direction == "high" and num > thr:
                active.add(rule["feature"])
            elif direction == "low" and num < thr:
                active.add(rule["feature"])


def _match_vitals(vitals: dict[str, Any], active: set[str]) -> None:
    for key, raw in (vitals or {}).items():
        kn = _norm(str(key))
        if kn in {"bp", "ад", "давление"} or "blood" in kn:
            text = str(raw)
            m = re.search(r"(\d+)\s*/\s*(\d+)", text)
            if m:
                sys_v, dia_v = int(m.group(1)), int(m.group(2))
                if sys_v >= 140 or dia_v >= 90:
                    active.add("vital_bp_high")
                if sys_v < 90 or dia_v < 60:
                    active.add("vital_bp_low")
            continue
        num = _parse_number(str(raw))
        if num is None:
            continue
        for rule in feat.vital_rules():
            if not any(k in kn for k in rule["keys"]):
                continue
            thr = float(rule["threshold"])
            if rule["direction"] == "high" and num >= thr:
                active.add(rule["feature"])
            elif rule["direction"] == "low" and num <= thr:
                active.add(rule["feature"])


def aggregate_important(
    documents: list[dict[str, Any]] | list[Any],
    *,
    extra_text: str = "",
) -> dict[str, Any]:
    """Merge important blocks + full free-text from route documents."""
    symptoms: list[str] = []
    diagnoses: list[str] = []
    labs: list[dict[str, Any]] = []
    medications: list[str] = []
    vitals: dict[str, str] = {}
    red_flags: list[str] = []
    snippets: list[str] = []
    free_texts: list[str] = []

    for doc in documents or []:
        if hasattr(doc, "model_dump"):
            d = doc.model_dump()
        else:
            d = doc if isinstance(doc, dict) else {}
        imp = d.get("important") or {}
        if hasattr(imp, "model_dump"):
            imp = imp.model_dump()
        symptoms.extend(imp.get("symptoms") or [])
        diagnoses.extend(imp.get("diagnoses") or [])
        medications.extend(imp.get("medications") or [])
        red_flags.extend(imp.get("red_flags") or [])
        snippets.extend(imp.get("clinical_snippets") or [])
        for lab in imp.get("labs") or []:
            if hasattr(lab, "model_dump"):
                lab = lab.model_dump()
            labs.append(lab)
        for k, v in (imp.get("vitals") or {}).items():
            vitals[str(k)] = str(v)
        raw = (d.get("raw_text") or "").strip()
        if raw:
            free_texts.append(raw)
        if d.get("summary"):
            snippets.append(d["summary"])

    if extra_text and str(extra_text).strip():
        free_texts.append(str(extra_text).strip())

    return {
        "symptoms": symptoms,
        "diagnoses": diagnoses,
        "labs": labs,
        "medications": medications,
        "vitals": vitals,
        "red_flags": red_flags,
        "clinical_snippets": snippets,
        "free_text": free_texts,
    }


def vectorize_important(
    important: dict[str, Any],
    *,
    alias_free_text: bool = True,
    seed_active: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    Map important + optional free text → binary vector.

    alias_free_text=False: не гонять raw free_text через алиасы
    (когда LLM уже отфильтровал отклонения в symptoms/red_flags/seed_active).
    Labs/vitals numeric thresholds всё равно считаются.
    """
    active: set[str] = set(seed_active or [])
    matched_phrases: list[dict[str, str]] = []
    text_tokens: list[str] = []

    structured_chunks: list[str] = []
    free_chunks: list[str] = []

    for key in ("symptoms", "diagnoses", "red_flags", "medications", "clinical_snippets"):
        for item in important.get(key) or []:
            structured_chunks.append(str(item))
            text_tokens.extend(split_complaint_tokens(str(item)))

    for ft in important.get("free_text") or []:
        free_chunks.append(str(ft))
        text_tokens.extend(split_complaint_tokens(str(ft)))

    if important.get("text"):
        free_chunks.append(str(important["text"]))
        text_tokens.extend(split_complaint_tokens(str(important["text"])))

    # de-dupe tokens preserving order
    seen_tok: set[str] = set()
    uniq_tokens: list[str] = []
    for t in text_tokens:
        k = _norm(t)
        if k in seen_tok:
            continue
        seen_tok.add(k)
        uniq_tokens.append(t)
    text_tokens = uniq_tokens

    vitals = dict(important.get("vitals") or {})
    labs = list(important.get("labs") or [])

    # Parse vitals/labs from free text (numeric thresholds — не «в норме»).
    for chunk in free_chunks + structured_chunks:
        for k, v in extract_vitals_from_text(chunk).items():
            vitals.setdefault(k, v)
        labs.extend(extract_labs_from_text(chunk))

    for k, v in vitals.items():
        structured_chunks.append(f"{k} {v}")

    # Alias structured complaints always; free text only if requested.
    for token in (
        split_complaint_tokens(" | ".join(structured_chunks))
        if structured_chunks
        else []
    ):
        _activate_aliases(token, active, matched_phrases)
    for item in structured_chunks:
        _activate_aliases(str(item), active, matched_phrases)

    if alias_free_text:
        for token in text_tokens:
            _activate_aliases(token, active, matched_phrases)
        if free_chunks:
            _activate_aliases(" | ".join(free_chunks), active, matched_phrases)

    # If we have a numeric temp, drop fever-from-alias-only when not actually high
    temp_num = _parse_number(vitals.get("temp") or "")
    if temp_num is not None and temp_num < 37.2:
        active.discard("symptom_fever")
        active.discard("vital_temp_high")

    for lab in labs:
        if hasattr(lab, "model_dump"):
            lab = lab.model_dump()
        name = str(lab.get("name") or "")
        value = str(lab.get("value") or "")
        ref = lab.get("ref_range")
        _match_lab(name, value, ref, active)
        _activate_aliases(f"{name} {value}", active, matched_phrases)

    _match_vitals(vitals, active)

    for lab in labs:
        if hasattr(lab, "model_dump"):
            lab = lab.model_dump()
        n = _norm(str(lab.get("name") or ""))
        v = _norm(str(lab.get("value") or ""))
        if "лейкоцит" in n and "моч" in n and v not in {"отриц", "отр", "neg", "-", "0"}:
            active.add("lab_urine_leukocytes")
        if ("эритроцит" in n or "кровь" in n) and "моч" in n and v not in {
            "отриц",
            "отр",
            "neg",
            "-",
            "0",
        }:
            active.add("lab_urine_blood")
        if "глюкоз" in n and "моч" in n and v not in {"отриц", "отр", "neg", "-", "0"}:
            active.add("lab_urine_glucose")

    # Dedupe matched_phrases
    seen_m: set[tuple[str, str]] = set()
    uniq_matched: list[dict[str, str]] = []
    for m in matched_phrases:
        key = (m["token"], m["feature"])
        if key in seen_m:
            continue
        seen_m.add(key)
        uniq_matched.append(m)

    vec = feat.vector_from_active(active)
    return {
        "vector": vec,
        "active_features": sorted(active),
        "text_tokens": text_tokens,
        "matched_phrases": uniq_matched,
        "parsed_vitals": vitals,
        "features_version": feat.catalog_version(),
        "dim": feat.feature_dim(),
    }


def vectorize_documents(
    documents: list[Any],
    *,
    extra_text: str = "",
    alias_free_text: bool = True,
    seed_active: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    return vectorize_important(
        aggregate_important(documents, extra_text=extra_text),
        alias_free_text=alias_free_text,
        seed_active=seed_active,
    )


def vectorize_text(text: str) -> dict[str, Any]:
    """Convenience: plain complaint / epicrisis text → vector."""
    return vectorize_important({"text": text, "free_text": [text]})
