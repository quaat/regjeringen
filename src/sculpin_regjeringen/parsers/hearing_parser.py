"""Hearing detail-page parser scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sculpin_regjeringen.models.canonical import HearingDocument
from sculpin_regjeringen.models.provenance import FieldProvenance
from sculpin_regjeringen.parsers.html_common import extract_document_id, infer_language


class HearingPageParser:
    parser_version = "regjeringen-parser-0.1.0"

    def parse(self, html: str, *, source_url: str, source_artifact_uri: str) -> HearingDocument:
        """Create a minimal canonical document from a hearing fixture.

        The deterministic selector implementation belongs in Phase 2. This scaffold records
        provenance for the fields it can derive without parsing site-specific structure.
        """

        document_id = extract_document_id(source_url)
        if document_id is None:
            msg = f"Could not derive regjeringen.no document id from {source_url}"
            raise ValueError(msg)

        title = self._fallback_title(html) or document_id
        return HearingDocument(
            document_id=document_id,
            canonical_url=source_url,
            title=title,
            language=infer_language(source_url),
            source_html_object_uri=source_artifact_uri,
            provenance=[
                self._provenance(
                    "document_id",
                    document_id,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    method="regex",
                ),
                self._provenance(
                    "title",
                    title,
                    source_url=source_url,
                    source_artifact_uri=source_artifact_uri,
                    method="html_selector",
                    selector="title",
                ),
            ],
        )

    def _fallback_title(self, html: str) -> str | None:
        start = html.lower().find("<title")
        if start < 0:
            return None
        close_start = html.find(">", start)
        close_end = html.lower().find("</title>", close_start)
        if close_start < 0 or close_end < 0:
            return None
        return " ".join(html[close_start + 1 : close_end].split())

    def _provenance(
        self,
        field_path: str,
        value: str,
        *,
        source_url: str,
        source_artifact_uri: str,
        method: str,
        selector: str | None = None,
    ) -> FieldProvenance:
        return FieldProvenance(
            field_path=field_path,
            value_hash=f"sha256:{sha256(value.encode()).hexdigest()}",
            extraction_method=method,  # type: ignore[arg-type]
            source_artifact_uri=source_artifact_uri,
            source_url=source_url,
            css_selector=selector,
            extractor_version=self.parser_version,
            extracted_at=datetime.now(UTC),
            confidence=1.0,
        )
