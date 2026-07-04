from datetime import UTC, datetime
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF
from typer.testing import CliRunner

from sculpin_regjeringen.cli import app
from sculpin_regjeringen.crawler.attachment_downloader import AttachmentDownloadOptions
from sculpin_regjeringen.crawler.fetcher import FetchResult
from sculpin_regjeringen.crawler.robots import CrawlPolicy, build_robots_parser
from sculpin_regjeringen.graph.mapping import SCGOV, document_to_graph, serialize_document_turtle
from sculpin_regjeringen.storage.artifacts import (
    process_hearing_fixture,
    write_hearing_fixture_artifacts,
)
from sculpin_regjeringen.storage.local_metadata_store import LocalJsonMetadataStore
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore

FIXTURE = Path("tests/fixtures/regjeringen/hearings/id3167072/page.html")
FULL_HEARING_LETTER_TEXT = "Vi viser til Miljødirektoratets brev 19. august 2025"


def test_local_object_store_is_content_addressed_and_readable(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")

    first = store.put_object("raw/page.html", b"same", content_type="text/html")
    second = store.put_object("other/page.html", b"same", content_type="text/html")
    third = store.put_object("raw/page.html", b"different", content_type="text/html")

    assert first.uri == second.uri
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.uri != third.uri
    assert store.get_bytes(first.uri) == b"same"
    assert len(list((tmp_path / "objects").rglob("*.html"))) == 2


def test_fixture_to_artifacts_metadata_and_graph_pipeline_is_idempotent(tmp_path: Path) -> None:
    object_store = LocalObjectStore(tmp_path / "objects")
    metadata_store = LocalJsonMetadataStore(tmp_path / "metadata" / "metadata.json")

    first = write_hearing_fixture_artifacts(
        FIXTURE, object_store=object_store, metadata_store=metadata_store
    )
    second = write_hearing_fixture_artifacts(
        FIXTURE, object_store=object_store, metadata_store=metadata_store
    )

    assert first.document.document_id == "id3167072"
    assert first.manifest.source_artifact_uri == second.manifest.source_artifact_uri
    first_section_uris = [section.text_object_uri for section in first.document.sections]
    second_section_uris = [section.text_object_uri for section in second.document.sections]
    assert first_section_uris == second_section_uris
    # Manifest/document JSON artifacts include run timestamps/provenance timestamps and may vary.
    assert first.manifest.metadata is not None
    assert second.manifest.metadata is not None
    assert first.manifest.metadata.inserted_version
    assert not second.manifest.metadata.inserted_version
    assert metadata_store.count("documents") == 1
    assert metadata_store.count("document_versions") == 1
    assert all(section.text_object_uri for section in first.document.sections)

    graph = document_to_graph(first.document)
    turtle = graph.serialize(format="turtle")
    assert first.document.source_html_object_uri in turtle
    assert "textObjectUri" in turtle
    assert FULL_HEARING_LETTER_TEXT not in turtle

    doc_uri = URIRef(
        f"https://w3id.org/sculpin/government/regjeringen/document/{first.document.document_id}"
    )
    assert (doc_uri, RDF.type, SCGOV.Consultation) in graph
    assert (doc_uri, DCTERMS.title, Literal(first.document.title, lang="nb")) in graph
    assert any(
        predicate == SCGOV.hearingRecipient
        for _, predicate, _ in graph.triples((doc_uri, None, None))
    )


def test_serialize_document_turtle_round_trips_with_rdflib(tmp_path: Path) -> None:
    result = write_hearing_fixture_artifacts(
        FIXTURE,
        object_store=LocalObjectStore(tmp_path / "objects"),
        metadata_store=LocalJsonMetadataStore(tmp_path / "metadata.json"),
    )
    output = tmp_path / "graph.ttl"

    serialize_document_turtle(result.document, output)

    graph = Graph().parse(output, format="turtle")
    doc_uri = URIRef(
        f"https://w3id.org/sculpin/government/regjeringen/document/{result.document.document_id}"
    )
    assert (doc_uri, DCTERMS.identifier, Literal("id3167072")) in graph
    assert (doc_uri, SCGOV.canonicalUrl, URIRef(result.document.canonical_url)) in graph
    assert FULL_HEARING_LETTER_TEXT not in output.read_text(encoding="utf-8")


def test_process_fixture_and_export_graph_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    graph_output = tmp_path / "id3167072.ttl"
    result = runner.invoke(
        app,
        [
            "process-fixture",
            str(FIXTURE),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--metadata-db",
            str(tmp_path / "metadata.json"),
            "--graph-output",
            str(graph_output),
        ],
    )
    assert result.exit_code == 0
    assert graph_output.exists()
    assert FULL_HEARING_LETTER_TEXT not in graph_output.read_text(encoding="utf-8")

    fixture_graph = tmp_path / "fixture.ttl"
    result = runner.invoke(
        app,
        ["export-graph", "--fixture", str(FIXTURE), "--output", str(fixture_graph)],
    )
    assert result.exit_code == 0
    assert fixture_graph.exists()

    document_json = tmp_path / "document.json"
    result = runner.invoke(
        app,
        [
            "parse-fixture",
            str(FIXTURE),
            "--document-type",
            "hearing",
            "--output",
            str(document_json),
        ],
    )
    assert result.exit_code == 0
    json_graph = tmp_path / "json.ttl"
    result = runner.invoke(
        app,
        ["export-graph", "--document-json", str(document_json), "--output", str(json_graph)],
    )
    assert result.exit_code == 0
    assert json_graph.exists()


class PipelineFakeAttachmentFetcher:
    async def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            request_url=url,
            final_url=url,
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            body=b"%PDF-1.7 pipeline bytes\n",
            fetched_at=datetime.now(UTC),
            redirect_chain=[],
        )


