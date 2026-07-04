"""Command line interface for source audit, parsing, and graph export."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import httpx
import typer

from sculpin_regjeringen.crawler.attachment_downloader import AttachmentDownloadOptions
from sculpin_regjeringen.crawler.fetcher import HttpxFetcher
from sculpin_regjeringen.crawler.robots import CrawlPolicy, build_robots_parser
from sculpin_regjeringen.crawler.source_audit import SourceAuditOptions, run_source_audit_sync
from sculpin_regjeringen.graph.mapping import serialize_document_turtle
from sculpin_regjeringen.ingest_hearings import (
    HearingBatchIngestionOptions,
    run_hearing_batch_ingestion,
)
from sculpin_regjeringen.models.canonical import HearingDocument
from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser
from sculpin_regjeringen.storage.artifacts import (
    process_hearing_fixture,
)
from sculpin_regjeringen.storage.local_metadata_store import LocalJsonMetadataStore, MetadataStore
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore

app = typer.Typer(help="Ingest and organize regjeringen.no documents for Sculpin.")


@app.command("audit-sources")
def audit_sources(
    categories: Annotated[str, typer.Option(help="Comma-separated category names.")] = "hearing",
    sample_size: Annotated[int, typer.Option(min=1, max=500)] = 50,
    output: Annotated[Path, typer.Option()] = Path("reports/source-audit.md"),
    fixture_root: Annotated[Path, typer.Option()] = Path("tests/fixtures/regjeringen"),
    max_listing_pages: Annotated[int, typer.Option(min=1, max=50)] = 1,
    fetch_details: Annotated[bool, typer.Option()] = True,
) -> None:
    """Audit robots, sitemap, category pages, and parser field availability."""

    result = run_source_audit_sync(
        SourceAuditOptions(
            categories=[category.strip() for category in categories.split(",") if category.strip()],
            sample_size=sample_size,
            output=output,
            fixture_root=fixture_root,
            max_listing_pages=max_listing_pages,
            fetch_details=fetch_details,
        )
    )
    typer.echo(f"Wrote source audit report: {output}")
    typer.echo(f"Wrote source audit manifest: {output.with_suffix('.json')}")
    typer.echo(f"Crawl batch: {result.crawl_batch_id}")


@app.command("parse-fixture")
def parse_fixture(
    fixture: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    document_type: Annotated[str, typer.Option()] = "hearing",
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Parse a saved fixture into the canonical document model."""

    if document_type != "hearing":
        typer.echo(f"Unsupported document type: {document_type}", err=True)
        raise typer.Exit(code=2)

    html = fixture.read_text(encoding="utf-8")
    document_id = fixture.parent.name
    source_url = f"https://www.regjeringen.no/no/dokumenter/fixture/{document_id}/"
    document = HearingPageParser().parse(
        html,
        source_url=source_url,
        source_artifact_uri=fixture.resolve().as_uri(),
    )
    payload = document.model_dump_json(indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"Wrote parsed fixture: {output}")
    else:
        typer.echo(payload)


@app.command("process-fixture")
def process_fixture(
    fixture: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    artifact_root: Annotated[Path, typer.Option()] = Path("data/local-artifacts"),
    metadata_db: Annotated[Path, typer.Option()] = Path("data/local-metadata/metadata.json"),
    graph_output: Annotated[Path | None, typer.Option()] = None,
    download_attachments: Annotated[
        bool, typer.Option("--download-attachments/--no-download-attachments")
    ] = False,
    attachment_fail_fast: Annotated[
        bool, typer.Option("--attachment-fail-fast/--no-attachment-fail-fast")
    ] = False,
    respect_robots: Annotated[
        bool, typer.Option("--respect-robots/--no-respect-robots")
    ] = True,
) -> None:
    """Parse a hearing fixture and write local artifacts, metadata, and optional Turtle."""

    object_store = LocalObjectStore(artifact_root / "objects")
    metadata_store = LocalJsonMetadataStore(metadata_db)
    attachment_fetcher = None
    attachment_options = None
    if download_attachments:
        user_agent = "sculpin-regjeringen-ingest/0.1 (+https://github.com/quaat/regjeringen)"
        attachment_fetcher = HttpxFetcher(user_agent=user_agent)
        policy = _live_crawl_policy(user_agent) if respect_robots else None
        attachment_options = AttachmentDownloadOptions(
            fail_fast=attachment_fail_fast,
            policy=policy,
        )
    result = asyncio.run(
        process_hearing_fixture(
            fixture,
            object_store=object_store,
            metadata_store=metadata_store,
            attachment_fetcher=attachment_fetcher,
            attachment_options=attachment_options,
        )
    )
    if graph_output is not None:
        serialize_document_turtle(result.document, graph_output)
        typer.echo(f"Wrote Turtle graph: {graph_output}")
    typer.echo(f"Wrote canonical document: {result.document_json_uri}")
    typer.echo(f"Wrote artifact manifest: {result.manifest_uri}")
    if result.manifest.metadata is not None:
        typer.echo(
            f"Metadata version: {result.manifest.metadata.version_id} "
            f"inserted={result.manifest.metadata.inserted_version}"
        )


