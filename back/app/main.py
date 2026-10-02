"""
Sparrow Route — FastAPI backend (SQLite).

Запуск:
  cd back
  source .venv/bin/activate
  uvicorn app.main:app --reload --port 8000
"""

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, models, schemas  # noqa: F401
from .db import Base, engine, ensure_schema, get_db
from .extractors import ExtractError, StructureError, extract_bytes, llm_configured, structure_text

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="Sparrow Route API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "llm_configured": llm_configured()}


@app.post("/api/v1/upload", response_model=schemas.ExtractOut)
async def upload_document(
    file: UploadFile = File(...),
    structure: bool = Query(
        True,
        description="Прогнать текст через DeepSeek → important + metadata_junk JSON",
    ),
):
    """Извлечь текст из PDF / DOCX / TXT (+ опционально LLM-структуризация)."""
    filename = file.filename or "upload.bin"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        result = extract_bytes(data, filename)
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    warnings = list(result.get("warnings") or [])
    structured = None
    structure_model = None

    if structure:
        if not llm_configured():
            warnings.append(
                "LLM structure skipped: нет OPENROUTER_API_KEY / DEEPSEEK_API_KEY в back/.env"
            )
        else:
            try:
                structured_doc = structure_text(result["text"], filename=filename)
                structured = structured_doc.model_dump(exclude={"model", "raw_char_count"})
                structure_model = structured_doc.model
            except StructureError as exc:
                warnings.append(f"LLM structure failed: {exc}")

    important = (structured or {}).get("important") or {}
    metadata_junk = (structured or {}).get("metadata_junk") or {}
    summary = (structured or {}).get("summary") or ""

    document = schemas.RouteDocument(
        filename=filename,
        filetype=result.get("filetype") or "text",
        raw_text=result.get("text") or "",
        important=important,
        metadata_junk=metadata_junk,
        summary=summary,
        structure_model=structure_model,
        warnings=warnings,
    )

    return {
        **result,
        "warnings": warnings,
        "structured": structured,
        "structure_model": structure_model,
        "document": document,
    }


@app.post("/api/v1/structure", response_model=dict)
def structure_raw(
    payload: dict,
):
    """Структурировать уже готовый текст (без файла). Body: {\"text\": \"...\"}."""
    text = (payload or {}).get("text") or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="Нет LLM-ключа: OPENROUTER_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY в .env",
        )
    try:
        doc = structure_text(text, filename=payload.get("filename"))
    except StructureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return doc.model_dump()


@app.post("/api/v1/routes", response_model=schemas.RouteOut, status_code=201)
def create_route(payload: schemas.RouteCreate, db: Session = Depends(get_db)):
    """Создать route; если routing-поля пустые — Decider (vector match + LLM)."""
    data = payload
    needs_decide = (
        not (payload.department or "").strip()
        or not (payload.reasoning or [])
        or (payload.decision_json or {}).get("force_decide")
    )
    if needs_decide and payload.documents:
        from .routing.decider import decide_from_documents

        decision = decide_from_documents(payload.documents, raw_input=payload.raw_input)
        dj = decision.get("decision_json") or {}
        if isinstance(dj, dict):
            dj = {k: v for k, v in dj.items() if k != "routing"}
        data = payload.model_copy(
            update={
                "priority": decision["priority"],
                "department": decision["department"],
                "specialists": decision["specialists"],
                "required_tests": decision["required_tests"],
                "reasoning": decision["reasoning"],
                "decision_json": dj,
                "status": payload.status or "pending_review",
                "approved": False,
            }
        )
    return crud.create_route(db, data)


@app.get("/api/v1/routing/features")
def routing_features():
    from .routing import features as feat

    return {
        "version": feat.catalog_version(),
        "dim": feat.feature_dim(),
        "features": feat.feature_meta(),
    }


