from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF
from typer.testing import CliRunner

from sculpin_regjeringen.cli import app
from sculpin_regjeringen.graph.mapping import SCGOV, document_to_graph, serialize_document_turtle
from sculpin_regjeringen.storage.artifacts import write_hearing_fixture_artifacts
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore
from sculpin_regjeringen.storage.postgres import LocalJsonMetadataStore

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
