"""Command line interface for source audit, parsing, and graph export."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from sculpin_regjeringen.crawler.source_audit import SourceAuditOptions, run_source_audit_sync

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

    typer.echo(
        "Fixture parser scaffold is ready. "
        f"fixture={fixture} document_type={document_type} output={output}"
    )


@app.command("export-graph")
def export_graph(
    document_id: Annotated[str, typer.Option()],
    format: Annotated[str, typer.Option()] = "turtle",
    output: Annotated[Path, typer.Option()] = Path("tmp/document.ttl"),
) -> None:
    """Export canonical metadata as Sculpin graph triples."""

    typer.echo(
        "Graph export scaffold is ready. "
        f"document_id={document_id} format={format} output={output}"
    )


if __name__ == "__main__":
    app()
