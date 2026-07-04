from datetime import UTC, datetime
from pathlib import Path

import pytest

from sculpin_regjeringen.crawler.attachment_downloader import (
    AttachmentDownloadOptions,
    download_document_attachments,
)
from sculpin_regjeringen.crawler.fetcher import FetchResult
from sculpin_regjeringen.crawler.robots import CrawlPolicy, build_robots_parser
from sculpin_regjeringen.models.canonical import Attachment
from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore

FIXTURE = Path("tests/fixtures/regjeringen/hearings/id3167072/page.html")


class FakeAttachmentFetcher:
    def __init__(
        self, *, body: bytes = b"%PDF-1.7\nfake hearing note\n", fail: bool = False
    ) -> None:
        self.body = body
        self.fail = fail

    async def fetch(self, url: str) -> FetchResult:
        if self.fail:
            raise RuntimeError("network down")
        return FetchResult(
            request_url=url,
            final_url=url.replace("/contentassets/", "/download/contentassets/"),
            status_code=200,
            headers={"Content-Type": "application/pdf", "ETag": '"fake"'},
            body=self.body,
            fetched_at=datetime.now(UTC),
            redirect_chain=[url],
        )


def parse_document():
    html = FIXTURE.read_text(encoding="utf-8")
    return HearingPageParser().parse(
        html,
        source_url="https://www.regjeringen.no/no/dokumenter/example/id3167072/",
        source_artifact_uri="file://fixtures/id3167072/page.html",
    )


@pytest.mark.anyio
async def test_download_document_attachments_updates_document_and_object_store(
    tmp_path: Path,
) -> None:
    document = parse_document()
    store = LocalObjectStore(tmp_path / "objects")

    manifest = await download_document_attachments(
        document,
        fetcher=FakeAttachmentFetcher(),
        object_store=store,
    )

    assert manifest.document_id == "id3167072"
    assert len(manifest.results) == 1
    assert manifest.results[0].status == "downloaded"
    attachment = document.attachments[0]
    assert attachment.final_url and "/download/contentassets/" in attachment.final_url
    assert attachment.checksum_sha256 == manifest.results[0].checksum_sha256
    assert attachment.size_bytes == len(b"%PDF-1.7\nfake hearing note\n")
    assert attachment.media_type == "application/pdf"
    assert attachment.object_uri == manifest.results[0].object_uri
    assert store.get_bytes(attachment.object_uri) == b"%PDF-1.7\nfake hearing note\n"


@pytest.mark.anyio
async def test_downloader_supports_office_extensions_and_skips_unknown(tmp_path: Path) -> None:
    document = parse_document()
    document.attachments = [
        _attachment("a1", "https://example.test/file.docx", "docx"),
        _attachment("a2", "https://example.test/file.xls", "xls"),
        _attachment("a3", "https://example.test/file.xlsx", "xlsx"),
        _attachment("a4", "https://example.test/file.zip", "zip"),
    ]

    manifest = await download_document_attachments(
        document,
        fetcher=FakeAttachmentFetcher(),
        object_store=LocalObjectStore(tmp_path / "objects"),
    )

    assert [result.status for result in manifest.results] == [
        "downloaded",
        "downloaded",
        "downloaded",
        "skipped",
    ]
    assert manifest.results[3].skipped_reason == "unsupported_extension:.zip"


@pytest.mark.anyio
async def test_downloader_records_crawl_policy_rejection(tmp_path: Path) -> None:
    document = parse_document()
    robots = build_robots_parser("https://example.test/robots.txt", "User-agent: *\nDisallow: /")

    manifest = await download_document_attachments(
        document,
        fetcher=FakeAttachmentFetcher(),
        object_store=LocalObjectStore(tmp_path / "objects"),
        options=AttachmentDownloadOptions(policy=CrawlPolicy(robots=robots, user_agent="test")),
    )

    assert manifest.results[0].status == "skipped"
    assert manifest.results[0].skipped_reason == "crawl_policy_rejected"
    assert document.attachments[0].object_uri is None


@pytest.mark.anyio
async def test_downloader_records_fetch_failure_without_crashing(tmp_path: Path) -> None:
    document = parse_document()

    manifest = await download_document_attachments(
        document,
        fetcher=FakeAttachmentFetcher(fail=True),
        object_store=LocalObjectStore(tmp_path / "objects"),
    )

    assert manifest.results[0].status == "failed"
    assert manifest.results[0].error_type == "RuntimeError"
    assert document.attachments[0].object_uri is None


@pytest.mark.anyio
async def test_downloader_fail_fast_raises(tmp_path: Path) -> None:
    document = parse_document()

    with pytest.raises(RuntimeError, match="network down"):
        await download_document_attachments(
            document,
            fetcher=FakeAttachmentFetcher(fail=True),
            object_store=LocalObjectStore(tmp_path / "objects"),
            options=AttachmentDownloadOptions(fail_fast=True),
        )


@pytest.mark.anyio
async def test_repeated_download_has_stable_object_uri_and_checksum(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    first = parse_document()
    second = parse_document()

    first_manifest = await download_document_attachments(
        first, fetcher=FakeAttachmentFetcher(), object_store=store
    )
    second_manifest = await download_document_attachments(
        second, fetcher=FakeAttachmentFetcher(), object_store=store
    )

    assert first_manifest.results[0].object_uri == second_manifest.results[0].object_uri
    assert first_manifest.results[0].checksum_sha256 == second_manifest.results[0].checksum_sha256


def _attachment(attachment_id: str, url: str, extension: str) -> Attachment:
    return Attachment(
        attachment_id=attachment_id,
        document_id="id3167072",
        source_url=url,
        original_label=url,
        normalized_filename=Path(url).name,
        file_extension=extension,
    )
