"""PDF text extraction: pdfplumber → pypdf fallback → optional OCR stub."""

from __future__ import annotations

import io
from typing import Any

from .clean import clean_text


class PdfExtractError(Exception):
    pass


def extract_pdf(data: bytes, *, filename: str = "document.pdf") -> dict[str, Any]:
    """
    Extract text from a PDF.

    Strategy:
      1. pdfplumber (tables + layout-aware text)
      2. pypdf fallback if almost empty
      3. OCR hook (optional) if still empty and deps available
    """
    if not data:
        raise PdfExtractError("Empty PDF")

    pages_text: list[str] = []
    engine = "pdfplumber"
    warnings: list[str] = []

    try:
        pages_text = _via_pdfplumber(data)
    except Exception as exc:  # noqa: BLE001 — fallback chain
        warnings.append(f"pdfplumber failed: {exc}")
        pages_text = []

    joined = "\n\n".join(p for p in pages_text if p.strip())
    if len(joined.strip()) < 40:
        try:
            alt = _via_pypdf(data)
            if len(alt.strip()) > len(joined.strip()):
                joined = alt
                engine = "pypdf"
                warnings.append("Used pypdf fallback (sparse pdfplumber output)")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"pypdf failed: {exc}")

    if len(joined.strip()) < 20:
        ocr_text, ocr_note = _try_ocr(data)
        if ocr_text.strip():
            joined = ocr_text
            engine = "ocr"
            warnings.append(ocr_note or "OCR used")
        else:
            warnings.append(ocr_note or "OCR unavailable / empty")

    text = clean_text(joined)
    if not text:
        raise PdfExtractError(
            f"Could not extract text from {filename}. "
            "Possibly a scanned PDF without OCR deps."
        )

    return {
        "filename": filename,
        "filetype": "pdf",
        "engine": engine,
        "page_count": max(len(pages_text), 1),
        "char_count": len(text),
        "text": text,
        "warnings": warnings,
    }


def _via_pdfplumber(data: bytes) -> list[str]:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            chunk = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            # tables as TSV append
            tables = page.extract_tables() or []
            table_bits: list[str] = []
            for table in tables:
                for row in table:
                    cells = [(c or "").strip() for c in row]
                    if any(cells):
                        table_bits.append("\t".join(cells))
            if table_bits:
                chunk = (chunk + "\n" + "\n".join(table_bits)).strip()
            pages.append(chunk)
    return pages


def _via_pypdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n\n".join(parts)


def _try_ocr(data: bytes) -> tuple[str, str]:
    """
    Optional OCR path. Requires pytesseract + pdf2image + system tesseract/poppler.
    Soft-fails if missing — fine for hackathon laptops without OCR stack.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        return "", "OCR skipped (install pytesseract + pdf2image for scanned PDFs)"

    try:
        images = convert_from_bytes(data, dpi=200)
        chunks = [pytesseract.image_to_string(img, lang="rus+eng") for img in images]
        return "\n\n".join(chunks), f"OCR pages={len(images)}"
    except Exception as exc:  # noqa: BLE001
        return "", f"OCR failed: {exc}"
