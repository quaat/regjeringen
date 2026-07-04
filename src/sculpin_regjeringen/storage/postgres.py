"""PostgreSQL metadata storage adapter."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from sculpin_regjeringen.crawler.attachment_downloader import AttachmentDownloadManifest
from sculpin_regjeringen.models.canonical import HearingDocument
from sculpin_regjeringen.storage.local_metadata_store import MetadataUpsertResult

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "postgres" / "001_metadata.sql"


class PostgresMetadataStore:
    """Persist normalized regjeringen.no metadata to PostgreSQL using psycopg."""

    def __init__(self, connection: Any | str) -> None:
        if isinstance(connection, str):
            psycopg = importlib.import_module("psycopg")
            self.connection = psycopg.connect(connection)
            self._owns_connection = True
        else:
            self.connection = connection
            self._owns_connection = False

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def apply_schema(self, schema_path: Path = _SCHEMA_PATH) -> None:
        with self.connection.transaction():
            self.connection.execute(schema_path.read_text(encoding="utf-8"))

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
        version_id = f"{document.document_id}:{html_checksum_sha256}:{parser_version}"
        with self.connection.transaction():
            inserted_document = self._upsert_document(document)
            inserted_version = self._upsert_version(
                document=document,
                version_id=version_id,
                html_checksum_sha256=html_checksum_sha256,
                parser_version=parser_version,
                source_artifact_uri=source_artifact_uri,
                processed_at=processed_at,
            )
            self._replace_children(document, version_id, attachment_downloads)
            self.connection.execute(
                """
                INSERT INTO extraction_runs (
                    version_id, document_id, parser_version, processed_at, status, error_count
                ) VALUES (%s, %s, %s, %s, 'success', 0)
                ON CONFLICT (version_id) DO UPDATE SET
                    parser_version = EXCLUDED.parser_version,
                    processed_at = EXCLUDED.processed_at,
                    status = EXCLUDED.status,
                    error_count = EXCLUDED.error_count
                """,
                (version_id, document.document_id, parser_version, processed_at),
            )
            document_count = self._count("documents")
            version_count = self._count("document_versions")
        return MetadataUpsertResult(
            document_id=document.document_id,
            version_id=version_id,
            inserted_document=inserted_document,
            inserted_version=inserted_version,
            document_count=document_count,
            version_count=version_count,
        )

    def _upsert_document(self, document: HearingDocument) -> bool:
        inserted = self.connection.execute(
            """
            INSERT INTO documents (
                document_id, document_type, canonical_url, source_site, title, subtitle, summary,
                language, publication_date, updated_date, status, normalized_status, deadline,
                source_html_object_uri, extracted_text_object_uri
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                document_type = EXCLUDED.document_type,
                canonical_url = EXCLUDED.canonical_url,
                source_site = EXCLUDED.source_site,
                title = EXCLUDED.title,
                subtitle = EXCLUDED.subtitle,
                summary = EXCLUDED.summary,
                language = EXCLUDED.language,
                publication_date = EXCLUDED.publication_date,
                updated_date = EXCLUDED.updated_date,
                status = EXCLUDED.status,
                normalized_status = EXCLUDED.normalized_status,
                deadline = EXCLUDED.deadline,
                source_html_object_uri = EXCLUDED.source_html_object_uri,
                extracted_text_object_uri = EXCLUDED.extracted_text_object_uri,
                updated_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            (
                document.document_id,
                document.document_type,
                document.canonical_url,
                document.source_site,
                document.title,
                document.subtitle,
                document.summary,
                document.language,
                document.publication_date,
                document.updated_date,
                document.status,
                document.normalized_status,
                document.deadline,
                document.source_html_object_uri,
                document.extracted_text_object_uri,
            ),
        ).fetchone()
        return bool(inserted[0])

    def _upsert_version(
        self,
        *,
        document: HearingDocument,
        version_id: str,
        html_checksum_sha256: str,
        parser_version: str,
        source_artifact_uri: str,
        processed_at: str,
    ) -> bool:
        manifest_checksum = _attachment_manifest_checksum(document)
        inserted = self.connection.execute(
            """
            INSERT INTO document_versions (
                version_id, document_id, fetched_at, html_checksum_sha256,
                normalized_text_checksum_sha256, attachment_manifest_checksum_sha256,
                parser_version, extraction_status, previous_version_id, source_artifact_uri
            ) VALUES (%s, %s, %s, %s, NULL, %s, %s, 'success', NULL, %s)
            ON CONFLICT (document_id, html_checksum_sha256, parser_version) DO UPDATE SET
                attachment_manifest_checksum_sha256 = EXCLUDED.attachment_manifest_checksum_sha256,
                extraction_status = EXCLUDED.extraction_status,
                source_artifact_uri = EXCLUDED.source_artifact_uri
            RETURNING (xmax = 0) AS inserted
            """,
            (
                version_id,
                document.document_id,
                processed_at,
                html_checksum_sha256,
                manifest_checksum,
                parser_version,
                source_artifact_uri,
            ),
        ).fetchone()
        return bool(inserted[0])

    def _replace_children(
        self,
        document: HearingDocument,
        version_id: str,
        attachment_downloads: AttachmentDownloadManifest | None,
    ) -> None:
        for table in [
            "document_departments",
            "document_themes",
            "document_attachments",
            "document_sections",
            "document_links",
            "hearing_recipients",
            "contacts",
            "field_provenance",
        ]:
            self.connection.execute(
                f"DELETE FROM {table} WHERE document_id = %s",
                (document.document_id,),
            )

        for index, department in enumerate(document.responsible_departments):
            self.connection.execute(
                """
                INSERT INTO document_departments (document_id, ordinal, label, uri)
                VALUES (%s, %s, %s, %s)
                """,
                (document.document_id, index, department.label, department.uri),
            )
        for index, theme in enumerate(document.themes):
            self.connection.execute(
                """
                INSERT INTO document_themes (document_id, ordinal, label, uri)
                VALUES (%s, %s, %s, %s)
                """,
                (document.document_id, index, theme.label, theme.uri),
            )
        for attachment in document.attachments:
            self.connection.execute(
                """
                INSERT INTO document_attachments (
                    attachment_id, document_id, source_url, final_url, original_label,
                    original_filename, normalized_filename, media_type, file_extension,
                    size_label, size_bytes, checksum_sha256, object_uri, attachment_role,
                    extracted_text_uri, downloaded_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s IS NULL THEN NULL ELSE now() END
                )
                ON CONFLICT (attachment_id) DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    final_url = EXCLUDED.final_url,
                    original_label = EXCLUDED.original_label,
                    original_filename = EXCLUDED.original_filename,
                    normalized_filename = EXCLUDED.normalized_filename,
                    media_type = EXCLUDED.media_type,
                    file_extension = EXCLUDED.file_extension,
                    size_label = EXCLUDED.size_label,
                    size_bytes = EXCLUDED.size_bytes,
                    checksum_sha256 = EXCLUDED.checksum_sha256,
                    object_uri = EXCLUDED.object_uri,
                    attachment_role = EXCLUDED.attachment_role,
                    extracted_text_uri = EXCLUDED.extracted_text_uri,
                    downloaded_at = EXCLUDED.downloaded_at
                """,
                (
                    attachment.attachment_id,
                    document.document_id,
                    attachment.source_url,
                    attachment.final_url,
                    attachment.original_label,
                    attachment.original_filename,
                    attachment.normalized_filename,
                    attachment.media_type,
                    attachment.file_extension,
                    attachment.size_label,
                    attachment.size_bytes,
                    attachment.checksum_sha256,
                    attachment.object_uri,
                    attachment.attachment_role,
                    attachment.extracted_text_uri,
                    attachment.object_uri,
                ),
            )
        for section in document.sections:
            self.connection.execute(
                """
                INSERT INTO document_sections (
                    document_id, section_id, heading, heading_path, text_object_uri, source_span_id
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    document.document_id,
                    section.section_id,
                    section.heading,
                    json.dumps(section.heading_path),
                    section.text_object_uri,
                    section.source_span_id,
                ),
            )
        for index, link in enumerate(document.source_links):
            self.connection.execute(
                """
                INSERT INTO document_links (document_id, ordinal, url, label, relation)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (document.document_id, index, link.url, link.label, link.relation),
            )
        self.connection.execute(
            """
            INSERT INTO hearing_details (
                document_id, hearing_status, hearing_deadline, hearing_letter_section_id,
                hearing_note_attachment_ids, submission_url, hearing_responses_url
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                hearing_status = EXCLUDED.hearing_status,
                hearing_deadline = EXCLUDED.hearing_deadline,
                hearing_letter_section_id = EXCLUDED.hearing_letter_section_id,
                hearing_note_attachment_ids = EXCLUDED.hearing_note_attachment_ids,
                submission_url = EXCLUDED.submission_url,
                hearing_responses_url = EXCLUDED.hearing_responses_url
            """,
            (
                document.document_id,
                document.hearing_status,
                document.hearing_deadline,
                document.hearing_letter_section_id,
                json.dumps(document.hearing_note_attachment_ids),
                document.submission_url,
                document.hearing_responses_url,
            ),
        )
        for index, recipient in enumerate(document.hearing_recipients):
            self.connection.execute(
                """
                INSERT INTO hearing_recipients (document_id, ordinal, label, uri)
                VALUES (%s, %s, %s, %s)
                """,
                (document.document_id, index, recipient.label, recipient.uri),
            )
        for index, contact in enumerate(document.contacts):
            self.connection.execute(
                """
                INSERT INTO contacts (document_id, ordinal, label, email, phone, organization)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    document.document_id,
                    index,
                    contact.label,
                    contact.email,
                    contact.phone,
                    contact.organization,
                ),
            )
        for provenance in document.provenance:
            self.connection.execute(
                """
                INSERT INTO field_provenance (
                    document_id, field_path, value_hash, extraction_method, source_artifact_uri,
                    source_url, css_selector, heading_path, char_start, char_end, page_number,
                    quote, extractor_version, extracted_at, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id, field_path, source_artifact_uri) DO UPDATE SET
                    value_hash = EXCLUDED.value_hash,
                    extraction_method = EXCLUDED.extraction_method,
                    source_url = EXCLUDED.source_url,
                    css_selector = EXCLUDED.css_selector,
                    heading_path = EXCLUDED.heading_path,
                    char_start = EXCLUDED.char_start,
                    char_end = EXCLUDED.char_end,
                    page_number = EXCLUDED.page_number,
                    quote = EXCLUDED.quote,
                    extractor_version = EXCLUDED.extractor_version,
                    extracted_at = EXCLUDED.extracted_at,
                    confidence = EXCLUDED.confidence
                """,
                (
                    document.document_id,
                    provenance.field_path,
                    provenance.value_hash,
                    provenance.extraction_method,
                    provenance.source_artifact_uri,
                    provenance.source_url,
                    provenance.css_selector,
                    json.dumps(provenance.heading_path),
                    provenance.char_start,
                    provenance.char_end,
                    provenance.page_number,
                    provenance.quote,
                    provenance.extractor_version,
                    provenance.extracted_at,
                    provenance.confidence,
                ),
            )
        if attachment_downloads is not None:
            self.connection.execute(
                "DELETE FROM attachment_download_events WHERE version_id = %s", (version_id,)
            )
            for result in attachment_downloads.results:
                self.connection.execute(
                    """
                    INSERT INTO attachment_download_events (
                        version_id, document_id, attachment_id, source_url, request_url, final_url,
                        status, skipped_reason, error_type, error_message, status_code, headers,
                        redirect_chain, fetched_at, content_type, media_type, size_bytes,
                        checksum_sha256, object_uri
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        %s::jsonb, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        version_id,
                        document.document_id,
                        result.attachment_id,
                        result.source_url,
                        result.request_url,
                        result.final_url,
                        result.status,
                        result.skipped_reason,
                        result.error_type,
                        result.error_message,
                        result.status_code,
                        json.dumps(result.headers),
                        json.dumps(result.redirect_chain),
                        result.fetched_at,
                        result.content_type,
                        result.media_type,
                        result.size_bytes,
                        result.checksum_sha256,
                        result.object_uri,
                    ),
                )

    def _count(self, table: str) -> int:
        row = self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()
        return int(row[0])


def _attachment_manifest_checksum(document: HearingDocument) -> str:
    payload = [attachment.model_dump(mode="json") for attachment in document.attachments]
    import hashlib

    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
