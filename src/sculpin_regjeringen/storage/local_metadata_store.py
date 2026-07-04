"""Local JSON metadata persistence for fixture workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel

from sculpin_regjeringen.crawler.attachment_downloader import AttachmentDownloadManifest
from sculpin_regjeringen.models.canonical import HearingDocument

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
    "attachment_download_events",
)


class MetadataUpsertResult(BaseModel):
    document_id: str
    version_id: str
    inserted_document: bool
    inserted_version: bool
    document_count: int
    version_count: int


class MetadataStore(Protocol):
    def upsert_hearing_document(
        self,
        document: HearingDocument,
        *,
        html_checksum_sha256: str,
        parser_version: str,
        source_artifact_uri: str,
        processed_at: str,
        attachment_downloads: AttachmentDownloadManifest | None = None,
    ) -> MetadataUpsertResult:
        """Persist parsed hearing metadata idempotently."""


@dataclass(slots=True)
class LocalJsonMetadataStore(MetadataStore):
    """Small JSON-backed metadata repository for local tests and fixture workflows."""

    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._empty_state())

    def upsert_hearing_document(
        self,
        document: HearingDocument,
        *,
        html_checksum_sha256: str,
        parser_version: str,
        source_artifact_uri: str,
        processed_at: str,
        attachment_downloads: AttachmentDownloadManifest | None = None,
    ) -> MetadataUpsertResult:
        state = self._read()
        documents = state["documents"]
        inserted_document = document.document_id not in documents
        documents[document.document_id] = {
            "document_id": document.document_id,
            "document_type": document.document_type,
            "title": document.title,
            "canonical_url": document.canonical_url,
            "language": document.language,
            "source_artifact_uri": source_artifact_uri,
            "updated_at": processed_at,
        }

        version_id = f"{document.document_id}:{html_checksum_sha256}:{parser_version}"
        versions = state["document_versions"]
        inserted_version = version_id not in versions
        versions[version_id] = {
            "version_id": version_id,
            "document_id": document.document_id,
            "html_checksum_sha256": html_checksum_sha256,
            "parser_version": parser_version,
            "processed_at": processed_at,
        }

        state["attachments"] = {
            key: value
            for key, value in state["attachments"].items()
            if value["document_id"] != document.document_id
        }
        for attachment in document.attachments:
            state["attachments"][attachment.attachment_id] = attachment.model_dump(mode="json")

        state["document_sections"] = {
            key: value
            for key, value in state["document_sections"].items()
            if value["document_id"] != document.document_id
        }
        for section in document.sections:
            state["document_sections"][f"{document.document_id}:{section.section_id}"] = {
                "document_id": document.document_id,
                **section.model_dump(mode="json"),
            }

        state["field_provenance"] = {
            key: value
            for key, value in state["field_provenance"].items()
            if value["document_id"] != document.document_id
        }
        for index, provenance in enumerate(document.provenance):
            state["field_provenance"][f"{document.document_id}:{index}:{provenance.field_path}"] = {
                "document_id": document.document_id,
                **provenance.model_dump(mode="json"),
            }

        if attachment_downloads is not None:
            state.setdefault("attachment_download_events", {})
            state["attachment_download_events"] = {
                key: value
                for key, value in state["attachment_download_events"].items()
                if value["document_id"] != document.document_id
            }
            for index, result in enumerate(attachment_downloads.results):
                state["attachment_download_events"][
                    f"{version_id}:{index}:{result.attachment_id}"
                ] = {
                    "document_id": document.document_id,
                    "version_id": version_id,
                    **result.model_dump(mode="json"),
                }

        state["extraction_runs"][version_id] = {
            "document_id": document.document_id,
            "version_id": version_id,
            "parser_version": parser_version,
            "processed_at": processed_at,
        }
        self._write(state)
        return MetadataUpsertResult(
            document_id=document.document_id,
            version_id=version_id,
            inserted_document=inserted_document,
            inserted_version=inserted_version,
            document_count=len(state["documents"]),
            version_count=len(state["document_versions"]),
        )

    def count(self, table: str) -> int:
        return len(self._read()[table])

    def _read(self) -> dict[str, dict[str, Any]]:
        return cast(dict[str, dict[str, Any]], json.loads(self.path.read_text(encoding="utf-8")))

    def _write(self, state: dict[str, dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _empty_state(self) -> dict[str, dict[str, Any]]:
        return {table: {} for table in MINIMUM_TABLES}
