from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

import pytest

from sculpin_regjeringen.crawler.fetcher import FetchResult
from sculpin_regjeringen.ingest_hearings import (
    HearingBatchIngestionOptions,
    run_hearing_batch_ingestion,
)
from sculpin_regjeringen.storage.local_metadata_store import LocalJsonMetadataStore

FIXTURE = Path("tests/fixtures/regjeringen/hearings/id3167072/page.html")


class FakeFetcher:
    def __init__(self, html: str | None = None, *, fail: bool = False) -> None:
        self.html = html or FIXTURE.read_text(encoding="utf-8")
        self.fail = fail

    async def fetch(self, url: str) -> FetchResult:
        if self.fail or "fail" in url:
            raise RuntimeError("boom")
        body = b"%PDF-1.4 fake" if url.endswith(".pdf") else self.html.encode()
        content_type = "application/pdf" if url.endswith(".pdf") else "text/html; charset=utf-8"
        return FetchResult(
            request_url=url,
            final_url=url,
            status_code=200,
            headers={"content-type": content_type},
            body=body,
            fetched_at=datetime.now(UTC),
        )


class RawBytesFetcher:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.body = body
        self.content_type = content_type

    async def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            request_url=url,
            final_url=url,
            status_code=200,
            headers={"content-type": self.content_type},
            body=self.body,
            fetched_at=datetime.now(UTC),
        )


class RaisingAttachmentFetcher:
    async def fetch(self, url: str) -> FetchResult:
        raise AssertionError(f"attachment fetcher should not be called for {url}")


@pytest.mark.anyio
async def test_single_hearing_success_writes_artifacts_metadata_and_graph(
    tmp_path: Path,
) -> None:
    metadata = LocalJsonMetadataStore(tmp_path / "metadata.json")
    summary = await run_hearing_batch_ingestion(
        HearingBatchIngestionOptions(
            seed_urls=("https://www.regjeringen.no/no/dokumenter/test/id3167072/",),
            artifact_root=tmp_path / "artifacts",
            metadata_json=tmp_path / "metadata.json",
            graph_output_dir=tmp_path / "graphs",
        ),
        page_fetcher=FakeFetcher(),
        metadata_store=metadata,
    )

    assert summary.pages_attempted == 1
    assert summary.pages_succeeded == 1
    result = summary.manifest.results[0]
    assert result.document_id == "id3167072"
    assert result.canonical_document_uri is not None
    assert result.artifact_manifest_uri is not None
    assert result.graph_output_path is not None
    assert Path(result.graph_output_path).exists()
    assert metadata.count("documents") == 1
    assert metadata.count("document_versions") == 1


@pytest.mark.anyio
async def test_live_ingestion_preserves_original_raw_html_bytes(tmp_path: Path) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    raw_body = html.encode("cp1252")
    assert raw_body != html.encode("utf-8")

    summary = await run_hearing_batch_ingestion(
        HearingBatchIngestionOptions(
            seed_urls=("https://www.regjeringen.no/no/dokumenter/test/id3167072/",),
            artifact_root=tmp_path / "artifacts",
        ),
        page_fetcher=RawBytesFetcher(raw_body, "text/html; charset=windows-1252"),
    )

    result = summary.manifest.results[0]
    assert result.document_id == "id3167072"
    assert result.artifact_manifest_uri is not None
    manifest_path = Path(urlparse(result.artifact_manifest_uri).path)
    artifact_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_record = next(item for item in artifact_manifest["artifacts"] if item["role"] == "raw_html")
    raw_path = Path(urlparse(raw_record["uri"]).path)
    assert raw_path.read_bytes() == raw_body
    assert raw_record["checksum_sha256"] == sha256(raw_body).hexdigest()
    assert artifact_manifest["html_checksum_sha256"] == sha256(raw_body).hexdigest()


