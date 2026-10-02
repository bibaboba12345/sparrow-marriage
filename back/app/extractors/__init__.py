"""Document extractors facade: PDF / DOCX / plain text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .clean import clean_text
from .llm_structurer import StructureError, llm_configured, structure_text
from .pdf_extractor import PdfExtractError, extract_pdf
from .structure_schema import StructuredDocument
from .word_extractor import WordExtractError, extract_docx

__all__ = [
    "ExtractError",
    "StructureError",
    "StructuredDocument",
    "extract_bytes",
    "extract_pdf",
    "extract_docx",
    "clean_text",
    "structure_text",
    "llm_configured",
]


class ExtractError(Exception):
    pass


_PDF = {".pdf"}
_WORD = {".docx"}  # .doc rejected inside word_extractor
_TEXT = {".txt", ".md", ".csv"}


def extract_bytes(data: bytes, filename: str) -> dict[str, Any]:
    """Dispatch by extension / content sniffing."""
    suffix = Path(filename or "file.bin").suffix.lower()

    try:
        if suffix in _PDF or _looks_like_pdf(data):
            return extract_pdf(data, filename=filename)
        if suffix in _WORD or suffix == ".doc":
            return extract_docx(data, filename=filename)
        if suffix in _TEXT or _looks_like_text(data):
            text = clean_text(data.decode("utf-8", errors="replace"))
            return {
                "filename": filename,
                "filetype": "text",
                "engine": "utf-8",
                "page_count": None,
                "char_count": len(text),
                "text": text,
                "warnings": [],
            }
    except (PdfExtractError, WordExtractError) as exc:
        raise ExtractError(str(exc)) from exc

    raise ExtractError(
        f"Unsupported file type «{suffix or 'unknown'}». "
        "Use PDF, DOCX or TXT."
    )


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:2048]
    if b"\x00" in sample:
        return False
    # high ratio of printable-ish bytes
    printable = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b <= 126 or b >= 192)
    return printable / max(len(sample), 1) > 0.85
