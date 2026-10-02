import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
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
