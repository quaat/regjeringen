"""Parser interfaces."""

from __future__ import annotations

from typing import Protocol

from sculpin_regjeringen.models.canonical import GovernmentDocument


class DocumentParser(Protocol):
    def parse(self, html: str, *, source_url: str, source_artifact_uri: str) -> GovernmentDocument:
        """Parse a source artifact into a canonical document."""
