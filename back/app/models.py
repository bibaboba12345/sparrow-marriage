import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .db import Base


def new_id(prefix: str = "rt") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class RouteRecord(Base):
    """Одна попытка маршрутизации: сырой ввод + полный decision/reasoning."""

    __tablename__ = "route_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)

    # пациент / клиент
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    patient_name: Mapped[str] = mapped_column(String(256))
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # raw input (legacy aggregate + per-document structure)
    raw_input: Mapped[str] = mapped_column(Text, default="")
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    documents: Mapped[list] = mapped_column(JSON, default=list)
    # documents[]: {id, filename, filetype, raw_text, important, metadata_junk, summary, ...}

    # decision
    priority: Mapped[str] = mapped_column(String(32), default="routine")
    department: Mapped[str] = mapped_column(String(256), default="")
    specialists: Mapped[list] = mapped_column(JSON, default=list)
    required_tests: Mapped[list] = mapped_column(JSON, default=list)

    reasoning: Mapped[list] = mapped_column(JSON, default=list)
    decision_json: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(32), default="pending_review")
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ClinicalJourney(Base):
    """Клинический хирургический маршрут пациента (воронка)."""

    __tablename__ = "clinical_journeys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("jn"))
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    patient_name: Mapped[str] = mapped_column(String(256), default="")
    trigger_pathology: Mapped[str] = mapped_column(String(256))
    source_study: Mapped[str] = mapped_column(String(256), default="")
    source_route_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(64), default="detected", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    clinic: Mapped[str] = mapped_column(String(256), default="")
    coordinator: Mapped[str] = mapped_column(String(256), default="")
    specialty: Mapped[str] = mapped_column(String(128), default="")
    slot_profile: Mapped[str] = mapped_column(String(64), default="")
    target_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    matrix_rule_id: Mapped[str] = mapped_column(String(128), default="")
    matrix_version: Mapped[str] = mapped_column(String(32), default="1")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    tactics: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hospitalization_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_escalation_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class JourneyEvent(Base):
    __tablename__ = "journey_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ev"))
    journey_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ap"))
    journey_id: Mapped[str] = mapped_column(String(32), index=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    modality: Mapped[str] = mapped_column(String(32), default="in_person")  # in_person|online
    location: Mapped[str] = mapped_column(String(256), default="")
    doctor: Mapped[str] = mapped_column(String(256), default="")
    specialty: Mapped[str] = mapped_column(String(128), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    state: Mapped[str] = mapped_column(String(32), default="booked", index=True)
    kind: Mapped[str] = mapped_column(String(32), default="consult")  # consult|control
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("nt"))
    journey_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="cabinet")  # cabinet|push|sms|call_task
    title: Mapped[str] = mapped_column(String(256), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(32), default="info")  # info|month|urgent
    escalation_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoordinatorTask(Base):
    __tablename__ = "coordinator_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("tk"))
    journey_id: Mapped[str] = mapped_column(String(32), index=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    script: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(32), default="open", index=True)  # open|done
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelClock(Base):
    """Singleton row id='default': model time = real_utcnow + offset_seconds."""

    __tablename__ = "model_clock"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    offset_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessedMisEvent(Base):
    """Idempotency store for MIS webhook event_id."""

    __tablename__ = "processed_mis_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), default="")
    journey_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
