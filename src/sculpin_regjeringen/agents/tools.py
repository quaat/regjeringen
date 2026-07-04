"""Sculpin tool surface scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class GovernmentDocumentSearchFilters:
    department: str | None = None
    status: str | None = None
    deadline_from: date | None = None
    deadline_to: date | None = None
    theme: str | None = None


class GovernmentDocumentTools:
    def search_government_documents(self, filters: GovernmentDocumentSearchFilters) -> list[object]:
        raise NotImplementedError("Search requires populated metadata and index storage.")

    def get_government_document(self, document_id: str) -> object:
        raise NotImplementedError("Document retrieval requires metadata storage.")

    def get_document_sections(self, document_id: str) -> list[object]:
        raise NotImplementedError("Section retrieval requires extracted text storage.")

    def get_document_attachments(self, document_id: str) -> list[object]:
        raise NotImplementedError("Attachment retrieval requires metadata storage.")

    def query_government_kg(self, sparql: str) -> object:
        raise NotImplementedError("KG queries require a configured Sculpin graph backend.")
