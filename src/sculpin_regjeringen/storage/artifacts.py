"""Fixture-to-artifacts pipeline for hearing documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field

from sculpin_regjeringen.models.canonical import HearingDocument
from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser
from sculpin_regjeringen.storage.local_metadata_store import (
    LocalJsonMetadataStore,
    MetadataUpsertResult,
)
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore, StoredObject


class ArtifactRecord(BaseModel):
    role: str
    uri: str
    checksum_sha256: str
    content_type: str | None = None
    source_url: str
    source_artifact_uri: str | None = None
    parser_version: str
    processed_at: str


class HearingArtifactManifest(BaseModel):
    document_id: str
    canonical_url: str
    parser_version: str
    processed_at: str
    source_url: str
    source_artifact_uri: str
    html_checksum_sha256: str
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    metadata: MetadataUpsertResult | None = None


@dataclass(frozen=True, slots=True)
class HearingArtifactResult:
    document: HearingDocument
    manifest: HearingArtifactManifest
    manifest_uri: str
    document_json_uri: str


def write_hearing_fixture_artifacts(
    fixture: Path,
    *,
    object_store: LocalObjectStore,
    metadata_store: LocalJsonMetadataStore | None = None,
    source_url: str | None = None,
) -> HearingArtifactResult:
    """Parse a hearing fixture and write immutable local artifacts."""

    html = fixture.read_text(encoding="utf-8")
    html_bytes = html.encode("utf-8")
    processed_at = datetime.now(UTC).isoformat()
    parser = HearingPageParser()
    raw_object = object_store.put_object(
        f"raw-html/{fixture.parent.name}/page.html",
        html_bytes,
        content_type="text/html; charset=utf-8",
    )
    parse_source_url = (
        source_url or f"https://www.regjeringen.no/no/dokumenter/fixture/{fixture.parent.name}/"
    )
    document = parser.parse(
        html,
        source_url=parse_source_url,
        source_artifact_uri=raw_object.uri,
    )
    artifacts = [
        _artifact_record(
            role="raw_html",
            stored=raw_object,
            source_url=document.canonical_url,
            source_artifact_uri=None,
            parser_version=parser.parser_version,
            processed_at=processed_at,
        )
    ]

    for section in document.sections:
        if not section.visible_text:
            continue
        section_object = object_store.put_object(
            f"sections/{document.document_id}/{section.section_id}.txt",
            section.visible_text.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
        )
        section.text_object_uri = section_object.uri
        artifacts.append(
            _artifact_record(
                role=f"section_text:{section.section_id}",
                stored=section_object,
                source_url=document.canonical_url,
                source_artifact_uri=raw_object.uri,
                parser_version=parser.parser_version,
                processed_at=processed_at,
            )
        )

    document_json = document.model_dump_json(indent=2).encode("utf-8")
    document_object = object_store.put_object(
        f"documents/{document.document_id}/document.json",
        document_json,
        content_type="application/json",
    )
    artifacts.append(
        _artifact_record(
            role="canonical_document",
            stored=document_object,
            source_url=document.canonical_url,
            source_artifact_uri=raw_object.uri,
            parser_version=parser.parser_version,
            processed_at=processed_at,
        )
    )

    metadata_result = None
    if metadata_store is not None:
        metadata_result = metadata_store.upsert_hearing_document(
            document,
            html_checksum_sha256=raw_object.checksum_sha256,
            parser_version=parser.parser_version,
            source_artifact_uri=raw_object.uri,
            processed_at=processed_at,
        )

    manifest = HearingArtifactManifest(
        document_id=document.document_id,
        canonical_url=document.canonical_url,
        parser_version=parser.parser_version,
        processed_at=processed_at,
        source_url=document.canonical_url,
        source_artifact_uri=raw_object.uri,
        html_checksum_sha256=raw_object.checksum_sha256,
        artifacts=artifacts,
        metadata=metadata_result,
    )
    manifest_bytes = manifest.model_dump_json(indent=2).encode("utf-8")
    manifest_object = object_store.put_object(
        f"manifests/{document.document_id}/manifest.json",
        manifest_bytes,
        content_type="application/json",
    )
    return HearingArtifactResult(
        document=document,
        manifest=manifest,
        manifest_uri=manifest_object.uri,
        document_json_uri=document_object.uri,
    )


def _artifact_record(
    *,
    role: str,
    stored: StoredObject,
    source_url: str,
    source_artifact_uri: str | None,
    parser_version: str,
    processed_at: str,
) -> ArtifactRecord:
    return ArtifactRecord(
        role=role,
        uri=stored.uri,
        checksum_sha256=stored.checksum_sha256,
        content_type=stored.content_type,
        source_url=source_url,
        source_artifact_uri=source_artifact_uri,
        parser_version=parser_version,
        processed_at=processed_at,
    )


def sha256_hex(body: bytes) -> str:
    return sha256(body).hexdigest()
