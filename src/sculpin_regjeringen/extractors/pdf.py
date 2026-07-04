"""PDF extraction scaffold."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PdfTextBlock(BaseModel):
    block_id: str
    text: str
    bbox: tuple[float, float, float, float] | None = None


class PdfPageText(BaseModel):
    document_id: str
    attachment_id: str
    page_number: int
    text: str
    blocks: list[PdfTextBlock] = Field(default_factory=list)
    extraction_method: str = "pymupdf"
    confidence: float | None = None


class PdfExtractor:
    def extract(self, path: str, *, document_id: str, attachment_id: str) -> list[PdfPageText]:
        raise NotImplementedError("PDF extraction will be implemented in Phase 3.")
