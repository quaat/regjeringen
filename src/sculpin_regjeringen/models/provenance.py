"""Field-level provenance models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ExtractionMethod = Literal["html_selector", "regex", "pdf_text", "docx_text", "llm", "manual"]


class FieldProvenance(BaseModel):
    field_path: str
    value_hash: str
    extraction_method: ExtractionMethod
    source_artifact_uri: str
    source_url: str
    css_selector: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    quote: str | None = None
    extractor_version: str
    extracted_at: datetime
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
