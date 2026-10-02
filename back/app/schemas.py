from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_doc_id() -> str:
    return f"doc-{uuid4().hex[:10]}"


class LabToken(BaseModel):
    name: str
    value: str
    unit: str | None = None
    ref_range: str | None = None


class ImportantTokens(BaseModel):
    patient_name: str | None = None
    age: int | None = None
    sex: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    labs: list[LabToken] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    vitals: dict[str, str] = Field(default_factory=dict)
    red_flags: list[str] = Field(default_factory=list)
    clinical_snippets: list[str] = Field(default_factory=list)


class MetadataJunk(BaseModel):
    headers_footers: list[str] = Field(default_factory=list)
    clinic_meta: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    legalese: list[str] = Field(default_factory=list)
    other_noise: list[str] = Field(default_factory=list)


class RouteDocument(BaseModel):
    """Один файл/текст внутри extract + LLM structure."""

    id: str = Field(default_factory=new_doc_id)
    filename: str = "document"
    filetype: str = "text"
    raw_text: str = ""
    important: ImportantTokens = Field(default_factory=ImportantTokens)
    metadata_junk: MetadataJunk = Field(default_factory=MetadataJunk)
    summary: str = ""
    structure_model: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RouteCreate(BaseModel):
    patient_id: str = Field(..., examples=["pat-kozlov"])
    patient_name: str = Field(..., examples=["Козлов И.Н."])
    age: int | None = None
    documents: list[RouteDocument] = Field(default_factory=list)
    # legacy / aggregated (заполняются из documents, если пусто)
    raw_input: str = ""
    source_file: str | None = None
    priority: str = "routine"
    department: str = ""
    specialists: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    decision_json: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending_review"
    approved: bool = False

    @model_validator(mode="after")
    def sync_documents(self) -> "RouteCreate":
        if self.documents:
            texts = [d.raw_text for d in self.documents if d.raw_text]
            if not self.raw_input and texts:
                self.raw_input = "\n\n---\n\n".join(texts)
            if not self.source_file:
                names = [d.filename for d in self.documents if d.filename]
                self.source_file = ", ".join(names) if names else None
        elif self.raw_input.strip():
            self.documents = [
                RouteDocument(
                    filename=self.source_file or "text_input",
                    filetype="text",
                    raw_text=self.raw_input,
                )
            ]
            self.source_file = self.documents[0].filename
        return self


class RouteUpdate(BaseModel):
    patient_name: str | None = None
    age: int | None = None
    documents: list[RouteDocument] | None = None
    raw_input: str | None = None
    source_file: str | None = None
    priority: str | None = None
    department: str | None = None
    specialists: list[str] | None = None
    required_tests: list[str] | None = None
    reasoning: list[str] | None = None
    decision_json: dict[str, Any] | None = None
    status: str | None = None
    approved: bool | None = None


class RouteOut(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    age: int | None
    documents: list[RouteDocument] = Field(default_factory=list)
    raw_input: str = ""
    source_file: str | None = None
    priority: str
    department: str
    specialists: list[str]
    required_tests: list[str]
    reasoning: list[str]
    decision_json: dict[str, Any]
    status: str
    approved: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def legacy_documents(self) -> "RouteOut":
        if not self.documents and self.raw_input:
            self.documents = [
                RouteDocument(
                    id="legacy",
                    filename=self.source_file or "raw_input",
                    filetype="text",
                    raw_text=self.raw_input,
                )
            ]
        return self


class PatientOut(BaseModel):
    patient_id: str
    patient_name: str


class ExtractOut(BaseModel):
    filename: str
    filetype: str
    engine: str
    page_count: int | None = None
    char_count: int
    text: str
    warnings: list[str] = Field(default_factory=list)
    structured: dict[str, Any] | None = None
    structure_model: str | None = None
    # удобный готовый документ для клиентской очереди
    document: RouteDocument | None = None
