"""Deterministic surgical journey engine over pathology tokens + routing matrix."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from .patient_alerts import collect_rads_scores

_THRESHOLD_RE = re.compile(
    r"^(?P<key>[A-Za-zА-Яа-яЁё0-9_]+)\s*(?P<op>>=|<=|>|<|==|=)\s*(?P<val>-?\d+(?:[.,]\d+)?)$"
)


def _matrix_path() -> Path:
    return Path(__file__).resolve().parent / "routing_matrix.json"


@lru_cache(maxsize=1)
def load_matrix() -> dict[str, Any]:
    path = _matrix_path()
    mtime = path.stat().st_mtime
    return _load_matrix_at(str(path), mtime)


@lru_cache(maxsize=2)
def _load_matrix_at(path_str: str, _mtime: float) -> dict[str, Any]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def reload_matrix() -> dict[str, Any]:
    load_matrix.cache_clear()
    _load_matrix_at.cache_clear()
    return load_matrix()


def save_matrix(data: dict[str, Any]) -> dict[str, Any]:
    """Persist routing matrix to disk and refresh cache."""
    if not isinstance(data, dict):
        raise ValueError("matrix must be an object")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("matrix.rules must be a non-empty list")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or not rule.get("id"):
            raise ValueError(f"rules[{i}] must have id")
        if not rule.get("slot_profile") and not rule.get("specialty"):
            raise ValueError(f"rules[{i}] needs slot_profile or specialty")
    # bump patch version lightly
    ver = str(data.get("version") or "1.0")
    data = dict(data)
    data["version"] = ver
    path = _matrix_path()
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return reload_matrix()


def matrix_profiles_summary(matrix: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Group rules by slot_profile for admin UI."""
    m = matrix or load_matrix()
    by: dict[str, dict[str, Any]] = {}
    for rule in m.get("rules") or []:
        profile = rule.get("slot_profile") or "other"
        if profile not in by:
            by[profile] = {
                "slot_profile": profile,
                "specialty": rule.get("specialty") or "",
                "study": rule.get("study") or "",
                "rules": [],
            }
        match = rule.get("match") or {}
        by[profile]["rules"].append(
            {
                "id": rule.get("id"),
                "specialty": rule.get("specialty"),
                "study": rule.get("study"),
                "target_days": rule.get("target_days"),
                "pathology_labels": list(match.get("pathology_labels") or []),
                "token_any": list(match.get("token_any") or []),
                "rads": match.get("rads"),
                "patient_message": rule.get("patient_message") or "",
                "clinic": rule.get("clinic"),
            }
        )
        # prefer first non-empty specialty/study on profile
        if rule.get("specialty") and not by[profile]["specialty"]:
            by[profile]["specialty"] = rule["specialty"]
        if rule.get("study") and not by[profile]["study"]:
            by[profile]["study"] = rule["study"]
    return list(by.values())