@pytest.mark.anyio
async def test_process_fixture_downloads_before_document_metadata_and_graph(tmp_path: Path) -> None:
    object_store = LocalObjectStore(tmp_path / "objects")
    metadata_store = LocalJsonMetadataStore(tmp_path / "metadata" / "metadata.json")

    result = await process_hearing_fixture(
        FIXTURE,
        object_store=object_store,
        metadata_store=metadata_store,
        attachment_fetcher=PipelineFakeAttachmentFetcher(),
        attachment_options=AttachmentDownloadOptions(),
    )

    attachment = result.document.attachments[0]
    assert attachment.checksum_sha256
    assert attachment.size_bytes == len(b"%PDF-1.7 pipeline bytes\n")
    assert attachment.media_type == "application/pdf"
    assert attachment.final_url == attachment.source_url
    assert attachment.object_uri
    assert result.manifest.attachment_downloads
    assert result.manifest.attachment_downloads.results[0].status == "downloaded"

    document_json = object_store.get_bytes(result.document_json_uri).decode("utf-8")
    assert attachment.checksum_sha256 in document_json
    assert attachment.object_uri in document_json

    metadata = metadata_store._read()
    stored_attachment = metadata["attachments"][attachment.attachment_id]
    assert stored_attachment["checksum_sha256"] == attachment.checksum_sha256
    assert stored_attachment["object_uri"] == attachment.object_uri
    assert metadata["attachment_download_events"]

    graph = document_to_graph(result.document)
    turtle = graph.serialize(format="turtle")
    assert "objectUri" in turtle
    assert attachment.object_uri in turtle
    assert "%PDF-1.7 pipeline bytes" not in turtle
    assert FULL_HEARING_LETTER_TEXT not in turtle


@pytest.mark.anyio
async def test_process_fixture_persists_policy_skip_download_events(tmp_path: Path) -> None:
    object_store = LocalObjectStore(tmp_path / "objects")
    metadata_store = LocalJsonMetadataStore(tmp_path / "metadata" / "metadata.json")
    robots = build_robots_parser(
        "https://www.regjeringen.no/robots.txt", "User-agent: *\nDisallow: /"
    )

    result = await process_hearing_fixture(
        FIXTURE,
        object_store=object_store,
        metadata_store=metadata_store,
        attachment_fetcher=PipelineFakeAttachmentFetcher(),
        attachment_options=AttachmentDownloadOptions(
            policy=CrawlPolicy(robots=robots, user_agent="test")
        ),
    )

    assert result.manifest.attachment_downloads
    download_result = result.manifest.attachment_downloads.results[0]
    assert download_result.status == "skipped"
    assert download_result.skipped_reason == "crawl_policy_rejected"
    metadata = metadata_store._read()
    event = next(iter(metadata["attachment_download_events"].values()))
    assert event["status"] == "skipped"
    assert event["skipped_reason"] == "crawl_policy_rejected"
