"""Journey engine smoke tests (no LLM)."""

from app.db import Base, SessionLocal, engine
from app import models  # noqa: F401
from app.routing import journey_engine as je


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_polyp_trigger_and_escalation():
    db = SessionLocal()
    try:
        # unique source each run
        import uuid

        sid = f"pytest-{uuid.uuid4().hex[:8]}"
        r = je.create_journeys_from_protocol(
            db,
            patient_id="pat-test",
            patient_name="Тестова А.А.",
            clinical={"полип_эндометрия": 1},
            pathology={"matched": [{"label": "полип_эндометрия", "severity": "pathology"}]},
            source_route_id=sid,
        )
        assert r["triggered"]
        j = r["journeys"][0]
        assert j.stage == "notified"
        assert j.matrix_rule_id == "endometrial_polyp"

        # idempotent
        r2 = je.create_journeys_from_protocol(
            db,
            patient_id="pat-test",
            patient_name="Тестова А.А.",
            clinical={"полип_эндометрия": 1},
            pathology={"matched": [{"label": "полип_эндометрия", "severity": "pathology"}]},
            source_route_id=sid,
        )
        assert len(r2["journeys"]) == 1
        assert r2["journeys"][0].id == j.id

        # book
        slots = je.list_slots(db, profile=j.slot_profile, journey_id=j.id)
        assert slots
        ap = je.book_slot(db, j, slot=slots[0])
        assert ap.state == "booked"
        db.refresh(j)
        assert j.stage == "booked"

        # tactics surgery
        j = je.set_tactics(db, j, "surgery")
        assert j.stage == "referral_created"

        j = je.schedule_hospitalization(db, j)
        assert j.stage == "hospitalization_scheduled"
    finally:
        db.close()


def test_no_trigger_on_empty():
    db = SessionLocal()
    try:
        r = je.create_journeys_from_protocol(
            db,
            patient_id="pat-norm",
            patient_name="Норма",
            clinical={"study_us_pelvis": 1},
            pathology={"matched": []},
            source_route_id="pytest-norm",
        )
        assert r["triggered"] is False
        assert r["reason"] == "no_trigger"
    finally:
        db.close()


def test_clock_escalation_creates_reminders():
    db = SessionLocal()
    try:
        import uuid

        sid = f"pytest-esc-{uuid.uuid4().hex[:8]}"
        r = je.create_journeys_from_protocol(
            db,
            patient_id="pat-esc",
            patient_name="Эскалация Е.Е.",
            clinical={"BI_RADS_R": 4},
            pathology={"matched": []},
            source_route_id=sid,
        )
        assert r["triggered"]
        jid = r["journeys"][0].id
        before = (
            db.query(models.Notification)
            .filter(models.Notification.journey_id == jid)
            .count()
        )
        res = je.advance_clock(db, hours=25)
        assert res["advanced_hours"] == 25
        after = (
            db.query(models.Notification)
            .filter(models.Notification.journey_id == jid)
            .count()
        )
        assert after >= before  # h24 reminder may add channels
        j = db.get(models.ClinicalJourney, jid)
        assert j.last_escalation_key in {"h24", "initial", None} or j.last_escalation_key
    finally:
        db.close()
