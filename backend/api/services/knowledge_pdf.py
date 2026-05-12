from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


class KnowledgePdfError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPdfText:
    text: str
    pages: list[dict[str, object]]


def extract_pdf_text(pdf_bytes: bytes) -> ExtractedPdfText:
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        raise KnowledgePdfError("PDF file content is empty.")
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:
        raise KnowledgePdfError("PDF file could not be parsed.") from exc

    try:
        pages: list[dict[str, object]] = []
        for index, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            text = _normalize_text(raw_text)
            if text:
                pages.append({"page": index, "text": text})
    except Exception as exc:
        raise KnowledgePdfError("PDF file could not be parsed.") from exc

    combined = "\n\n".join(str(page["text"]) for page in pages).strip()
    if not combined:
        raise KnowledgePdfError("No readable text was found in this PDF.")
    return ExtractedPdfText(text=combined, pages=pages)


def _normalize_text(value: str) -> str:
    return "\n".join(line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip())
