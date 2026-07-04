"""PostgreSQL metadata storage placeholder."""

from __future__ import annotations

MINIMUM_TABLES = (
    "documents",
    "document_versions",
    "attachments",
    "document_sections",
    "field_provenance",
    "crawl_batches",
    "fetch_events",
    "extraction_runs",
    "parser_errors",
)


class PostgresMetadataStore:
    def upsert_document(self, document: object) -> None:
        raise NotImplementedError("Metadata persistence will be implemented after model fixtures.")