@app.post("/api/v1/routing/tokenize")
def routing_tokenize(payload: dict):
    """Split text → LLM deviation filter → symptoms / features (без match/decider)."""
    from .routing.token_normalizer import collect_text_tokens, normalize_tokens
    from .routing.vectorize import split_complaint_tokens, vectorize_important

    text = (payload or {}).get("text") or ""
    if not str(text).strip():
        raise HTTPException(status_code=400, detail="text is required")
    use_llm = bool((payload or {}).get("normalize", True))

    tokens = collect_text_tokens(extra_text=text)
    if not tokens:
        tokens = split_complaint_tokens(text)

    norm = None
    if use_llm and tokens:
        norm = normalize_tokens(tokens, context=text)

    if norm and norm.get("source") == "llm":
        important = {
            "symptoms": list(norm.get("symptoms") or []),
            "red_flags": list(norm.get("red_flags") or []),
            "diagnoses": [],
            "labs": [],
            "medications": [],
            "vitals": {},
            "clinical_snippets": [],
        }
        vec = vectorize_important(
            {**important, "free_text": [text]},
            alias_free_text=False,
            seed_active=norm.get("active_features") or [],
        )
        return {
            "text_tokens": norm.get("text_tokens") or tokens,
            "important": important,
            "active_features": vec["active_features"],
            "matched_phrases": vec.get("matched_phrases") or [],
            "token_filter": {
                "source": norm.get("source"),
                "model": norm.get("model"),
                "dropped": norm.get("dropped") or [],
                "symptoms": norm.get("symptoms") or [],
                "red_flags": norm.get("red_flags") or [],
            },
            "features_version": vec["features_version"],
        }

    # Heuristic split + alias (нет ключа / ошибка LLM)
    vec = vectorize_important({"text": text, "free_text": [text]})
    return {
        "text_tokens": vec.get("text_tokens") or tokens,
        "important": {
            "symptoms": list(vec.get("text_tokens") or tokens),
            "red_flags": [],
            "diagnoses": [],
            "labs": [],
            "medications": [],
            "vitals": vec.get("parsed_vitals") or {},
            "clinical_snippets": [],
        },
        "active_features": vec["active_features"],
        "matched_phrases": vec.get("matched_phrases") or [],
        "token_filter": {
            "source": (norm or {}).get("source") or "heuristic",
            "model": (norm or {}).get("model"),
            "dropped": (norm or {}).get("dropped") or [],
            "symptoms": [],
            "red_flags": [],
        },
        "features_version": vec["features_version"],
    }


@app.post("/api/v1/routing/match")
def routing_match(payload: dict):
    """Vectorize + nearest case. Body: documents | important | text. Optional normalize=true (LLM)."""
    from .routing.decider import _vectorize_with_token_llm, match_only_from_documents
    from .routing.matcher import match_vector

    use_llm = bool(payload.get("normalize", True))
    if payload.get("text") and not payload.get("documents") and not payload.get("important"):
        vec = _vectorize_with_token_llm(
            None,
            raw_input=payload["text"],
            use_llm_filter=use_llm,
        )
        m = match_vector(vec["vector"], vec["active_features"])
        return {**vec, "match": m.to_dict()}
    if payload.get("documents"):
        return match_only_from_documents(
            payload["documents"],
            extra_text=payload.get("text") or payload.get("raw_input") or "",
            use_llm_filter=use_llm,
        )
    if payload.get("important"):
        vec = _vectorize_with_token_llm(
            None,
            raw_input=payload.get("text") or "",
            important=payload["important"],
            use_llm_filter=use_llm,
        )
        m = match_vector(vec["vector"], vec["active_features"])
        return {**vec, "match": m.to_dict()}
    raise HTTPException(status_code=400, detail="documents, important, or text required")


@app.get("/api/v1/routes", response_model=list[schemas.RouteOut])
def list_routes(
    patient_id: str | None = Query(None, description="Фильтр по patient_id"),
    approved: bool | None = Query(None, description="true / false / omit"),
    db: Session = Depends(get_db),
):
    """Admin-очередь с фильтрами: по юзеру и approved."""
    return crud.list_routes(db, patient_id=patient_id, approved=approved)


@app.get("/api/v1/patients", response_model=list[schemas.PatientOut])
def list_patients(db: Session = Depends(get_db)):
    """Уникальные пациенты из route-записей — для фильтра на admin."""
    return crud.list_patients(db)


@app.get("/api/v1/routes/{route_id}", response_model=schemas.RouteOut)
def get_route(route_id: str, db: Session = Depends(get_db)):
    row = crud.get_route(db, route_id)
    if not row:
        raise HTTPException(status_code=404, detail="Route not found")
    return row


@app.get("/api/v1/patients/{patient_id}/routes", response_model=list[schemas.RouteOut])
def list_patient_routes(
    patient_id: str,
    approved: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    return crud.list_routes(db, patient_id=patient_id, approved=approved)


@app.patch("/api/v1/routes/{route_id}", response_model=schemas.RouteOut)
def update_route(
    route_id: str,
    payload: schemas.RouteUpdate,
    db: Session = Depends(get_db),
):
    row = crud.update_route(db, route_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="Route not found")
    return row


@app.post("/api/v1/routes/{route_id}/approve", response_model=schemas.RouteOut)
def approve_route(route_id: str, db: Session = Depends(get_db)):
    row = crud.approve_route(db, route_id)
    if not row:
        raise HTTPException(status_code=404, detail="Route not found")
    return row


@app.delete("/api/v1/routes/{route_id}", status_code=204)
def delete_route(route_id: str, db: Session = Depends(get_db)):
    if not crud.delete_route(db, route_id):
        raise HTTPException(status_code=404, detail="Route not found")
    return None


@app.post("/api/v1/seed", response_model=list[schemas.RouteOut])
def seed(db: Session = Depends(get_db)):
    return crud.seed_demo(db)
