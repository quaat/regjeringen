from datetime import UTC, datetime
from pathlib import Path

import pytest

from sculpin_regjeringen.crawler.attachment_downloader import download_document_attachments
from sculpin_regjeringen.crawler.fetcher import FetchResult
from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser
from sculpin_regjeringen.storage.local_object_store import LocalObjectStore

FIXTURE = Path("tests/fixtures/regjeringen/hearings/id3167072/page.html")


class FakeAttachmentFetcher:
    async def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            request_url=url,
            final_url=url.replace("/contentassets/", "/download/contentassets/"),
            status_code=200,
            headers={"Content-Type": "application/pdf", "ETag": '"fake"'},
            body=b"%PDF-1.7\nfake hearing note\n",
            fetched_at=datetime.now(UTC),
            redirect_chain=[],
        )


@pytest.mark.anyio
async def test_download_document_attachments_updates_document_and_object_store(
    tmp_path: Path,
) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    document = HearingPageParser().parse(
        html,
        source_url="https://www.regjeringen.no/no/dokumenter/example/id3167072/",
        source_artifact_uri="file://fixtures/id3167072/page.html",
    )
    store = LocalObjectStore(tmp_path / "objects")

    manifest = await download_document_attachments(
        document,
        fetcher=FakeAttachmentFetcher(),
        object_store=store,
    )

    assert manifest.document_id == "id3167072"
    assert len(manifest.records) == 1
    attachment = document.attachments[0]
    assert attachment.final_url and "/download/contentassets/" in attachment.final_url
    assert attachment.checksum_sha256 == manifest.records[0].checksum_sha256
    assert attachment.size_bytes == len(b"%PDF-1.7\nfake hearing note\n")
    assert attachment.media_type == "application/pdf"
    assert attachment.object_uri == manifest.records[0].object_uri
    assert store.get_bytes(attachment.object_uri) == b"%PDF-1.7\nfake hearing note\n"
