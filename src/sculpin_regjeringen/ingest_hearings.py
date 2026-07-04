"""Batch ingestion runner for live regjeringen.no hearing pages."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from sculpin_regjeringen.crawler.attachment_downloader import (
    AttachmentDownloadOptions,
    AttachmentFetcher,
)
from sculpin_regjeringen.crawler.fetcher import FetchResult, HttpxFetcher
from sculpin_regjeringen.crawler.robots import CrawlPolicy
from sculpin_regjeringen.graph.mapping import serialize_document_turtle
from sculpin_regjeringen.storage.artifacts import HearingArtifactResult, process_hearing_html
from sculpin_regjeringen.storage.local_metadata_store import MetadataStore
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


@dataclass(frozen=True, slots=True)
class HearingBatchIngestionOptions:
    seed_urls: tuple[str, ...]
    artifact_root: Path
    postgres_dsn: str | None = None
    metadata_json: Path | None = None
    graph_output_dir: Path | None = None
    download_attachments: bool = False
    attachment_fail_fast: bool = False
    respect_robots: bool = True
    user_agent: str = "sculpin-regjeringen-ingest/0.1 (+https://github.com/quaat/regjeringen)"
    max_pages: int | None = None
    concurrency: int = 2
    request_timeout_seconds: float = 30.0
    dry_run: bool = False
    fail_fast: bool = False


class AttachmentResultCounts(BaseModel):
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0


class HearingBatchDocumentResult(BaseModel):
    source_url: str
    status: str
    document_id: str | None = None
    artifact_manifest_uri: str | None = None
    canonical_document_uri: str | None = None
    graph_output_path: str | None = None
    attachment_counts: AttachmentResultCounts = Field(default_factory=AttachmentResultCounts)
    error_type: str | None = None
    error_message: str | None = None


class HearingBatchManifest(BaseModel):
    batch_id: str
    started_at: str
    finished_at: str | None = None
    input_urls: list[str]
    results: list[HearingBatchDocumentResult] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HearingBatchSummary:
    manifest: HearingBatchManifest
    manifest_uri: str
    pages_attempted: int
    pages_succeeded: int
    pages_failed: int
    attachments_downloaded: int
    attachments_skipped: int
    attachments_failed: int
    metadata_backend: str
    artifact_root: Path
    graph_output_dir: Path | None


async def run_hearing_batch_ingestion(
    options: HearingBatchIngestionOptions,
    *,
    page_fetcher: PageFetcher | None = None,
    attachment_fetcher: AttachmentFetcher | None = None,
    metadata_store: MetadataStore | None = None,
    crawl_policy: CrawlPolicy | None = None,
) -> HearingBatchSummary:
    urls = _dedupe(options.seed_urls)
    if options.max_pages is not None:
        urls = urls[: options.max_pages]
    object_store = LocalObjectStore(options.artifact_root / "objects")
    fetcher = page_fetcher or HttpxFetcher(options.user_agent, options.request_timeout_seconds)
    sem = asyncio.Semaphore(max(1, options.concurrency))
    manifest = HearingBatchManifest(
        batch_id=f"hearing-batch-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        started_at=datetime.now(UTC).isoformat(),
        input_urls=list(urls),
    )

    async def one(url: str) -> HearingBatchDocumentResult:
        async with sem:
            if crawl_policy is not None and not crawl_policy.is_allowed(url):
                return _failure(url, PermissionError("URL disallowed by robots policy"))
            try:
                if options.dry_run:
                    return HearingBatchDocumentResult(source_url=url, status="skipped")
                fetched = await fetcher.fetch(url)
                html = fetched.body.decode(_charset(fetched.headers), errors="replace")
                effective_attachment_fetcher = (
                    attachment_fetcher if options.download_attachments else None
                )
                effective_attachment_options = (
                    AttachmentDownloadOptions(
                        fail_fast=options.attachment_fail_fast,
                        policy=crawl_policy,
                    )
                    if effective_attachment_fetcher is not None
                    else None
                )
                artifact_result = await process_hearing_html(
                    html,
                    source_url=fetched.final_url,
                    object_store=object_store,
                    metadata_store=metadata_store,
                    attachment_fetcher=effective_attachment_fetcher,
                    attachment_options=effective_attachment_options,
                    raw_html_bytes=fetched.body,
                    raw_html_content_type=_content_type(fetched.headers),
                )
                graph_path = None
                if options.graph_output_dir is not None:
                    graph_path = (
                        options.graph_output_dir / f"{artifact_result.document.document_id}.ttl"
                    )
                    serialize_document_turtle(artifact_result.document, graph_path)
                return _success(url, artifact_result, graph_path)
            except Exception as exc:  # noqa: BLE001 - batch runner records per-URL failures.
                if options.fail_fast:
                    raise
                return _failure(url, exc)

    for task in asyncio.as_completed([one(url) for url in urls]):
        manifest.results.append(await task)
    manifest.finished_at = datetime.now(UTC).isoformat()
    manifest_obj = object_store.put_object(
        f"batch-manifests/{manifest.batch_id}.json",
        manifest.model_dump_json(indent=2).encode("utf-8"),
        content_type="application/json",
    )
    counts = _total_counts(manifest.results)
    return HearingBatchSummary(
        manifest=manifest,
        manifest_uri=manifest_obj.uri,
        pages_attempted=len(urls),
        pages_succeeded=sum(1 for r in manifest.results if r.status == "success"),
        pages_failed=sum(1 for r in manifest.results if r.status == "failed"),
        attachments_downloaded=counts.downloaded,
        attachments_skipped=counts.skipped,
        attachments_failed=counts.failed,
        metadata_backend="injected" if metadata_store is not None else "none",
        artifact_root=options.artifact_root,
        graph_output_dir=options.graph_output_dir,
    )


def _success(
    url: str, result: HearingArtifactResult, graph_path: Path | None
) -> HearingBatchDocumentResult:
    counts = AttachmentResultCounts()
    if result.manifest.attachment_downloads is not None:
        for item in result.manifest.attachment_downloads.results:
            setattr(counts, item.status, getattr(counts, item.status) + 1)
    return HearingBatchDocumentResult(
        source_url=url,
        status="success",
        document_id=result.document.document_id,
        artifact_manifest_uri=result.manifest_uri,
        canonical_document_uri=result.document_json_uri,
        graph_output_path=str(graph_path) if graph_path else None,
        attachment_counts=counts,
    )


def _failure(url: str, exc: Exception) -> HearingBatchDocumentResult:
    return HearingBatchDocumentResult(
        source_url=url,
        status="failed",
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def _dedupe(urls: tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(url.strip() for url in urls if url.strip()))


def _charset(headers: dict[str, str]) -> str:
    content_type = headers.get("content-type", "")
    for part in content_type.split(";"):
        if "charset=" in part.lower():
            return part.split("=", 1)[1].strip()
    return "utf-8"


def _total_counts(results: list[HearingBatchDocumentResult]) -> AttachmentResultCounts:
    counts = AttachmentResultCounts()
    for result in results:
        counts.downloaded += result.attachment_counts.downloaded
        counts.skipped += result.attachment_counts.skipped
        counts.failed += result.attachment_counts.failed
    return counts


def _content_type(headers: dict[str, str]) -> str | None:
    return headers.get("content-type") or headers.get("Content-Type")