def apply_profile_triggers(
    profile: str,
    rules_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Replace all rules for a slot_profile with the given list.
    Each item: {id?, pathology_labels, token_any, rads, specialty, study, target_days, patient_message}
    """
    matrix = dict(load_matrix())
    defaults = matrix.get("defaults") or {}
    other = [r for r in (matrix.get("rules") or []) if r.get("slot_profile") != profile]
    new_rules: list[dict[str, Any]] = []
    for i, item in enumerate(rules_payload):
        rid = (item.get("id") or f"{profile}_{i+1}").strip()
        match: dict[str, Any] = {}
        labels = [x.strip() for x in (item.get("pathology_labels") or []) if str(x).strip()]
        tokens = [x.strip() for x in (item.get("token_any") or []) if str(x).strip()]
        if labels:
            match["pathology_labels"] = labels
        if tokens:
            match["token_any"] = tokens
        rads = item.get("rads")
        if isinstance(rads, dict) and rads.get("prefixes"):
            match["rads"] = {
                "prefixes": list(rads["prefixes"]),
                "min": float(rads.get("min") or 3),
            }
        if not match:
            raise ValueError(f"rule {rid}: empty match (нужны pathology_labels / token_any / rads)")
        new_rules.append(
            {
                "id": rid,
                "match": match,
                "study": item.get("study") or "",
                "specialty": item.get("specialty") or "",
                "slot_profile": profile,
                "target_days": int(item.get("target_days") or 7),
                "clinic": item.get("clinic") or defaults.get("clinic") or "",
                "patient_message": item.get("patient_message")
                or "По результатам исследования рекомендована консультация профильного специалиста.",
            }
        )
    matrix["rules"] = other + new_rules
    return save_matrix(matrix)


# ── model clock ──────────────────────────────────────────────


def ensure_clock(db: Session) -> models.ModelClock:
    row = db.get(models.ModelClock, "default")
    if not row:
        row = models.ModelClock(id="default", offset_seconds=0.0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def now(db: Session) -> datetime:
    clock = ensure_clock(db)
    return datetime.utcnow() + timedelta(seconds=float(clock.offset_seconds or 0))


def advance_clock(db: Session, *, hours: float = 0, days: float = 0) -> dict[str, Any]:
    clock = ensure_clock(db)
    delta = hours * 3600 + days * 86400
    clock.offset_seconds = float(clock.offset_seconds or 0) + delta
    clock.updated_at = datetime.utcnow()
    db.add(clock)
    db.commit()
    fired = process_due_escalations(db)
    return {
        "offset_seconds": clock.offset_seconds,
        "now": now(db).isoformat() + "Z",
        "advanced_hours": hours + days * 24,
        "escalations_fired": fired,
    }


def clock_status(db: Session) -> dict[str, Any]:
    clock = ensure_clock(db)
    return {
        "offset_seconds": clock.offset_seconds,
        "now": now(db).isoformat() + "Z",
        "real_utcnow": datetime.utcnow().isoformat() + "Z",
    }


# ── trigger matching ─────────────────────────────────────────


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("ё", "е").replace("_", " "))


def _pathology_labels(pathology: dict[str, Any] | None) -> set[str]:
    out: set[str] = set()
    for m in (pathology or {}).get("matched") or []:
        lab = m.get("label") or m.get("id") or ""
        if lab:
            out.add(_norm(lab))
            out.add(_norm(str(lab).replace("_", " ")))
    return out


def _rads_max_for_prefixes(clinical: dict[str, Any], prefixes: list[str]) -> float:
    best = 0.0
    for hit in collect_rads_scores(clinical):
        fam = str(hit.get("family") or "")
        if any(fam == p or fam.startswith(p) for p in prefixes):
            best = max(best, float(hit["score"]))
    return best


def _token_present(clinical: dict[str, Any], key: str) -> bool:
    if key not in clinical:
        return False
    v = clinical[key]
    if v is None or v is False or v == 0 or v == "":
        return False
    return True


def rule_matches(
    rule: dict[str, Any],
    clinical: dict[str, Any],
    pathology: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    match = rule.get("match") or {}
    evidence: dict[str, Any] = {"rule_id": rule.get("id"), "hits": []}
    labels = _pathology_labels(pathology)
    ok = False

    for lab in match.get("pathology_labels") or []:
        if _norm(lab) in labels or _norm(lab.replace("_", " ")) in labels:
            evidence["hits"].append({"type": "pathology_label", "value": lab})
            ok = True
        # also fire if catalog binary token present under same name
        for key in clinical:
            if _norm(key) == _norm(lab) or _norm(key) == _norm(lab.replace("_", " ")):
                if _token_present(clinical, key):
                    evidence["hits"].append({"type": "clinical_token", "value": key})
                    ok = True
                    break

    for tok in match.get("token_any") or []:
        if _token_present(clinical, tok):
            evidence["hits"].append({"type": "token", "value": tok, "raw": clinical.get(tok)})
            ok = True

    rads = match.get("rads")
    if rads:
        prefixes = list(rads.get("prefixes") or [])
        mn = float(rads.get("min") or 3)
        score = _rads_max_for_prefixes(clinical, prefixes)
        if score >= mn:
            evidence["hits"].append({"type": "rads", "prefixes": prefixes, "score": score, "min": mn})
            ok = True

    return ok, evidence


def evaluate_triggers(
    clinical: dict[str, Any] | None,
    pathology: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    matrix = load_matrix()
    clinical = clinical or {}
    matched: list[dict[str, Any]] = []
    for rule in matrix.get("rules") or []:
        ok, evidence = rule_matches(rule, clinical, pathology)
        if ok:
            matched.append({"rule": rule, "evidence": evidence})
    return matched


# ── persistence helpers ──────────────────────────────────────


def _add_event(
    db: Session,
    journey_id: str,
    kind: str,
    message: str,
    *,
    actor: str = "system",
    payload: dict | None = None,
    at: datetime | None = None,
) -> models.JourneyEvent:
    ev = models.JourneyEvent(
        journey_id=journey_id,
        kind=kind,
        actor=actor,
        message=message,
        payload=payload or {},
        created_at=at or datetime.utcnow(),
    )
    db.add(ev)
    return ev


def _send_notification(
    db: Session,
    *,
    journey: models.ClinicalJourney,
    channel: str,
    title: str,
    text: str,
    level: str = "info",
    escalation_key: str | None = None,
    actions: list | None = None,
    at: datetime | None = None,
) -> models.Notification:
    ts = at or now(db)
    n = models.Notification(
        journey_id=journey.id,
        patient_id=journey.patient_id,
        channel=channel,
        title=title,
        text=text,
        level=level,
        escalation_key=escalation_key,
        scheduled_for=ts,
        sent_at=ts,
        read=False,
        actions=actions or [],
        created_at=ts,
    )
    db.add(n)
    _add_event(
        db,
        journey.id,
        "notify",
        f"{channel}: {title}",
        payload={"channel": channel, "escalation_key": escalation_key},
        at=ts,
    )
    return n


def _create_task(
    db: Session,
    *,
    journey: models.ClinicalJourney,
    kind: str,
    title: str,
    script: str,
    at: datetime | None = None,
) -> models.CoordinatorTask:
    ts = at or now(db)
    t = models.CoordinatorTask(
        journey_id=journey.id,
        patient_id=journey.patient_id,
        kind=kind,
        title=title,
        script=script,
        state="open",
        due_at=ts,
        created_at=ts,
    )
    db.add(t)
    _add_event(db, journey.id, "task", title, payload={"kind": kind}, at=ts)
    return t


def create_journey_from_match(
    db: Session,
    *,
    patient_id: str,
    patient_name: str,
    match: dict[str, Any],
    source_route_id: str | None = None,
    source_study_override: str | None = None,
) -> models.ClinicalJourney:
    rule = match["rule"]
    evidence = match["evidence"]
    matrix = load_matrix()
    defaults = matrix.get("defaults") or {}
    ts = now(db)

    # idempotency: same source_route + rule
    if source_route_id:
        existing = (
            db.query(models.ClinicalJourney)
            .filter(
                models.ClinicalJourney.source_route_id == source_route_id,
                models.ClinicalJourney.matrix_rule_id == rule["id"],
                models.ClinicalJourney.status != "cancelled",
            )
            .first()
        )
        if existing:
            return existing

    target_days = int(rule.get("target_days") or 7)
    journey = models.ClinicalJourney(
        patient_id=patient_id,
        patient_name=patient_name or patient_id,
        trigger_pathology=rule.get("id") or (evidence.get("hits") or [{}])[0].get("value", "trigger"),
        source_study=source_study_override or rule.get("study") or "",
        source_route_id=source_route_id,
        stage="detected",
        status="active",
        clinic=rule.get("clinic") or defaults.get("clinic") or "",
        coordinator=rule.get("coordinator") or defaults.get("coordinator") or "",
        specialty=rule.get("specialty") or "",
        slot_profile=rule.get("slot_profile") or "",
        target_due_at=ts + timedelta(days=target_days),
        matrix_rule_id=rule["id"],
        matrix_version=str(matrix.get("version") or "1"),
        evidence={
            **evidence,
            "patient_message": rule.get("patient_message"),
            "specialty": rule.get("specialty"),
            "target_days": target_days,
        },
        detected_at=ts,
        created_at=ts,
        updated_at=ts,
    )
    # human-readable trigger from first pathology hit
    for h in evidence.get("hits") or []:
        if h.get("type") == "pathology_label":
            journey.trigger_pathology = str(h["value"]).replace("_", " ")
            break
        if h.get("type") == "rads":
            journey.trigger_pathology = f"RADS≥{h.get('min')} ({h.get('score')})"
            break

    db.add(journey)
    db.flush()
    _add_event(
        db,
        journey.id,
        "created",
        f"Маршрут создан: {journey.trigger_pathology} → {journey.specialty}",
        payload={"rule_id": rule["id"], "evidence": evidence},
        at=ts,
    )

    msg = rule.get("patient_message") or (
        "По результатам исследования выявлены изменения, требующие консультации "
        "профильного специалиста для определения дальнейшей тактики."
    )
    for ch in ("cabinet", "push", "sms"):
        _send_notification(
            db,
            journey=journey,
            channel=ch,
            title="Результат УЗИ готов",
            text=msg,
            level="month",
            escalation_key="initial",
            actions=["book", "online", "callback"],
            at=ts,
        )
    journey.stage = "notified"
    journey.updated_at = ts
    db.add(journey)
    db.commit()
    db.refresh(journey)
    return journey


def create_journeys_from_protocol(
    db: Session,
    *,
    patient_id: str,
    patient_name: str,
    clinical: dict[str, Any] | None,
    pathology: dict[str, Any] | None = None,
    source_route_id: str | None = None,
) -> dict[str, Any]:
    matches = evaluate_triggers(clinical, pathology)
    if not matches:
        return {
            "triggered": False,
            "reason": "no_trigger",
            "journeys": [],
            "matches": [],
        }
    journeys = []
    for m in matches:
        j = create_journey_from_match(
            db,
            patient_id=patient_id,
            patient_name=patient_name,
            match=m,
            source_route_id=source_route_id,
            source_study_override=m["rule"].get("study"),
        )
        journeys.append(j)
    return {
        "triggered": True,
        "reason": None,
        "journeys": journeys,
        "matches": [
            {"rule_id": m["rule"]["id"], "evidence": m["evidence"]} for m in matches
        ],
    }


# ── schedule stubs ───────────────────────────────────────────

_SLOT_DOCTORS = {
    "operating_gyn": [
        ("Иванова Е.А.", "оперирующий гинеколог"),
        ("Смирнова О.В.", "оперирующий гинеколог"),
    ],
    "mammologist": [("Кузнецова Н.П.", "маммолог")],
    "surgeon_abd": [("Петров А.И.", "хирург")],
    "endocrinologist": [("Орлова Т.М.", "эндокринолог")],
    "urologist": [("Васильев Д.С.", "уролог")],
}

_LOCATIONS = ["Онлайн", "ВДНХ", "Текстильщики", "Сенежская"]


def list_slots(
    db: Session,
    *,
    profile: str,
    journey_id: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    ts = now(db)
    doctors = _SLOT_DOCTORS.get(profile) or [("Специалист", "врач")]
    slots = []
    offsets_h = [4, 18, 26, 42, 50, 74]
    for i, oh in enumerate(offsets_h[:limit]):
        doc, spec = doctors[i % len(doctors)]
        loc = _LOCATIONS[i % len(_LOCATIONS)]
        modality = "online" if loc == "Онлайн" else "in_person"
        start = ts + timedelta(hours=oh)
        slots.append(
            {
                "id": f"slot-{profile}-{i}-{int(start.timestamp())}",
                "profile": profile,
                "journey_id": journey_id,
                "modality": modality,
                "location": loc,
                "doctor": doc,
                "specialty": spec,
                "starts_at": start.isoformat() + "Z",
            }
        )
    return slots


def book_slot(
    db: Session,
    journey: models.ClinicalJourney,
    *,
    slot: dict[str, Any],
    kind: str = "consult",
) -> models.Appointment:
    ts = now(db)
    starts = datetime.fromisoformat(str(slot["starts_at"]).replace("Z", ""))
    ap = models.Appointment(
        journey_id=journey.id,
        patient_id=journey.patient_id,
        modality=slot.get("modality") or "in_person",
        location=slot.get("location") or "",
        doctor=slot.get("doctor") or "",
        specialty=slot.get("specialty") or journey.specialty,
        starts_at=starts,
        state="booked",
        kind=kind,
        created_at=ts,
    )
    db.add(ap)
    if kind == "control":
        journey.stage = "control_booked"
    else:
        journey.stage = "booked"
    journey.status = "active"
    journey.updated_at = ts
    db.add(journey)
    _add_event(
        db,
        journey.id,
        "booked",
        f"Запись: {ap.doctor} · {ap.location} · {starts.isoformat()}",
        payload={"appointment_id": ap.id, "kind": kind},
        at=ts,
    )
    db.commit()
    db.refresh(ap)
    return ap


# ── outcomes / tactics ───────────────────────────────────────


def appointment_outcome(
    db: Session,
    journey: models.ClinicalJourney,
    *,
    outcome: str,
    appointment_id: str | None = None,
) -> models.ClinicalJourney:
    ts = now(db)
    ap = None
    if appointment_id:
        ap = db.get(models.Appointment, appointment_id)
    if not ap:
        ap = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.journey_id == journey.id,
                models.Appointment.state == "booked",
            )
            .order_by(models.Appointment.starts_at.desc())
            .first()
        )
    if not ap:
        raise ValueError("no booked appointment")

    if outcome == "completed":
        ap.state = "completed"
        journey.stage = "visit_done" if ap.kind == "consult" else "control_done"
        if ap.kind == "control":
            journey.status = "completed"
        _add_event(db, journey.id, "visit_done", "Приём состоялся", at=ts)
    elif outcome == "cancelled":
        ap.state = "cancelled"
        journey.stage = "needs_rebook"
        _add_event(db, journey.id, "cancelled", "Запись отменена → требуется повторная запись", at=ts)
        _send_notification(
            db,
            journey=journey,
            channel="cabinet",
            title="Требуется повторная запись",
            text="Запись на консультацию отменена. Вы можете выбрать другое время — очно или онлайн.",
            actions=["book", "online"],
            at=ts,
        )
    elif outcome == "no_show":
        ap.state = "no_show"
        journey.stage = "no_show"
        _add_event(db, journey.id, "no_show", "Неявка №1", at=ts)
        _send_notification(
            db,
            journey=journey,
            channel="cabinet",
            title="Консультация не состоялась",
            text=(
                "Сегодня не состоялась запланированная консультация врача. "
                "Если вопрос остаётся актуальным, мы можем предложить другое время или онлайн-консультацию."
            ),
            actions=["book", "online"],
            escalation_key="no_show",
            at=ts,
        )
        # reset escalation baseline to no-show moment
        journey.detected_at = ts
        journey.last_escalation_key = "no_show"
    else:
        raise ValueError(f"unknown outcome: {outcome}")

    journey.updated_at = ts
    db.add(ap)
    db.add(journey)
    db.commit()
    db.refresh(journey)
    return journey


TACTICS = {
    "surgery": "Оперативное лечение показано",
    "extra_exam": "Требуется дополнительное обследование",
    "watch": "Динамическое наблюдение",
    "no_surgery": "Операция не показана",
    "refused": "Пациент отказался",
    "other_profile": "Направление в другой профиль",
}


def set_tactics(
    db: Session,
    journey: models.ClinicalJourney,
    tactics: str,
    *,
    create_referral: bool = True,
) -> models.ClinicalJourney:
    if tactics not in TACTICS:
        raise ValueError(f"unknown tactics: {tactics}")
    ts = now(db)
    journey.tactics = tactics
    journey.stage = "tactics_chosen"
    journey.updated_at = ts
    _add_event(
        db,
        journey.id,
        "tactics",
        TACTICS[tactics],
        actor="doctor",
        payload={"tactics": tactics},
        at=ts,
    )
    if tactics == "surgery" and create_referral:
        journey.stage = "referral_created"
        _add_event(
            db,
            journey.id,
            "referral",
            "Создано направление на госпитализацию (stub 1С)",
            actor="doctor",
            at=ts,
        )
        _create_task(
            db,
            journey=journey,
            kind="hospitalization",
            title="Назначить дату госпитализации",
            script=(
                f"Пациент {journey.patient_name}: показано оперативное лечение "
                f"({journey.trigger_pathology}). Назначьте дату госпитализации не позднее 3 рабочих дней."
            ),
            at=ts,
        )
        _send_notification(
            db,
            journey=journey,
            channel="cabinet",
            title="Направление на госпитализацию",
            text=(
                "По результатам консультации сформировано направление на госпитализацию. "
                "С вами свяжется менеджер по госпитализации."
            ),
            level="urgent",
            at=ts,
        )
    elif tactics == "watch":
        journey.status = "completed"
        journey.stage = "control_done"
    elif tactics in {"no_surgery", "refused"}:
        journey.status = "completed"
    journey.updated_at = ts
    db.add(journey)
    db.commit()
    db.refresh(journey)
    return journey


def schedule_hospitalization(
    db: Session,
    journey: models.ClinicalJourney,
    *,
    when: datetime | None = None,
) -> models.ClinicalJourney:
    ts = now(db)
    journey.hospitalization_date = when or (ts + timedelta(days=3))
    journey.stage = "hospitalization_scheduled"
    journey.updated_at = ts
    _add_event(
        db,
        journey.id,
        "hospitalization_scheduled",
        f"Госпитализация назначена на {journey.hospitalization_date.isoformat()}",
        at=ts,
    )
    # close open hospitalization tasks
    for t in (
        db.query(models.CoordinatorTask)
        .filter(
            models.CoordinatorTask.journey_id == journey.id,
            models.CoordinatorTask.kind == "hospitalization",
            models.CoordinatorTask.state == "open",
        )
        .all()
    ):
        t.state = "done"
        t.completed_at = ts
        db.add(t)
    db.add(journey)
    db.commit()
    db.refresh(journey)
    return journey


def mis_progress(
    db: Session,
    journey: models.ClinicalJourney,
    kind: str,
) -> models.ClinicalJourney:
    """hospitalized | operated | discharged"""
    ts = now(db)
    matrix = load_matrix()
    defaults = matrix.get("defaults") or {}
    if kind == "hospitalized":
        journey.stage = "hospitalized"
    elif kind == "operated":
        journey.stage = "operated"
        _add_event(db, journey.id, "operated", "Операция выполнена (услуга из МИС)", at=ts)
    elif kind == "discharged":
        journey.stage = "discharged"
        _add_event(db, journey.id, "discharged", "Выписка", at=ts)
        # auto-book control if possible
        days = int(defaults.get("postop_control_days") or 7)
        slots = list_slots(db, profile=journey.slot_profile or "operating_gyn", journey_id=journey.id)
        # prefer slot ~ control day
        control_at = ts + timedelta(days=days)
        best = min(
            slots,
            key=lambda s: abs(
                datetime.fromisoformat(s["starts_at"].replace("Z", "")).timestamp()
                - control_at.timestamp()
            ),
        )
        book_slot(db, journey, slot=best, kind="control")
        _send_notification(
            db,
            journey=journey,
            channel="cabinet",
            title="Контрольный приём назначен",
            text=(
                f"Контрольный приём после проведённого лечения назначен на "
                f"{best['starts_at']}. Подтвердить / изменить время можно в личном кабинете."
            ),
            actions=["confirm", "reschedule"],
            at=ts,
        )
        return journey  # book_slot already committed
    else:
        raise ValueError(kind)
    journey.updated_at = ts
    db.add(journey)
    _add_event(db, journey.id, kind, kind, at=ts)
    db.commit()
    db.refresh(journey)
    return journey


def patient_response(
    db: Session,
    journey: models.ClinicalJourney,
    action: str,
) -> models.ClinicalJourney:
    ts = now(db)
    if action == "already_seen":
        journey.stage = "visit_done"
        journey.status = "completed"
        _add_event(db, journey.id, "patient_already_seen", "Пациент отметил обращение вне клиники", actor="patient", at=ts)
    elif action == "decline":
        journey.stage = "abandoned"
        journey.status = "abandoned"
        _add_event(db, journey.id, "patient_decline", "Пациент не планирует обращаться", actor="patient", at=ts)
    elif action == "book":
        pass  # UI opens slots
    else:
        raise ValueError(action)
    journey.updated_at = ts
    db.add(journey)
    db.commit()
    db.refresh(journey)
    return journey


# ── escalations on model time ────────────────────────────────


def _escalation_plan() -> list[dict[str, Any]]:
    matrix = load_matrix()
    return list((matrix.get("defaults") or {}).get("escalation") or [])


def process_due_escalations(db: Session) -> list[dict[str, Any]]:
    ts = now(db)
    fired: list[dict[str, Any]] = []
    active = (
        db.query(models.ClinicalJourney)
        .filter(
            models.ClinicalJourney.status == "active",
            models.ClinicalJourney.stage.in_(
                ["notified", "needs_rebook", "no_show", "detected", "referral_created"]
            ),
        )
        .all()
    )
    for j in active:
        # hospitalization without date
        if j.stage == "referral_created" and not j.hospitalization_date:
            hours = (ts - (j.updated_at or j.detected_at)).total_seconds() / 3600
            if hours >= 24 and j.last_escalation_key != "hosp_24":
                _create_task(
                    db,
                    journey=j,
                    kind="hospitalization",
                    title="Нет даты госпитализации (24ч)",
                    script=f"Срочно назначить дату госпитализации для {j.patient_name}.",
                    at=ts,
                )
                j.last_escalation_key = "hosp_24"
                fired.append({"journey_id": j.id, "key": "hosp_24"})
            elif hours >= 72 and j.last_escalation_key != "hosp_72":
                _create_task(
                    db,
                    journey=j,
                    kind="hospitalization",
                    title="Нет даты госпитализации (72ч)",
                    script=f"Повтор: назначить дату госпитализации для {j.patient_name}.",
                    at=ts,
                )
                j.last_escalation_key = "hosp_72"
                fired.append({"journey_id": j.id, "key": "hosp_72"})
            elif hours >= 120 and j.last_escalation_key != "hosp_lead":
                _create_task(
                    db,
                    journey=j,
                    kind="escalate_lead",
                    title="Эскалация руководителю: госпитализация",
                    script=f"Маршрут {j.id}: нет даты госпитализации >5 дней.",
                    at=ts,
                )
                j.last_escalation_key = "hosp_lead"
                fired.append({"journey_id": j.id, "key": "hosp_lead"})
            db.add(j)
            continue

        if j.stage not in {"notified", "needs_rebook", "no_show"}:
            continue

        # already booked? skip booking escalations
        booked = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.journey_id == j.id,
                models.Appointment.state == "booked",
                models.Appointment.kind == "consult",
            )
            .first()
        )
        if booked:
            continue

        hours = (ts - j.detected_at).total_seconds() / 3600
        for step in _escalation_plan():
            key = step["key"]
            if j.last_escalation_key == key:
                continue
            # skip if a later key already applied — order by after_hours
            after = float(step.get("after_hours") or 0)
            if hours < after:
                continue
            # only fire if this is the highest due step not yet passed
            # mark and fire one step at a time (highest due)
            pass

        due_steps = [s for s in _escalation_plan() if hours >= float(s.get("after_hours") or 0)]
        if not due_steps:
            continue
        step = due_steps[-1]
        key = step["key"]
        if j.last_escalation_key == key:
            continue
        # don't re-fire earlier keys if we're past them — jump to latest
        kind = step.get("kind")
        if kind == "not_engaged":
            j.stage = "not_engaged"
            j.status = "abandoned"
            _add_event(db, j.id, "not_engaged", "Маршрут не реализован / пациент не вовлечён", at=ts)
        elif kind == "coordinator_call":
            name = j.patient_name or "пациент"
            _create_task(
                db,
                journey=j,
                kind="call",
                title="Персональный звонок координатора",
                script=(
                    f"Добрый день, {name}. Вы недавно проходили у нас УЗИ. "
                    f"По результатам исследования рекомендована консультация ({j.specialty}) "
                    f"для определения дальнейшей тактики. Мы видим, что консультация пока не состоялась. "
                    f"Могу помочь подобрать врача и удобное время — очно или онлайн."
                ),
                at=ts,
            )
        elif kind in {"reminder", "soft_final"}:
            text = (
                "Напоминание: по результату УЗИ Вам рекомендована консультация профильного специалиста. "
                "Вы можете выбрать удобный формат — очно или онлайн."
            )
            if kind == "soft_final":
                text = (
                    "Напоминаем о рекомендации обратиться к профильному врачу по результатам "
                    "ранее выполненного исследования. Если консультация уже состоялась в другой "
                    "медицинской организации, Вы можете отметить это в личном кабинете."
                )
            actions = list(step.get("actions") or ["book", "online"])
            for ch in step.get("channels") or ["cabinet"]:
                if ch == "call_task":
                    continue
                _send_notification(
                    db,
                    journey=j,
                    channel=ch,
                    title="Напоминание о консультации",
                    text=text,
                    escalation_key=key,
                    actions=actions,
                    at=ts,
                )
        j.last_escalation_key = key
        j.updated_at = ts
        db.add(j)
        fired.append({"journey_id": j.id, "key": key, "kind": kind})
    db.commit()
    return fired


def handle_mis_event(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or "")
    kind = str(payload.get("kind") or "")
    if not event_id or not kind:
        raise ValueError("event_id and kind required")
    if db.get(models.ProcessedMisEvent, event_id):
        return {"ok": True, "duplicate": True}

    journey_id = payload.get("journey_id")
    journey = db.get(models.ClinicalJourney, journey_id) if journey_id else None

    if kind == "protocol_voided" and journey:
        journey.status = "cancelled"
        journey.stage = "abandoned"
        _add_event(db, journey.id, "voided", "Протокол аннулирован — маршрут закрыт", at=now(db))
        db.add(journey)
    elif kind == "protocol_amended" and journey:
        clinical = payload.get("clinical") or {}
        pathology = payload.get("pathology") or {}
        matches = evaluate_triggers(clinical, pathology)
        rule_ids = {m["rule"]["id"] for m in matches}
        if journey.matrix_rule_id not in rule_ids:
            journey.status = "cancelled"
            _add_event(db, journey.id, "amended_closed", "После исправления протокола триггер снят", at=now(db))
        else:
            _add_event(db, journey.id, "amended", "Протокол исправлен, триггер подтверждён", at=now(db))
        db.add(journey)
    elif kind == "appointment_completed" and journey:
        appointment_outcome(db, journey, outcome="completed", appointment_id=payload.get("appointment_id"))
    elif kind == "appointment_no_show" and journey:
        appointment_outcome(db, journey, outcome="no_show", appointment_id=payload.get("appointment_id"))
    elif kind == "hospitalized" and journey:
        mis_progress(db, journey, "hospitalized")
    elif kind == "service_rendered" and journey and payload.get("service") == "surgery":
        mis_progress(db, journey, "operated")
    elif kind == "discharged" and journey:
        mis_progress(db, journey, "discharged")
    else:
        pass

    db.add(
        models.ProcessedMisEvent(
            event_id=event_id,
            kind=kind,
            journey_id=journey.id if journey else None,
            processed_at=now(db),
        )
    )
    db.commit()
    return {"ok": True, "duplicate": False, "journey_id": journey.id if journey else None}


# ── funnel analytics ─────────────────────────────────────────


FUNNEL_STAGES = [
    ("triggered", "УЗИ с хирургическими триггерами", None),
    ("notified", "Получили уведомление", {"notified", "booked", "visit_done", "tactics_chosen", "referral_created", "hospitalization_scheduled", "hospitalized", "operated", "discharged", "control_booked", "control_done", "needs_rebook", "no_show", "not_engaged"}),
    ("booked", "Записались к специалисту", {"booked", "visit_done", "tactics_chosen", "referral_created", "hospitalization_scheduled", "hospitalized", "operated", "discharged", "control_booked", "control_done", "no_show", "needs_rebook"}),
    ("visit_done", "Приём состоялся", {"visit_done", "tactics_chosen", "referral_created", "hospitalization_scheduled", "hospitalized", "operated", "discharged", "control_booked", "control_done"}),
    ("surgery_rec", "Операция рекомендована", None),
    ("referral", "Создано направление", {"referral_created", "hospitalization_scheduled", "hospitalized", "operated", "discharged", "control_booked", "control_done"}),
    ("hosp_sched", "Назначена госпитализация", {"hospitalization_scheduled", "hospitalized", "operated", "discharged", "control_booked", "control_done"}),
    ("hospitalized", "Госпитализированы", {"hospitalized", "operated", "discharged", "control_booked", "control_done"}),
    ("operated", "Оперированы", {"operated", "discharged", "control_booked", "control_done"}),
    ("control", "Контрольный визит", {"control_booked", "control_done"}),
]


def funnel_stats(db: Session) -> dict[str, Any]:
    rows = db.query(models.ClinicalJourney).all()
    total = len(rows)

    def count_stages(stages: set[str] | None) -> int:
        if stages is None:
            return total
        return sum(1 for r in rows if r.stage in stages)

    surgery_rec = sum(1 for r in rows if r.tactics == "surgery" or r.stage in {
        "referral_created", "hospitalization_scheduled", "hospitalized", "operated",
        "discharged", "control_booked", "control_done",
    })

    steps = []
    prev = total or 1
    for key, label, stages in FUNNEL_STAGES:
        if key == "triggered":
            n = total
        elif key == "surgery_rec":
            n = surgery_rec
        else:
            n = count_stages(stages)
        pct = round(100.0 * n / prev, 1) if prev else 0.0
        steps.append({"key": key, "label": label, "count": n, "pct_of_prev": pct})
        if key != "surgery_rec":
            prev = n or prev

    return {"total": total, "steps": steps, "journeys": [journey_to_dict(r, db, light=True) for r in rows]}


def journey_to_dict(
    j: models.ClinicalJourney,
    db: Session | None = None,
    *,
    light: bool = False,
) -> dict[str, Any]:
    d = {
        "id": j.id,
        "patient_id": j.patient_id,
        "patient_name": j.patient_name,
        "trigger_pathology": j.trigger_pathology,
        "source_study": j.source_study,
        "source_route_id": j.source_route_id,
        "stage": j.stage,
        "status": j.status,
        "clinic": j.clinic,
        "coordinator": j.coordinator,
        "specialty": j.specialty,
        "slot_profile": j.slot_profile,
        "target_due_at": j.target_due_at.isoformat() + "Z" if j.target_due_at else None,
        "matrix_rule_id": j.matrix_rule_id,
        "matrix_version": j.matrix_version,
        "evidence": j.evidence or {},
        "tactics": j.tactics,
        "hospitalization_date": j.hospitalization_date.isoformat() + "Z" if j.hospitalization_date else None,
        "detected_at": j.detected_at.isoformat() + "Z" if j.detected_at else None,
        "created_at": j.created_at.isoformat() + "Z" if j.created_at else None,
        "updated_at": j.updated_at.isoformat() + "Z" if j.updated_at else None,
    }
    if light or db is None:
        return d
    events = (
        db.query(models.JourneyEvent)
        .filter(models.JourneyEvent.journey_id == j.id)
        .order_by(models.JourneyEvent.created_at.asc())
        .all()
    )
    appts = (
        db.query(models.Appointment)
        .filter(models.Appointment.journey_id == j.id)
        .order_by(models.Appointment.starts_at.asc())
        .all()
    )
    notifs = (
        db.query(models.Notification)
        .filter(models.Notification.journey_id == j.id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )
    tasks = (
        db.query(models.CoordinatorTask)
        .filter(models.CoordinatorTask.journey_id == j.id)
        .order_by(models.CoordinatorTask.created_at.desc())
        .all()
    )
    d["events"] = [
        {
            "id": e.id,
            "kind": e.kind,
            "actor": e.actor,
            "message": e.message,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() + "Z" if e.created_at else None,
        }
        for e in events
    ]
    d["appointments"] = [
        {
            "id": a.id,
            "modality": a.modality,
            "location": a.location,
            "doctor": a.doctor,
            "specialty": a.specialty,
            "starts_at": a.starts_at.isoformat() + "Z" if a.starts_at else None,
            "state": a.state,
            "kind": a.kind,
        }
        for a in appts
    ]
    d["notifications"] = [notification_to_dict(n) for n in notifs]
    d["tasks"] = [task_to_dict(t) for t in tasks]
    return d


def notification_to_dict(n: models.Notification) -> dict[str, Any]:
    return {
        "id": n.id,
        "journey_id": n.journey_id,
        "patient_id": n.patient_id,
        "channel": n.channel,
        "title": n.title,
        "text": n.text,
        "level": n.level,
        "escalation_key": n.escalation_key,
        "sent_at": n.sent_at.isoformat() + "Z" if n.sent_at else None,
        "read": n.read,
        "actions": n.actions or [],
        "created_at": n.created_at.isoformat() + "Z" if n.created_at else None,
    }


def task_to_dict(t: models.CoordinatorTask) -> dict[str, Any]:
    return {
        "id": t.id,
        "journey_id": t.journey_id,
        "patient_id": t.patient_id,
        "kind": t.kind,
        "title": t.title,
        "script": t.script,
        "state": t.state,
        "due_at": t.due_at.isoformat() + "Z" if t.due_at else None,
        "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
        "completed_at": t.completed_at.isoformat() + "Z" if t.completed_at else None,
    }
