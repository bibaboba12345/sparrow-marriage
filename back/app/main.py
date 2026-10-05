"""
Sparrow Route — FastAPI backend (SQLite).

Запуск:
  cd back
  source .venv/bin/activate
  uvicorn app.main:app --reload --port 8000
"""

import os

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, models, schemas  # noqa: F401
from .db import Base, engine, ensure_schema, get_db
from .extractors import ExtractError, StructureError, extract_bytes, llm_configured, structure_text
from .routing.journey_api import router as journey_router

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

Base.metadata.create_all(bind=engine)
ensure_schema()

# Default 100 MiB; override via MAX_UPLOAD_MB
MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024)

app = FastAPI(title="Sparrow Route API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(journey_router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "llm_configured": llm_configured(),
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


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
    max_mb = MAX_UPLOAD_BYTES // (1024 * 1024)

    # Early reject by Content-Length when client sends it
    cl = file.headers.get("content-length") if file.headers else None
    if cl:
        try:
            if int(cl) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл слишком большой (лимит {max_mb} МБ)",
                )
        except ValueError:
            pass

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой: {len(data) / (1024 * 1024):.1f} МБ (лимит {max_mb} МБ)",
        )
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
                "LLM structure skipped: нет AMVERACLOUD_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY в back/.env"
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
            detail="Нет LLM-ключа: AMVERACLOUD_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY в .env",
        )
    try:
        doc = structure_text(text, filename=payload.get("filename"))
    except StructureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return doc.model_dump()


@app.post("/api/v1/routes", response_model=schemas.RouteOut, status_code=201)
def create_route(payload: schemas.RouteCreate, db: Session = Depends(get_db)):
    """Создать route/протокол. Decider только при явном decision_json.force_decide."""
    data = payload
    force_decide = bool((payload.decision_json or {}).get("force_decide"))
    if force_decide and payload.documents:
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
    else:
        dj = dict(payload.decision_json or {})
        dj.pop("force_decide", None)
        if "decider_source" not in dj:
            dj["decider_source"] = "skipped"
        data = payload.model_copy(update={"decision_json": dj})
    route = crud.create_route(db, data)
    # Auto-create clinical journeys from pathology / clinical tokens
    dj = route.decision_json or {}
    clinical = dj.get("clinical_tokens") or dj.get("tokens") or {}
    pathology = dj.get("pathology") or {}
    journey_info = None
    if clinical or (pathology.get("matched") if isinstance(pathology, dict) else None):
        from .routing import journey_engine as je

        try:
            journey_info = je.create_journeys_from_protocol(
                db,
                patient_id=route.patient_id,
                patient_name=route.patient_name,
                clinical=clinical if isinstance(clinical, dict) else {},
                pathology=pathology if isinstance(pathology, dict) else {},
                source_route_id=route.id,
            )
            # attach summary onto decision_json for admin UI
            dj = dict(route.decision_json or {})
            dj["journey"] = {
                "triggered": journey_info.get("triggered"),
                "reason": journey_info.get("reason"),
                "matches": journey_info.get("matches") or [],
                "journey_ids": [j.id for j in journey_info.get("journeys") or []],
            }
            route.decision_json = dj
            db.add(route)
            db.commit()
            db.refresh(route)
        except Exception as exc:  # noqa: BLE001 — don't fail save
            import logging

            logging.getLogger(__name__).warning("journey auto-create failed: %s", exc)
    return route


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
    """Strict protocol tokenize: patient + catalog clinical tokens; rest → junk."""
    from .routing.protocol_tokenizer import (
        ProtocolTokenError,
        enrich_tokenize_result,
        non_null_token_list,
        tokenize_protocol_text,
        tokens_as_important,
    )

    text = (payload or {}).get("text") or ""
    if not str(text).strip():
        raise HTTPException(status_code=400, detail="text is required")
    filename = (payload or {}).get("filename")

    try:
        out = tokenize_protocol_text(text, filename=filename)
    except ProtocolTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    patient = out.patient
    enriched = enrich_tokenize_result(text, out)
    clinical = enriched["clinical"]
    nonzero = non_null_token_list(patient, clinical)
    important = tokens_as_important(patient, clinical)
    text_tokens = [f"{x['key']}={x['value']}" for x in nonzero]
    # Merge patient into tokens dict for UI convenience
    tokens_out = {**patient.model_dump(), **clinical}

    return {
        "patient": patient.model_dump(),
        "tokens": tokens_out,
        "clinical_tokens": clinical,
        "junk": out.junk,
        "text_tokens": text_tokens,
        "important": important,
        "active_features": [k for k, v in clinical.items() if v == 1 or v is True],
        "matched_phrases": [],
        "recommendation": enriched["recommendation"],
        "by_organ": enriched["by_organ"],
        "organs_present": enriched["organs_present"],
        "pathology": enriched["pathology"],
        "patient_alert": enriched.get("patient_alert"),
        "token_filter": {
            "source": out.source,
            "model": out.model,
            "dropped": [{"token": j, "reason": "junk"} for j in out.junk],
            "mode": "patient_plus_catalog",
            "catalog_hits": len(clinical),
        },
        "features_version": None,
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
    priority: str | None = Query(
        None,
        description="emergency | urgent | routine",
        pattern="^(emergency|urgent|routine)$",
    ),
    db: Session = Depends(get_db),
):
    """Admin-очередь с фильтрами: юзер, approved, срочность."""
    return crud.list_routes(
        db,
        patient_id=patient_id,
        approved=approved,
        priority=priority,
    )


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
