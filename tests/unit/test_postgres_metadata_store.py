import importlib
import importlib.util
import os
from pathlib import Path

import pytest

from sculpin_regjeringen.crawler.attachment_downloader import AttachmentDownloadManifest
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
