from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import RouteRecord, new_id
from .schemas import RouteCreate, RouteDocument, RouteUpdate

DEMO = [
    RouteCreate(
        patient_id="pat-kozlov",
        patient_name="Козлов И.Н.",
        age=54,
        documents=[
            RouteDocument(
                filename="epicrisis_kozlov.pdf",
                filetype="pdf",
                raw_text=(
                    "Боль за грудиной > 30 мин, иррадиация в левую руку.\n"
                    "TnI 1.8 нг/мл. ЭКГ: элевация ST."
                ),
                important={
                    "patient_name": "Козлов И.Н.",
                    "age": 54,
                    "symptoms": ["боль за грудиной", "иррадиация в левую руку"],
                    "diagnoses": ["ОКС / STEMI"],
                    "labs": [
                        {
                            "name": "TnI",
                            "value": "1.8",
                            "unit": "нг/мл",
                            "ref_range": None,
                        }
                    ],
                    "red_flags": ["элевация ST", "STEMI"],
                    "clinical_snippets": [
                        "Боль за грудиной > 30 мин",
                        "TnI 1.8 нг/мл",
                    ],
                },
                metadata_junk={
                    "headers_footers": ["Стр. 1 из 2"],
                    "clinic_meta": ["ГБУЗ ГКБ"],
                },
                summary="Острый коронарный синдром с элевацией ST и высоким тропонином.",
            ),
            RouteDocument(
                filename="labs_kozlov.pdf",
                filetype="pdf",
                raw_text="Д-димер 0.9. ОАК без лейкоцитоза.",
                important={
                    "labs": [
                        {"name": "Д-димер", "value": "0.9", "unit": None, "ref_range": None},
                    ],
                    "clinical_snippets": ["Д-димер 0.9"],
                },
                summary="Доп. лабораторные маркеры.",
            ),
        ],
        priority="emergency",
        department="Кардиология / ОРИТ",
        specialists=["Кардиолог", "Реаниматолог"],
        required_tests=["Тропонин I", "ЭКГ", "Д-димер"],
        reasoning=[
            "Боль за грудиной > 30 мин, иррадиация в левую руку",
            "Тропонин повышен (цитата: «TnI 1.8 нг/мл»)",
            "Протокол ACS / STEMI — экстренная маршрутизация",
        ],
        decision_json={"protocol": "ACS/STEMI", "confidence": 0.91},
        status="pending_review",
        approved=False,
    ),
    RouteCreate(
        patient_id="pat-morozova",
        patient_name="Морозова Е.В.",
        age=31,
        documents=[
            RouteDocument(
                filename="labs_morozova.pdf",
                filetype="pdf",
                raw_text="Лихорадка 38.7°C 4 дня, кашель с мокротой. СРБ 48 мг/л.",
                important={
                    "patient_name": "Морозова Е.В.",
                    "age": 31,
                    "symptoms": ["лихорадка", "кашель с мокротой"],
                    "labs": [
                        {"name": "СРБ", "value": "48", "unit": "мг/л", "ref_range": None}
                    ],
                    "vitals": {"Temp": "38.7"},
                    "red_flags": [],
                    "clinical_snippets": ["Лихорадка 38.7°C 4 дня", "СРБ 48 мг/л"],
                },
                summary="Подозрение на внебольничную пневмонию.",
            )
        ],
        priority="urgent",
        department="Терапия",
        specialists=["Терапевт", "Пульмонолог"],
        required_tests=["ОАК", "СРБ", "Рентген ОГК"],
        reasoning=[
            "Лихорадка 38.7°C 4 дня, кашель с мокротой",
            "СРБ 48 мг/л",
            "Гайдлайн: внебольничная пневмония — срочный приём",
        ],
        decision_json={"protocol": "CAP", "confidence": 0.84},
        status="approved",
        approved=True,
    ),
    RouteCreate(
        patient_id="pat-smirnov",
        patient_name="Смирнов Д.А.",
        age=67,
        documents=[
            RouteDocument(
                filename="manual_input",
                filetype="text",
                raw_text="HbA1c 7.2%, глюкоза натощак 6.8. Жалоб на острые состояния нет.",
                important={
                    "patient_name": "Смирнов Д.А.",
                    "age": 67,
                    "labs": [
                        {"name": "HbA1c", "value": "7.2", "unit": "%", "ref_range": None},
                        {
                            "name": "Глюкоза натощак",
                            "value": "6.8",
                            "unit": None,
                            "ref_range": None,
                        },
                    ],
                    "diagnoses": ["СД 2 типа"],
                },
                summary="Плановый контроль компенсации диабета.",
            )
        ],
        priority="routine",
        department="Эндокринология",
        specialists=["Эндокринолог"],
        required_tests=["HbA1c", "Глюкоза натощак"],
        reasoning=[
            "HbA1c 7.2%, стабильная компенсация",
            "Нет острых осложнений",
            "Плановый контроль по протоколу СД 2 типа",
        ],
        decision_json={"protocol": "T2DM-followup", "confidence": 0.77},
        status="edited",
        approved=False,
    ),
]


