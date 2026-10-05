"""Journey / funnel / demo clock API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..routing import journey_engine as je

router = APIRouter(prefix="/api/v1", tags=["journeys"])


class FromProtocolIn(BaseModel):
    patient_id: str
    patient_name: str = ""
    source_route_id: str | None = None
    clinical: dict[str, Any] = Field(default_factory=dict)
    pathology: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None  # optional: re-tokenize if clinical empty


class BookIn(BaseModel):
    slot: dict[str, Any]
    kind: str = "consult"


class OutcomeIn(BaseModel):
    outcome: str  # completed|cancelled|no_show
    appointment_id: str | None = None


class TacticsIn(BaseModel):
    tactics: str
    create_referral: bool = True


class PatientResponseIn(BaseModel):
    action: str  # already_seen|decline|book


class HospDateIn(BaseModel):
    when: str | None = None  # ISO


class ClockIn(BaseModel):
    hours: float = 0
    days: float = 0
    reset: bool = False


class MisEventIn(BaseModel):
    event_id: str
    kind: str
    journey_id: str | None = None
    appointment_id: str | None = None
    service: str | None = None
    clinical: dict[str, Any] | None = None
    pathology: dict[str, Any] | None = None


@router.post("/journeys/from-protocol")
def journeys_from_protocol(payload: FromProtocolIn, db: Session = Depends(get_db)):
    clinical = dict(payload.clinical or {})
    pathology = dict(payload.pathology or {})
    if payload.text and not clinical:
        from ..routing.protocol_tokenizer import enrich_tokenize_result, tokenize_protocol_text

        out = tokenize_protocol_text(payload.text)
        enriched = enrich_tokenize_result(payload.text, out)
        clinical = enriched["clinical"]
        pathology = enriched["pathology"]
    result = je.create_journeys_from_protocol(
        db,
        patient_id=payload.patient_id,
        patient_name=payload.patient_name or payload.patient_id,
        clinical=clinical,
        pathology=pathology,
        source_route_id=payload.source_route_id,
    )
    return {
        "triggered": result["triggered"],
        "reason": result.get("reason"),
        "matches": result.get("matches") or [],
        "journeys": [je.journey_to_dict(j, db) for j in result.get("journeys") or []],
    }


@router.get("/journeys")
def list_journeys(
    patient_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.ClinicalJourney)
    if patient_id:
        q = q.filter(models.ClinicalJourney.patient_id == patient_id)
    if status:
        q = q.filter(models.ClinicalJourney.status == status)
    rows = q.order_by(models.ClinicalJourney.created_at.desc()).all()
    return [je.journey_to_dict(j, db, light=True) for j in rows]


@router.get("/journeys/{journey_id}")
def get_journey(journey_id: str, db: Session = Depends(get_db)):
    j = db.get(models.ClinicalJourney, journey_id)
    if not j:
        raise HTTPException(404, "journey not found")
    return je.journey_to_dict(j, db)


@router.post("/journeys/{journey_id}/book")
def book_journey(journey_id: str, payload: BookIn, db: Session = Depends(get_db)):
    j = db.get(models.ClinicalJourney, journey_id)
    if not j:
        raise HTTPException(404, "journey not found")
    ap = je.book_slot(db, j, slot=payload.slot, kind=payload.kind)
    return {"appointment": {
        "id": ap.id,
        "starts_at": ap.starts_at.isoformat() + "Z",
        "doctor": ap.doctor,
        "location": ap.location,
        "modality": ap.modality,
        "state": ap.state,
        "kind": ap.kind,
    }, "journey": je.journey_to_dict(j, db, light=True)}


@router.post("/journeys/{journey_id}/appointment-outcome")
def journey_outcome(journey_id: str, payload: OutcomeIn, db: Session = Depends(get_db)):
    j = db.get(models.ClinicalJourney, journey_id)
    if not j:
        raise HTTPException(404, "journey not found")
    try:
        j = je.appointment_outcome(
            db, j, outcome=payload.outcome, appointment_id=payload.appointment_id
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return je.journey_to_dict(j, db)


@router.post("/journeys/{journey_id}/tactics")
def journey_tactics(journey_id: str, payload: TacticsIn, db: Session = Depends(get_db)):
    j = db.get(models.ClinicalJourney, journey_id)
    if not j:
        raise HTTPException(404, "journey not found")
    try:
        j = je.set_tactics(db, j, payload.tactics, create_referral=payload.create_referral)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return je.journey_to_dict(j, db)


@router.post("/journeys/{journey_id}/hospitalization-date")
def journey_hosp_date(journey_id: str, payload: HospDateIn, db: Session = Depends(get_db)):
    j = db.get(models.ClinicalJourney, journey_id)
    if not j:
        raise HTTPException(404, "journey not found")
    when = None
    if payload.when:
        when = datetime.fromisoformat(payload.when.replace("Z", ""))
    j = je.schedule_hospitalization(db, j, when=when)
    return je.journey_to_dict(j, db)


@router.post("/journeys/{journey_id}/patient-response")
def journey_patient_response(
    journey_id: str, payload: PatientResponseIn, db: Session = Depends(get_db)
):
    j = db.get(models.ClinicalJourney, journey_id)
    if not j:
        raise HTTPException(404, "journey not found")
    try:
        j = je.patient_response(db, j, payload.action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return je.journey_to_dict(j, db)


@router.get("/schedule/slots")
def schedule_slots(
    profile: str = Query(...),
    journey_id: str | None = None,
    db: Session = Depends(get_db),
):
    return {"slots": je.list_slots(db, profile=profile, journey_id=journey_id)}


@router.get("/notifications")
def list_notifications(
    patient_id: str = Query(...),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.Notification)
        .filter(models.Notification.patient_id == patient_id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )
    # prefer cabinet channel for UI, but return all
    return [je.notification_to_dict(n) for n in rows]


@router.post("/notifications/{notif_id}/read")
def read_notification(notif_id: str, db: Session = Depends(get_db)):
    n = db.get(models.Notification, notif_id)
    if not n:
        raise HTTPException(404, "notification not found")
    n.read = True
    db.add(n)
    db.commit()
    return je.notification_to_dict(n)


@router.get("/coordinator/tasks")
def list_tasks(
    state: str | None = Query("open"),
    db: Session = Depends(get_db),
):
    q = db.query(models.CoordinatorTask)
    if state:
        q = q.filter(models.CoordinatorTask.state == state)
    rows = q.order_by(models.CoordinatorTask.created_at.desc()).all()
    return [je.task_to_dict(t) for t in rows]


@router.post("/coordinator/tasks/{task_id}/complete")
def complete_task(task_id: str, db: Session = Depends(get_db)):
    t = db.get(models.CoordinatorTask, task_id)
    if not t:
        raise HTTPException(404, "task not found")
    t.state = "done"
    t.completed_at = je.now(db)
    db.add(t)
    db.commit()
    return je.task_to_dict(t)


@router.get("/demo/clock")
def get_clock(db: Session = Depends(get_db)):
    return je.clock_status(db)


@router.post("/demo/clock")
def post_clock(payload: ClockIn, db: Session = Depends(get_db)):
    if payload.reset:
        clock = je.ensure_clock(db)
        clock.offset_seconds = 0.0
        db.add(clock)
        db.commit()
        return je.clock_status(db)
    return je.advance_clock(db, hours=payload.hours, days=payload.days)


@router.get("/analytics/funnel")
def analytics_funnel(db: Session = Depends(get_db)):
    return je.funnel_stats(db)


@router.post("/mis/events")
def mis_events(payload: MisEventIn, db: Session = Depends(get_db)):
    try:
        return je.handle_mis_event(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/routing/matrix")
def get_matrix():
    return je.load_matrix()


@router.get("/routing/matrix/profiles")
def get_matrix_profiles():
    return {"version": je.load_matrix().get("version"), "profiles": je.matrix_profiles_summary()}


class MatrixPutIn(BaseModel):
    version: str | None = None
    defaults: dict[str, Any] | None = None
    rules: list[dict[str, Any]]


@router.put("/routing/matrix")
def put_matrix(payload: MatrixPutIn):
    current = je.load_matrix()
    data = {
        "version": payload.version or current.get("version") or "1.0",
        "defaults": payload.defaults if payload.defaults is not None else current.get("defaults"),
        "rules": payload.rules,
    }
    try:
        saved = je.save_matrix(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return saved


class ProfileTriggersIn(BaseModel):
    specialty: str | None = None
    study: str | None = None
    rules: list[dict[str, Any]]


@router.put("/routing/matrix/profiles/{profile}")
def put_profile_triggers(profile: str, payload: ProfileTriggersIn):
    # stamp specialty/study onto rules if provided at profile level
    rules = []
    for r in payload.rules:
        item = dict(r)
        if payload.specialty and not item.get("specialty"):
            item["specialty"] = payload.specialty
        if payload.study and not item.get("study"):
            item["study"] = payload.study
        rules.append(item)
    try:
        saved = je.apply_profile_triggers(profile, rules)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "ok": True,
        "version": saved.get("version"),
        "profiles": je.matrix_profiles_summary(saved),
    }


@router.get("/routing/pathology-labels")
def pathology_label_suggestions():
    """Unique pathology rule labels for admin chips."""
    from .pathology import load_pathology_rules

    labels: list[str] = []
    seen: set[str] = set()
    for r in load_pathology_rules():
        lab = str(r.get("label") or "").strip()
        if lab and lab not in seen:
            seen.add(lab)
            labels.append(lab)
    return {"labels": labels}


@router.post("/demo/seed-journeys")
def seed_journeys(db: Session = Depends(get_db)):
    """Seed demo patients for scenarios 1–2."""
    # Scenario-ish: Ivanova — notified (endometrial polyp)
    r1 = je.create_journeys_from_protocol(
        db,
        patient_id="pat-ivanova",
        patient_name="Иванова Анна Петровна",
        clinical={"полип_эндометрия": 1, "study_us_pelvis": 1},
        pathology={
            "matched": [{"id": "pathology_полип_эндометрия", "label": "полип_эндометрия", "severity": "pathology"}]
        },
        source_route_id="seed-ivanova-polyp",
    )
    # Sidorova — BI-RADS 4 urgent path, already can book
    r2 = je.create_journeys_from_protocol(
        db,
        patient_id="pat-sidorova",
        patient_name="Сидорова Мария Константиновна",
        clinical={"BI_RADS_R": 4, "study_us_breast": 1},
        pathology={"matched": [{"id": "pathology_BI_RADS_R_ge_4", "label": "BI_RADS_R>=4", "severity": "pathology"}]},
        source_route_id="seed-sidorova-birads",
    )
    return {
        "ivanova": {
            "triggered": r1["triggered"],
            "journeys": [je.journey_to_dict(j, db, light=True) for j in r1.get("journeys") or []],
        },
        "sidorova": {
            "triggered": r2["triggered"],
            "journeys": [je.journey_to_dict(j, db, light=True) for j in r2.get("journeys") or []],
        },
    }
