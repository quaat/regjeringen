"""Parser coverage helpers for fixture-backed regression tests."""

from __future__ import annotations

from pydantic import BaseModel

from sculpin_regjeringen.models.canonical import HearingDocument


class ParserCoverage(BaseModel):
    title: bool
    document_id: bool
    canonical_url: bool
    language: bool
    publication_date: bool
    department: bool
    status: bool
    deadline: bool
    summary: bool
    sections: bool
    attachments: bool
    recipients: bool
    themes: bool
    source_links: bool
    contacts: bool
    provenance: bool

    @property
    def present_count(self) -> int:
        return sum(1 for value in self.model_dump().values() if value)


def hearing_parser_coverage(document: HearingDocument) -> ParserCoverage:
    """Return field-presence coverage for a parsed hearing document."""

    return ParserCoverage(
        title=bool(document.title),
        document_id=bool(document.document_id),
        canonical_url=bool(document.canonical_url),
        language=document.language != "unknown",
        publication_date=document.publication_date is not None,
        department=bool(document.responsible_departments),
        status=bool(document.status),
        deadline=document.deadline is not None,
        summary=bool(document.summary),
        sections=bool(document.sections),
        attachments=bool(document.attachments),
        recipients=bool(document.hearing_recipients),
        themes=bool(document.themes),
        source_links=bool(document.source_links),
        contacts=bool(document.contacts),
        provenance=bool(document.provenance),
    )
