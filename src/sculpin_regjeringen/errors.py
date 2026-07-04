"""Typed ingestion errors with retry and provenance context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ErrorContext:
    url: str
    crawl_batch_id: str | None = None
    document_id: str | None = None
    parser_version: str | None = None
    retryable: bool = False
    source_artifact_uri: str | None = None
    traceback_hash: str | None = None


class RegjeringenIngestionError(Exception):
    """Base class for ingestion failures."""

    def __init__(self, message: str, context: ErrorContext | None = None) -> None:
        super().__init__(message)
        self.context = context


class DiscoveryError(RegjeringenIngestionError):
    pass


class RobotsDisallowedError(RegjeringenIngestionError):
    pass


class FetchTimeoutError(RegjeringenIngestionError):
    pass


class HttpStatusError(RegjeringenIngestionError):
    pass


class HtmlStructureError(RegjeringenIngestionError):
    pass


class MissingRequiredFieldError(RegjeringenIngestionError):
    pass


class AttachmentDownloadError(RegjeringenIngestionError):
    pass


class PdfExtractionError(RegjeringenIngestionError):
    pass


class DocxExtractionError(RegjeringenIngestionError):
    pass


class NormalizationError(RegjeringenIngestionError):
    pass


class GraphExportError(RegjeringenIngestionError):
    pass


class ValidationError(RegjeringenIngestionError):
    pass
