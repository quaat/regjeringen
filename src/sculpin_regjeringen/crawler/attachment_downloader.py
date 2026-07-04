"""Attachment download pipeline for canonical regjeringen.no documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from sculpin_regjeringen.crawler.fetcher import FetchResult
from sculpin_regjeringen.crawler.robots import CrawlPolicy
from sculpin_regjeringen.models.canonical import Attachment, GovernmentDocument
from sculpin_regjeringen.storage.object_store import ObjectStore

AttachmentDownloadStatus = Literal["downloaded", "skipped", "failed"]


class AttachmentFetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult:
        """Fetch attachment bytes from a public source URL."""


class AttachmentDownloadResult(BaseModel):
    attachment_id: str
    source_url: str
    request_url: str
    final_url: str | None = None
    status: AttachmentDownloadStatus
    skipped_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    status_code: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    redirect_chain: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    content_type: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    object_uri: str | None = None


class AttachmentDownloadManifest(BaseModel):
    document_id: str
    results: list[AttachmentDownloadResult] = Field(default_factory=list)

    @property
    def records(self) -> list[AttachmentDownloadResult]:
        """Backward-compatible alias for earlier component-level tests."""

        return self.results


@dataclass(frozen=True, slots=True)
class AttachmentDownloadOptions:
    fail_fast: bool = False
    policy: CrawlPolicy | None = None
    allowed_extensions: frozenset[str] = frozenset(
        {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".rtf"}
    )


_ATTACHMENT_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".rtf": "application/rtf",
}


async def download_document_attachments(
    document: GovernmentDocument,
    *,
    fetcher: AttachmentFetcher,
    object_store: ObjectStore,
    key_prefix: str = "assets",
    options: AttachmentDownloadOptions | None = None,
) -> AttachmentDownloadManifest:
    """Download supported visible attachments into immutable object storage.

    Failures, unsupported extensions, and crawl-policy skips are recorded per
    attachment. Successful downloads update the same canonical document object
    used by downstream artifact, metadata, and graph writers.
    """

    effective_options = options or AttachmentDownloadOptions()
    results: list[AttachmentDownloadResult] = []
    for attachment in document.attachments:
        result = await _download_one(
            document=document,
            attachment=attachment,
            fetcher=fetcher,
            object_store=object_store,
            key_prefix=key_prefix,
            options=effective_options,
        )
        results.append(result)
    return AttachmentDownloadManifest(document_id=document.document_id, results=results)


async def _download_one(
    *,
    document: GovernmentDocument,
    attachment: Attachment,
    fetcher: AttachmentFetcher,
    object_store: ObjectStore,
    key_prefix: str,
    options: AttachmentDownloadOptions,
) -> AttachmentDownloadResult:
    extension = _attachment_extension(attachment)
    if extension not in options.allowed_extensions:
        return _skipped(attachment, f"unsupported_extension:{extension or 'none'}")
    if options.policy is not None and not options.policy.is_allowed(attachment.source_url):
        return _skipped(attachment, "crawl_policy_rejected")

    try:
        fetch_result = await fetcher.fetch(attachment.source_url)
    except Exception as exc:
        if options.fail_fast:
            raise
        return AttachmentDownloadResult(
            attachment_id=attachment.attachment_id,
            source_url=attachment.source_url,
            request_url=attachment.source_url,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    checksum = sha256(fetch_result.body).hexdigest()
    content_type = _content_type(fetch_result.headers)
    media_type = content_type or attachment.media_type or _media_type_for_ext(extension)
    filename = attachment.normalized_filename or PurePosixPath(attachment.source_url).name
    object_uri = object_store.put_bytes(
        f"{key_prefix}/{document.document_id}/{attachment.attachment_id}/{filename}",
        fetch_result.body,
        content_type=media_type,
    )

    attachment.final_url = fetch_result.final_url
    attachment.checksum_sha256 = checksum
    attachment.size_bytes = len(fetch_result.body)
    attachment.media_type = media_type
    attachment.object_uri = object_uri

    return AttachmentDownloadResult(
        attachment_id=attachment.attachment_id,
        source_url=attachment.source_url,
        request_url=fetch_result.request_url,
        final_url=fetch_result.final_url,
        status="downloaded",
        status_code=fetch_result.status_code,
        headers=fetch_result.headers,
        redirect_chain=fetch_result.redirect_chain,
        fetched_at=fetch_result.fetched_at,
        content_type=content_type,
        media_type=media_type,
        size_bytes=len(fetch_result.body),
        checksum_sha256=checksum,
        object_uri=object_uri,
    )


def _skipped(attachment: Attachment, reason: str) -> AttachmentDownloadResult:
    return AttachmentDownloadResult(
        attachment_id=attachment.attachment_id,
        source_url=attachment.source_url,
        request_url=attachment.source_url,
        status="skipped",
        skipped_reason=reason,
    )


def _attachment_extension(attachment: Attachment) -> str:
    raw_extension = attachment.file_extension or PurePosixPath(attachment.source_url).suffix
    extension = raw_extension.lower()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return extension


def _media_type_for_ext(extension: str | None) -> str | None:
    if not extension:
        return None
    normalized = extension if extension.startswith(".") else f".{extension}"
    return _ATTACHMENT_MEDIA_TYPES.get(normalized.lower())


def _content_type(headers: dict[str, str]) -> str | None:
    for key, value in headers.items():
        if key.lower() == "content-type":
            return value.split(";", 1)[0].strip().lower() or None
    return None