@pytest.mark.anyio
async def test_attachment_download_integration_keeps_graph_safe(tmp_path: Path) -> None:
    metadata = LocalJsonMetadataStore(tmp_path / "metadata.json")
    summary = await run_hearing_batch_ingestion(
        HearingBatchIngestionOptions(
            seed_urls=("https://www.regjeringen.no/no/dokumenter/test/id3167072/",),
            artifact_root=tmp_path / "artifacts",
            metadata_json=tmp_path / "metadata.json",
            graph_output_dir=tmp_path / "graphs",
            download_attachments=True,
        ),
        page_fetcher=FakeFetcher(),
        attachment_fetcher=FakeFetcher(),
        metadata_store=metadata,
    )

    assert summary.attachments_downloaded >= 1
    graph = Path(summary.manifest.results[0].graph_output_path or "").read_text(encoding="utf-8")
    assert "objectUri" in graph
    assert "%PDF-1.4" not in graph
    assert "Departementet sender med dette" not in graph
    assert metadata.count("attachment_download_events") >= 1


@pytest.mark.anyio
async def test_attachment_fetcher_ignored_when_downloads_disabled(tmp_path: Path) -> None:
    metadata = LocalJsonMetadataStore(tmp_path / "metadata.json")
    summary = await run_hearing_batch_ingestion(
        HearingBatchIngestionOptions(
            seed_urls=("https://www.regjeringen.no/no/dokumenter/test/id3167072/",),
            artifact_root=tmp_path / "artifacts",
            metadata_json=tmp_path / "metadata.json",
            download_attachments=False,
        ),
        page_fetcher=FakeFetcher(),
        attachment_fetcher=RaisingAttachmentFetcher(),
        metadata_store=metadata,
    )

    assert summary.pages_succeeded == 1
    assert summary.attachments_downloaded == 0
    assert summary.attachments_skipped == 0
    assert summary.attachments_failed == 0
    assert metadata.count("attachment_download_events") == 0


@pytest.mark.anyio
async def test_page_fetch_failure_continues_and_records_manifest(tmp_path: Path) -> None:
    summary = await run_hearing_batch_ingestion(
        HearingBatchIngestionOptions(
            seed_urls=("https://example.test/fail", "https://www.regjeringen.no/no/dokumenter/test/id3167072/"),
            artifact_root=tmp_path / "artifacts",
        ),
        page_fetcher=FakeFetcher(),
    )

    assert summary.pages_attempted == 2
    assert summary.pages_succeeded == 1
    assert summary.pages_failed == 1
    failed = [r for r in summary.manifest.results if r.status == "failed"][0]
    assert failed.error_type == "RuntimeError"


@pytest.mark.anyio
async def test_fail_fast_aborts_on_page_failure(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        await run_hearing_batch_ingestion(
            HearingBatchIngestionOptions(
                seed_urls=("https://example.test/fail",),
                artifact_root=tmp_path / "artifacts",
                fail_fast=True,
            ),
            page_fetcher=FakeFetcher(),
        )


@pytest.mark.anyio
async def test_no_metadata_backend_still_writes_artifacts_and_manifest(tmp_path: Path) -> None:
    summary = await run_hearing_batch_ingestion(
        HearingBatchIngestionOptions(
            seed_urls=("https://www.regjeringen.no/no/dokumenter/test/id3167072/",),
            artifact_root=tmp_path / "artifacts",
        ),
        page_fetcher=FakeFetcher(),
    )
    assert summary.pages_succeeded == 1
    assert summary.manifest_uri.startswith("file://")


def test_ingest_hearings_cli_with_fake_fetcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    import sculpin_regjeringen.cli as cli

    class CliFakeFetcher(FakeFetcher):
        def __init__(self, user_agent: str, timeout_seconds: float = 30.0) -> None:
            super().__init__()
            self.user_agent = user_agent
            self.timeout_seconds = timeout_seconds

    monkeypatch.setattr(cli, "HttpxFetcher", CliFakeFetcher)
    result = CliRunner().invoke(
        cli.app,
        [
            "ingest-hearings",
            "--url",
            "https://www.regjeringen.no/no/dokumenter/test/id3167072/",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--metadata-db",
            str(tmp_path / "metadata.json"),
            "--graph-output-dir",
            str(tmp_path / "graphs"),
            "--no-respect-robots",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Pages attempted: 1" in result.output
    assert "Pages succeeded: 1" in result.output
    assert "Metadata backend: local-json" in result.output
