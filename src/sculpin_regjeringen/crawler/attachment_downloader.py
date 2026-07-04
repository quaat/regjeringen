"""Attachment download pipeline for canonical regjeringen.no documents."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Protocol

from sculpin_regjeringen.crawler.fetcher import FetchResult
from sculpin_regjeringen.models.canonical import Attachment, GovernmentDocument
from sculpin_regjeringen.storage.object_store import ObjectStore


class AttachmentFetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult:
        """Fetch attachment bytes from a public source URL."""


@dataclass(frozen=True, slots=True)
class AttachmentDownloadRecord:
    attachment_id: str
    source_url: str
    final_url: str
    object_uri: str
    checksum_sha256: str
    size_bytes: int
    media_type: str | None


@dataclass(frozen=True, slots=True)
class AttachmentDownloadManifest:
    document_id: str
    records: list[AttachmentDownloadRecord]


_ATTACHMENT_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".rtf": "application/rtf",
}


async def download_document_attachments(
    document: GovernmentDocument,
    *,
    fetcher: AttachmentFetcher,
    object_store: ObjectStore,
    key_prefix: str = "assets",
) -> AttachmentDownloadManifest:
    """Download visible document attachments into immutable object storage.

    The canonical document is updated in place with final URL, checksum, size,
    media type, and object URI so downstream metadata stores can persist the
    production-ready asset pointers without embedding large bytes in the graph.
    """

    records: list[AttachmentDownloadRecord] = []
    for attachment in document.attachments:
        if not _should_download(attachment):
            continue
        result = await fetcher.fetch(attachment.source_url)
        checksum = sha256(result.body).hexdigest()
        media_type = _content_type(result.headers) or attachment.media_type or _media_type_for_ext(
            attachment.file_extension
        )
        filename = attachment.normalized_filename or PurePosixPath(attachment.source_url).name
        key = f"{key_prefix}/{document.document_id}/{attachment.attachment_id}/{filename}"
        object_uri = object_store.put_bytes(key, result.body, content_type=media_type)

        attachment.final_url = result.final_url
        attachment.checksum_sha256 = checksum
        attachment.size_bytes = len(result.body)
        attachment.media_type = media_type
        attachment.object_uri = object_uri

        records.append(
            AttachmentDownloadRecord(
                attachment_id=attachment.attachment_id,
                source_url=attachment.source_url,
                final_url=result.final_url,
                object_uri=object_uri,
                checksum_sha256=checksum,
                size_bytes=len(result.body),
                media_type=media_type,
            )
        )
    return AttachmentDownloadManifest(document_id=document.document_id, records=records)


def _should_download(attachment: Attachment) -> bool:
    raw_extension = attachment.file_extension or PurePosixPath(attachment.source_url).suffix
    extension = raw_extension.lower()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return extension in _ATTACHMENT_MEDIA_TYPES


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
