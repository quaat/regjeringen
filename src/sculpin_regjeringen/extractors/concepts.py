"""AI-assisted concept extraction scaffold."""

from __future__ import annotations


class ConceptExtractor:
    def propose(self, text: str, *, source_span_id: str) -> list[object]:
        raise NotImplementedError("Concept extraction requires source spans and review workflow.")
