"""Pydantic-модель структурированного документа после LLM-разбора."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class LabValue(BaseModel):
    name: str = Field(..., description="Название показателя, напр. Тропонин I")
    value: str = Field(..., description="Значение как в тексте")
    unit: str | None = Field(None, description="Единица измерения")
    ref_range: str | None = Field(None, description="Референс, если есть")

    @field_validator("value", mode="before")
    @classmethod
    def value_as_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class ImportantTokens(BaseModel):
    """Клинически значимые токены — то, что нужно Decider/RAG."""

    patient_name: str | None = None
    age: int | None = None
    sex: str | None = Field(None, description="м/ж или male/female, если явно")
    symptoms: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    labs: list[LabValue] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    vitals: dict[str, str] = Field(
        default_factory=dict,
        description="напр. {\"BP\": \"140/90\", \"HR\": \"98\", \"Temp\": \"38.7\"}",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Критические маркеры: боль за грудиной, кровотечение, SpO2↓…",
    )
    clinical_snippets: list[str] = Field(
        default_factory=list,
        description="Короткие цитаты из текста, важные для маршрутизации",
    )


class MetadataJunk(BaseModel):
    """Мусор / метаданные документа — не для клинического решения."""

    headers_footers: list[str] = Field(default_factory=list)
    clinic_meta: list[str] = Field(
        default_factory=list,
        description="Клиника, адрес, телефон, ИНН, печати, QR",
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description="Номера историй, штрихкоды, UUID форм",
    )
    legalese: list[str] = Field(default_factory=list)
    other_noise: list[str] = Field(default_factory=list)


class StructuredDocument(BaseModel):
    important: ImportantTokens
    metadata_junk: MetadataJunk
    summary: str = Field(
        "",
        description="1–3 предложения: суть выписки для маршрутизации",
    )
    model: str | None = Field(None, description="Какая LLM собрала JSON")
    raw_char_count: int | None = None

    def to_prompt_blob(self) -> str:
        """Компактный текст для последующего Decider LLM."""
        return self.model_dump_json(exclude={"model", "raw_char_count"}, ensure_ascii=False)


def schema_hint() -> dict[str, Any]:
    return StructuredDocument.model_json_schema()
