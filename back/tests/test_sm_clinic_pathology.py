"""Interactive pathology tests against СМ-Клиника gold labels.

Run (stop on first failure, live prints):
  cd back && source .venv/bin/activate
  pytest tests/test_sm_clinic_pathology.py -x -s

Rerun one protocol:
  pytest tests/test_sm_clinic_pathology.py -x -s -k OMT_8
  # ids: OMT_*, GP_*, BR_*, THY_*, PRO_*, VEIN_*
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from app.routing.pathology import is_normal_token
from app.routing.protocol_tokenizer import enrich_tokenize_result, tokenize_protocol_text
from pathology_match import cover_expected, humanize_token

_SKIP_CLINICAL_PREFIXES = (
    "study_",
    "рекомендация_",
)
_SKIP_CLINICAL_EXACT = {
    "age_years",
    "height_cm",
    "weight_kg",
    "sex",
}
_MEASURE_ONLY = re.compile(
    r".*_(длина|толщина|ширина|объем|объём|диаметр|размеры)(_|$)|.*_(мм|см|см3|мл)$",
    re.IGNORECASE,
)

_PROTOCOLS_ROOT = (
    Path(__file__).resolve().parents[2] / "СМ-Клиника-протоколы" / "протоколы"
)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _discover_cases() -> list[tuple[str, Path, Path]]:
    cases: list[tuple[str, Path, Path]] = []
    if not _PROTOCOLS_ROOT.is_dir():
        return cases
    for folder in sorted(_PROTOCOLS_ROOT.iterdir(), key=lambda p: _nfc(p.name)):
        if not folder.is_dir():
            continue
        seen: set[str] = set()
        for txt in sorted(folder.glob("*.txt"), key=lambda p: _nfc(p.name)):
            name = _nfc(txt.name)
            if name.endswith("_expected_output.txt"):
                continue
            if name in seen:
                continue
            seen.add(name)
            expected = txt.with_name(txt.stem + "_expected_output.txt")
            if not expected.is_file():
                continue
            # stable short id: folder hint + stem digits
            folder_key = _nfc(folder.name)
            # ASCII ids — удобно для pytest -k
            if "ОМТ" in folder_key:
                prefix = "OMT"
            elif folder_key.endswith("ЖП") or " ЖП" in folder_key:
                prefix = "GP"
            elif "молочн" in folder_key:
                prefix = "BR"
            elif "щитовид" in folder_key:
                prefix = "THY"
            elif "простат" in folder_key or "предстат" in folder_key:
                prefix = "PRO"
            elif "вен" in folder_key or "конечн" in folder_key:
                prefix = "VEIN"
            else:
                prefix = "CASE"
            m = re.search(r"\((\d+)\)", name)
            num = m.group(1) if m else re.sub(r"\W+", "_", txt.stem)[:24]
            case_id = f"{prefix}_{num}"
            cases.append((case_id, txt, expected))
    return cases


_CASES = _discover_cases()


def _is_finding_token(key: str) -> bool:
    if key in _SKIP_CLINICAL_EXACT:
        return False
    if any(key.startswith(p) for p in _SKIP_CLINICAL_PREFIXES):
        return False
    if is_normal_token(key):
        return False
    # keep size tokens that themselves encode a lesion (киста/узел/...), drop bare organ metrics
    low = key.lower()
    lesion = any(
        x in low
        for x in (
            "кист",
            "миом",
            "полип",
            "узел",
            "тромб",
            "стеноз",
            "окключ",
            "атером",
            "атеросклероз",
            "гиперплаз",
            "аденомиоз",
            "эндометриоз",
            "мастопат",
            "кальцин",
            "сладж",
            "гемангиом",
            "варикоз",
            "рефлюкс",
            "несостоятель",
        )
    )
    if _MEASURE_ONLY.match(key) and not lesion:
        return False
    return True


def _found_pathologies(enriched: dict) -> list[str]:
    """Pathology-rule hits + nonzero clinical finding tokens (for fuzzy gold match)."""
    path = enriched.get("pathology") or {}
    clinical = enriched.get("clinical") or {}
    labels: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        h = humanize_token(raw)
        if not h or h in seen:
            return
        seen.add(h)
        labels.append(h)

    for rule in path.get("matched") or []:
        if not isinstance(rule, dict):
            continue
        sev = str(rule.get("severity") or "")
        if sev not in {"pathology", "suspicious"}:
            continue
        add(str(rule.get("label") or rule.get("id") or ""))
        for term in rule.get("expr") or []:
            key = str(term).split(">")[0].split("<")[0].split("=")[0].strip()
            if key:
                add(key)

    by_token = path.get("by_token") or {}
    if isinstance(by_token, dict):
        for tok, sev in by_token.items():
            if sev in {"pathology", "suspicious"}:
                add(str(tok))

    if isinstance(clinical, dict):
        for key, val in clinical.items():
            if val in (None, 0, 0.0, "", False):
                continue
            if not _is_finding_token(str(key)):
                continue
            add(str(key))

    return labels


@pytest.mark.parametrize(
    "protocol_path,expected_path",
    [(p, e) for _, p, e in _CASES],
    ids=[c[0] for c in _CASES],
)
def test_protocol_pathologies(protocol_path: Path, expected_path: Path, capsys) -> None:
    expected = [
        ln.strip()
        for ln in expected_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert expected, f"empty gold file: {expected_path.name}"

    text = protocol_path.read_text(encoding="utf-8")
    print(f"\n>>> {protocol_path.parent.name} / {protocol_path.name}")
    out = tokenize_protocol_text(text, filename=protocol_path.name)
    enriched = enrich_tokenize_result(text, out)
    # для «норма» смотрим только сработавшие pathology-rules (без сырых clinical)
    expect_normal = len(expected) == 1 and expected[0].strip().lower() == "норма"
    found = _found_pathologies(enriched)
    if expect_normal:
        path = enriched.get("pathology") or {}
        found = []
        for rule in path.get("matched") or []:
            if isinstance(rule, dict) and rule.get("severity") in {"pathology", "suspicious"}:
                found.append(humanize_token(str(rule.get("label") or rule.get("id") or "")))

    print(f"    source={out.source} model={out.model}")
    print(f"    expected: {expected}")
    print(f"    found:    {found}")

    missing, extra = cover_expected(expected, found)
    if missing:
        pytest.fail(
            f"не покрыты ожидаемые патологии в {protocol_path.name}:\n"
            f"  missing: {missing}\n"
            f"  expected: {expected}\n"
            f"  found: {found}\n"
            f"  extra: {extra}\n"
            f"  clinical_keys: {sorted((enriched.get('clinical') or {}).keys())[:40]}"
        )
    if extra and expected != ["норма"]:
        # не валим тест на «лишних» — только показываем
        print(f"    (extra findings, ok): {extra}")
