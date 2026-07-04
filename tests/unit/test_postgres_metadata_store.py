import importlib
import importlib.util
import os
from pathlib import Path

import pytest

from sculpin_regjeringen.crawler.attachment_downloader import (
    AttachmentDownloadManifest,
    AttachmentDownloadResult,
)
from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser
from sculpin_regjeringen.storage.postgres import PostgresMetadataStore

FIXTURE = Path("tests/fixtures/regjeringen/hearings/id3167072/page.html")
POSTGRES_DSN = os.environ.get("REGJERINGEN_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    POSTGRES_DSN is None, reason="REGJERINGEN_TEST_POSTGRES_DSN is not set"
)
if POSTGRES_DSN is not None:
    assert importlib.util.find_spec("psycopg") is not None, "psycopg is required in CI"
psycopg = importlib.import_module("psycopg") if POSTGRES_DSN is not None else None


def _document():
    html = FIXTURE.read_text(encoding="utf-8")
    document = HearingPageParser().parse(
        html,
        source_url="https://www.regjeringen.no/no/dokumenter/example/id3167072/",
        source_artifact_uri="file://fixtures/id3167072/page.html",
    )
    attachment = document.attachments[0]
    attachment.final_url = attachment.source_url
    attachment.checksum_sha256 = "a" * 64
    attachment.size_bytes = 123
    attachment.media_type = "application/pdf"
    attachment.object_uri = "file:///objects/a.pdf"
    return document


def test_postgres_metadata_store_upsert_is_idempotent_and_preserves_provenance() -> None:
    assert POSTGRES_DSN is not None
    assert psycopg is not None
    connection = psycopg.connect(POSTGRES_DSN)
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    store = PostgresMetadataStore(connection)
    store.apply_schema()
    document = _document()

    first = store.upsert_hearing_document(
        document,
        html_checksum_sha256="b" * 64,
        parser_version="test-parser",
        source_artifact_uri=document.source_html_object_uri,
        processed_at="2026-07-04T00:00:00+00:00",
        attachment_downloads=AttachmentDownloadManifest(document_id=document.document_id),
    )
    second = store.upsert_hearing_document(
        document,
        html_checksum_sha256="b" * 64,
        parser_version="test-parser",
        source_artifact_uri=document.source_html_object_uri,
        processed_at="2026-07-04T00:00:00+00:00",
        attachment_downloads=AttachmentDownloadManifest(document_id=document.document_id),
    )

    assert first.inserted_version
    assert not second.inserted_version
    assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM document_versions").fetchone()[0] == 1
    attachment_row = connection.execute(
        "SELECT checksum_sha256, object_uri FROM document_attachments"
    ).fetchone()
    assert attachment_row == (
        "a" * 64,
        "file:///objects/a.pdf",
    )
    provenance = connection.execute(
        """
        SELECT value_hash, heading_path, quote, extractor_version
        FROM field_provenance
        WHERE field_path = 'title'
        """
    ).fetchone()
    assert provenance[0]
    assert provenance[1] == []
    assert provenance[2]
    assert provenance[3]

    document.attachments[0].checksum_sha256 = "c" * 64
    document.attachments[0].object_uri = "file:///objects/c.pdf"
    store.upsert_hearing_document(
        document,
        html_checksum_sha256="b" * 64,
        parser_version="test-parser",
        source_artifact_uri=document.source_html_object_uri,
        processed_at="2026-07-04T00:00:00+00:00",
    )
    attachment_row = connection.execute(
        "SELECT checksum_sha256, object_uri FROM document_attachments"
    ).fetchone()
    assert attachment_row == (
        "c" * 64,
        "file:///objects/c.pdf",
    )
    connection.close()


def test_postgres_metadata_store_persists_attachment_download_events() -> None:
    assert POSTGRES_DSN is not None
    assert psycopg is not None
    connection = psycopg.connect(POSTGRES_DSN)
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    store = PostgresMetadataStore(connection)
    store.apply_schema()
    document = _document()

    manifest = AttachmentDownloadManifest(
        document_id=document.document_id,
        results=[
            AttachmentDownloadResult(
                attachment_id="dl",
                source_url="https://example.test/dl.pdf",
                request_url="https://example.test/dl.pdf",
                final_url="https://example.test/download/dl.pdf",
                status="downloaded",
                status_code=200,
                headers={"Content-Type": "application/pdf"},
                redirect_chain=["https://example.test/dl.pdf"],
                content_type="application/pdf",
                media_type="application/pdf",
                size_bytes=10,
                checksum_sha256="d" * 64,
                object_uri="file:///objects/d.pdf",
            ),
            AttachmentDownloadResult(
                attachment_id="sk",
                source_url="https://example.test/sk.zip",
                request_url="https://example.test/sk.zip",
                status="skipped",
                skipped_reason="unsupported_extension:.zip",
            ),
            AttachmentDownloadResult(
                attachment_id="fa",
                source_url="https://example.test/fa.pdf",
                request_url="https://example.test/fa.pdf",
                status="failed",
                error_type="RuntimeError",
                error_message="network down",
            ),
        ],
    )

    def _upsert() -> None:
        store.upsert_hearing_document(
            document,
            html_checksum_sha256="b" * 64,
            parser_version="test-parser",
            source_artifact_uri=document.source_html_object_uri,
            processed_at="2026-07-04T00:00:00+00:00",
            attachment_downloads=manifest,
        )

    _upsert()
    events = connection.execute(
        """
        SELECT attachment_id, status, skipped_reason, error_type, headers, redirect_chain
        FROM attachment_download_events
        ORDER BY attachment_id
        """
    ).fetchall()
    assert [(row[0], row[1]) for row in events] == [
        ("dl", "downloaded"),
        ("fa", "failed"),
        ("sk", "skipped"),
    ]
    by_id = {row[0]: row for row in events}
    assert by_id["dl"][4] == {"Content-Type": "application/pdf"}
    assert by_id["dl"][5] == ["https://example.test/dl.pdf"]
    assert by_id["sk"][2] == "unsupported_extension:.zip"
    assert by_id["fa"][3] == "RuntimeError"

    # Re-running the same version must not duplicate download events.
    _upsert()
    count = connection.execute(
        "SELECT count(*) FROM attachment_download_events"
    ).fetchone()[0]
    assert count == 3
    connection.close()