@app.command("ingest-hearings")
def ingest_hearings(
    urls: Annotated[list[str] | None, typer.Option("--url")] = None,
    url_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    artifact_root: Annotated[Path, typer.Option()] = Path("data/local-artifacts"),
    metadata_db: Annotated[Path | None, typer.Option()] = None,
    postgres_dsn: Annotated[str | None, typer.Option()] = None,
    graph_output_dir: Annotated[Path | None, typer.Option()] = None,
    download_attachments: Annotated[
        bool, typer.Option("--download-attachments/--no-download-attachments")
    ] = False,
    attachment_fail_fast: Annotated[
        bool, typer.Option("--attachment-fail-fast/--no-attachment-fail-fast")
    ] = False,
    respect_robots: Annotated[bool, typer.Option("--respect-robots/--no-respect-robots")] = True,
    user_agent: Annotated[str, typer.Option()] = (
        "sculpin-regjeringen-ingest/0.1 (+https://github.com/quaat/regjeringen)"
    ),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
    concurrency: Annotated[int, typer.Option(min=1, max=16)] = 2,
    request_timeout_seconds: Annotated[float, typer.Option(min=1.0)] = 30.0,
    fail_fast: Annotated[bool, typer.Option("--fail-fast/--no-fail-fast")] = False,
) -> None:
    """Fetch and ingest explicit regjeringen.no hearing URLs or a newline URL file."""

    supplied_urls = list(urls or [])
    if url_file is not None:
        supplied_urls.extend(
            line.strip() for line in url_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not supplied_urls:
        typer.echo("Provide at least one --url or --url-file.", err=True)
        raise typer.Exit(code=2)
    if postgres_dsn is not None and metadata_db is not None:
        typer.echo("Use only one of --postgres-dsn or --metadata-db.", err=True)
        raise typer.Exit(code=2)

    metadata_store: MetadataStore | None = None
    metadata_backend = "none"
    if postgres_dsn is not None:
        from sculpin_regjeringen.storage.postgres import PostgresMetadataStore

        metadata_store = PostgresMetadataStore(postgres_dsn)
        metadata_store.apply_schema()
        metadata_backend = "postgres"
    elif metadata_db is not None:
        metadata_store = LocalJsonMetadataStore(metadata_db)
        metadata_backend = "local-json"

    policy = _live_crawl_policy(user_agent) if respect_robots else None
    fetcher = HttpxFetcher(user_agent=user_agent, timeout_seconds=request_timeout_seconds)
    summary = asyncio.run(
        run_hearing_batch_ingestion(
            HearingBatchIngestionOptions(
                seed_urls=tuple(supplied_urls),
                artifact_root=artifact_root,
                postgres_dsn=postgres_dsn,
                metadata_json=metadata_db,
                graph_output_dir=graph_output_dir,
                download_attachments=download_attachments,
                attachment_fail_fast=attachment_fail_fast,
                respect_robots=respect_robots,
                user_agent=user_agent,
                max_pages=max_pages,
                concurrency=concurrency,
                request_timeout_seconds=request_timeout_seconds,
                fail_fast=fail_fast,
            ),
            page_fetcher=fetcher,
            attachment_fetcher=fetcher if download_attachments else None,
            metadata_store=metadata_store,
            crawl_policy=policy,
        )
    )
    close = getattr(metadata_store, "close", None)
    if close is not None:
        close()
    typer.echo(f"Pages attempted: {summary.pages_attempted}")
    typer.echo(f"Pages succeeded: {summary.pages_succeeded}")
    typer.echo(f"Pages failed: {summary.pages_failed}")
    typer.echo(f"Attachments downloaded: {summary.attachments_downloaded}")
    typer.echo(f"Attachments skipped: {summary.attachments_skipped}")
    typer.echo(f"Attachments failed: {summary.attachments_failed}")
    typer.echo(f"Metadata backend: {metadata_backend}")
    typer.echo(f"Artifact root: {artifact_root}")
    typer.echo(f"Graph output directory: {graph_output_dir or 'not written'}")
    typer.echo(f"Batch manifest: {summary.manifest_uri}")


@app.command("export-graph")
def export_graph(
    output: Annotated[Path, typer.Option()] = Path("tmp/document.ttl"),
    document_json: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    fixture: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    document_type: Annotated[str, typer.Option()] = "hearing",
) -> None:
    """Export parsed hearing metadata and source pointers as Turtle."""

    if document_json is None and fixture is None:
        typer.echo("Provide --document-json or --fixture.", err=True)
        raise typer.Exit(code=2)
    if document_json is not None and fixture is not None:
        typer.echo("Use only one of --document-json or --fixture.", err=True)
        raise typer.Exit(code=2)
    if document_type != "hearing":
        typer.echo(f"Unsupported document type: {document_type}", err=True)
        raise typer.Exit(code=2)

    if document_json is not None:
        document = HearingDocument.model_validate_json(document_json.read_text(encoding="utf-8"))
    else:
        assert fixture is not None
        html = fixture.read_text(encoding="utf-8")
        document = HearingPageParser().parse(
            html,
            source_url=f"https://www.regjeringen.no/no/dokumenter/fixture/{fixture.parent.name}/",
            source_artifact_uri=fixture.resolve().as_uri(),
        )
    serialize_document_turtle(document, output)
    typer.echo(f"Wrote Turtle graph: {output}")


def _live_crawl_policy(user_agent: str) -> CrawlPolicy:
    robots_url = "https://www.regjeringen.no/robots.txt"
    response = httpx.get(robots_url, headers={"User-Agent": user_agent}, timeout=30.0)
    response.raise_for_status()
    return CrawlPolicy(
        robots=build_robots_parser(robots_url, response.text),
        user_agent=user_agent,
    )


if __name__ == "__main__":
    app()