def create_route(db: Session, payload: RouteCreate) -> RouteRecord:
    data = payload.model_dump()
    data.setdefault("approved", False)
    data.setdefault("documents", [])
    if not data.get("approved"):
        data["status"] = data.get("status") or "pending_review"
    row = RouteRecord(id=new_id(), **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_route(db: Session, route_id: str) -> RouteRecord | None:
    return db.get(RouteRecord, route_id)


def list_routes(
    db: Session,
    *,
    patient_id: str | None = None,
    approved: bool | None = None,
) -> list[RouteRecord]:
    stmt = select(RouteRecord)
    if patient_id:
        stmt = stmt.where(RouteRecord.patient_id == patient_id)
    if approved is not None:
        stmt = stmt.where(RouteRecord.approved.is_(approved))
    stmt = stmt.order_by(RouteRecord.created_at.desc())
    return list(db.scalars(stmt).all())


def get_all_routes(db: Session) -> list[RouteRecord]:
    return list_routes(db)


def get_routes_by_patient(db: Session, patient_id: str) -> list[RouteRecord]:
    return list_routes(db, patient_id=patient_id)


def list_patients(db: Session) -> list[dict]:
    rows = list_routes(db)
    seen: dict[str, str] = {}
    for r in rows:
        if r.patient_id not in seen:
            seen[r.patient_id] = r.patient_name
    return [{"patient_id": pid, "patient_name": name} for pid, name in sorted(seen.items())]


def update_route(db: Session, route_id: str, payload: RouteUpdate) -> RouteRecord | None:
    row = get_route(db, route_id)
    if not row:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "documents" in data and data["documents"] is not None:
        docs = data["documents"]
        texts = [d.get("raw_text", "") for d in docs if d.get("raw_text")]
        data["raw_input"] = "\n\n---\n\n".join(texts)
        names = [d.get("filename") for d in docs if d.get("filename")]
        data["source_file"] = ", ".join(names) if names else None
    for key, value in data.items():
        setattr(row, key, value)
    if "approved" in data and data["approved"] is True:
        row.status = "approved"
    elif "status" not in data and data and "approved" not in data:
        row.status = "edited"
        row.approved = False
    db.commit()
    db.refresh(row)
    return row


def approve_route(db: Session, route_id: str) -> RouteRecord | None:
    row = get_route(db, route_id)
    if not row:
        return None
    row.approved = True
    row.status = "approved"
    db.commit()
    db.refresh(row)
    return row


def delete_route(db: Session, route_id: str) -> bool:
    row = get_route(db, route_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def seed_demo(db: Session) -> list[RouteRecord]:
    existing = get_all_routes(db)
    if existing:
        return existing
    return [create_route(db, item) for item in DEMO]
