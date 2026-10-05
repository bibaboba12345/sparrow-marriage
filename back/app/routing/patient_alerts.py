"""Patient emergency alerts from RADS / TIRADS scores."""

from __future__ import annotations

import re
from typing import Any

# (token_prefix_or_exact, study label, default specialist nominative)
_RADS_FAMILIES: list[tuple[str, str, str]] = [
    ("BI_RADS", "УЗИ молочных желез", "маммолог"),
    ("O_RADS", "УЗИ органов малого таза", "гинеколог"),
    ("EU_TIRADS", "УЗИ щитовидной железы", "эндокринолог"),
    ("TI_RADS", "УЗИ щитовидной железы", "эндокринолог"),
]

_STUDY_TOKEN_LABELS: dict[str, str] = {
    "study_us_breast": "УЗИ молочных желез",
    "study_us_pelvis": "УЗИ органов малого таза",
    "study_us_thyroid": "УЗИ щитовидной железы",
    "study_us_abdomen": "УЗИ органов брюшной полости",
}

_DATIVE: dict[str, str] = {
    "гинеколог": "гинекологу",
    "маммолог": "маммологу",
    "эндокринолог": "эндокринологу",
    "уролог": "урологу",
    "гастроэнтеролог": "гастроэнтерологу",
    "невролог": "неврологу",
    "хирург": "хирургу",
    "сосудистый хирург / флеболог": "сосудистому хирургу / флебологу",
}

_FIO_LINE = re.compile(
    r"(?im)^(?:ФИО\s*пациента|Пациент|Ф\.?\s*И\.?\s*О\.?)\s*[:\t][ \t]*(\S[^\n\r]*)$"
)
_FIO_INLINE = re.compile(
    r"(?i)(?:ФИО\s*пациента|Пациент)\s*[:\t][ \t]*"
    r"([А-ЯЁа-яёA-Za-z\-]+(?:[ \t]+[А-ЯЁа-яёA-Za-z\-]+){1,3})"
)


def _as_num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != value:
            return None
        return float(value)
    if isinstance(value, str):
        t = value.strip().replace(",", ".")
        if not t:
            return None
        m = re.match(r"^(\d+(?:\.\d+)?)", t)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _family_for_key(key: str) -> tuple[str, str, str] | None:
    k = key.upper()
    for prefix, study, specialist in _RADS_FAMILIES:
        if k == prefix or k.startswith(prefix + "_"):
            return prefix, study, specialist
    return None


def collect_rads_scores(clinical: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return scored RADS tokens: [{key, score, family, study, specialist}]."""
    out: list[dict[str, Any]] = []
    for key, raw in (clinical or {}).items():
        fam = _family_for_key(str(key))
        if not fam:
            continue
        score = _as_num(raw)
        if score is None:
            continue
        prefix, study, specialist = fam
        out.append(
            {
                "key": key,
                "score": score,
                "family": prefix,
                "study": study,
                "specialist": specialist,
            }
        )
    out.sort(key=lambda x: (-x["score"], x["key"]))
    return out


def extract_name_patronymic(text: str | None) -> str | None:
    """From «Фамилия Имя Отчество» keep «Имя Отчество»."""
    blob = text or ""
    raw: str | None = None
    m = _FIO_LINE.search(blob)
    if m:
        cand = m.group(1).strip()
        if cand and not re.fullmatch(r"[\.\-—_\s]+", cand):
            raw = cand.split("\t")[0].strip()
    if not raw:
        m2 = _FIO_INLINE.search(blob)
        if m2:
            raw = m2.group(1).strip()
    if not raw:
        return None
    # drop card crumbs / trailing labels
    raw = re.split(r"\s{2,}|,", raw)[0].strip()
    parts = [p for p in re.split(r"\s+", raw) if p]
    if len(parts) >= 3:
        return f"{parts[1]} {parts[2]}"
    if len(parts) == 2:
        # already «Имя Отчество» or «Фамилия Имя»
        return f"{parts[0]} {parts[1]}"
    if len(parts) == 1 and len(parts[0]) >= 2:
        return parts[0]
    return None


def specialist_dative(nominative: str) -> str:
    if nominative in _DATIVE:
        return _DATIVE[nominative]
    # crude fallback: -ог → -огу, -ог → else +у
    if nominative.endswith("ог"):
        return nominative + "у"
    if nominative.endswith("а"):
        return nominative[:-1] + "е"
    return nominative + "у"


def _pick_specialist(
    family_default: str,
    recommendation: dict[str, Any] | None,
) -> str:
    specs = list((recommendation or {}).get("specialists") or [])
    if family_default in specs:
        return family_default
    # soft match by stem
    stem = family_default.split()[0][:6].lower()
    for s in specs:
        if stem in s.lower():
            return s
    if specs:
        return specs[0]
    return family_default


def _study_label(
    hit: dict[str, Any],
    clinical: dict[str, Any] | None,
) -> str:
    for tok, label in _STUDY_TOKEN_LABELS.items():
        if clinical and clinical.get(tok):
            # prefer study token only if it matches the RADS family organ system
            if hit["study"] == label:
                return label
    return hit["study"]


def _greeting(sex: str | None, name_patronymic: str | None) -> str:
    female = (sex or "").strip().upper() in {"F", "Ж", "FEMALE", "ЖЕН", "ЖЕНСКИЙ"}
    honorific = "Уважаемая" if female else "Уважаемый"
    if name_patronymic:
        return f"{honorific} {name_patronymic}"
    return f"{honorific} {'пациентка' if female else 'пациент'}"


def build_patient_alert(
    clinical: dict[str, Any] | None,
    *,
    text: str | None = None,
    recommendation: dict[str, Any] | None = None,
    patient: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    RADS == 3 → month follow-up alert.
    RADS >= 4 → urgent specialist alert.
    Uses max score across BI/O/TI/EU-RADS tokens.
    """
    scores = collect_rads_scores(clinical)
    if not scores:
        return None
    top = scores[0]
    score = top["score"]
    if score < 3:
        return None

    # among keys with the same max score, keep all
    max_score = score
    top_hits = [s for s in scores if s["score"] == max_score]
    hit = top_hits[0]

    study = _study_label(hit, clinical)
    specialist = _pick_specialist(hit["specialist"], recommendation)
    name = extract_name_patronymic(text)
    sex = None
    if patient:
        sex = patient.get("sex")
    greet = _greeting(sex if isinstance(sex, str) else None, name)
    spec_dat = specialist_dative(specialist)

    if max_score >= 4:
        level = "urgent"
        body = (
            f"{greet}, по результатам {study} Вам необходимо срочно "
            f"обратиться к {spec_dat}."
        )
    else:
        # exactly 3 (or 3.x < 4)
        level = "month"
        body = (
            f"{greet}, по результатам {study} Вам рекомендовано "
            f"обратиться к {spec_dat} в течение месяца."
        )

    return {
        "present": True,
        "level": level,  # month | urgent
        "label": "экстренный алерт" if level == "month" else "срочный алерт",
        "rads_score": int(max_score) if float(max_score).is_integer() else max_score,
        "rads_keys": [h["key"] for h in top_hits],
        "study": study,
        "specialist": specialist,
        "patient_address": name,
        "text": body,
    }
