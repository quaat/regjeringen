"""Canonical document models shared by crawlers, parsers, storage, and graph export."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from sculpin_regjeringen.models.provenance import FieldProvenance

DocumentType = Literal["hearing", "input", "proposition", "storting_message", "nou"]
LanguageCode = Literal["nb", "nn", "en", "se", "unknown"]


class DepartmentRef(BaseModel):
    label: str
    uri: str | None = None


class ThemeRef(BaseModel):
    label: str
    uri: str | None = None


class OrganizationRef(BaseModel):
    label: str
    uri: str | None = None


class ContactPoint(BaseModel):
    label: str
    email: str | None = None
    phone: str | None = None
    organization: str | None = None


class SourceLink(BaseModel):
    url: str
    label: str | None = None
    relation: str | None = None


class ExtractedReference(BaseModel):
    raw_text: str
    reference_type: str
    normalized_id: str | None = None
    source_span_id: str | None = None
    provenance: list[FieldProvenance] = Field(default_factory=list)


class DocumentSection(BaseModel):
    section_id: str
    heading: str
    heading_path: list[str] = Field(default_factory=list)
    visible_text: str | None = None
    text_object_uri: str | None = None
    source_span_id: str | None = None
    provenance: list[FieldProvenance] = Field(default_factory=list)


class Attachment(BaseModel):
    attachment_id: str
    document_id: str
    source_url: str
    final_url: str | None = None
    original_label: str
    original_filename: str | None = None
    normalized_filename: str
    media_type: str | None = None
    file_extension: str | None = None
    size_label: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    object_uri: str | None = None
    attachment_role: Literal[
        "hearing_note",
        "hearing_letter",
        "main_document",
        "appendix",
        "report",
        "form",
        "unknown",
    ] = "unknown"
    extracted_text_uri: str | None = None
    provenance: list[FieldProvenance] = Field(default_factory=list)


class GovernmentDocument(BaseModel):
    document_id: str
    canonical_url: str
    source_site: Literal["regjeringen.no"] = "regjeringen.no"
    document_type: DocumentType
    title: str
    subtitle: str | None = None
    summary: str | None = None
    language: LanguageCode = "unknown"
    publication_date: date | None = None
    updated_date: date | None = None
    responsible_departments: list[DepartmentRef] = Field(default_factory=list)
    themes: list[ThemeRef] = Field(default_factory=list)
    status: str | None = None
    normalized_status: str | None = None
    deadline: date | None = None
    document_number: str | None = None
    parliamentary_session: str | None = None
    reference_number: str | None = None
    source_html_object_uri: str
    extracted_text_object_uri: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    sections: list[DocumentSection] = Field(default_factory=list)
    contacts: list[ContactPoint] = Field(default_factory=list)
    source_links: list[SourceLink] = Field(default_factory=list)
    references: list[ExtractedReference] = Field(default_factory=list)
    provenance: list[FieldProvenance] = Field(default_factory=list)


class HearingDocument(GovernmentDocument):
    document_type: Literal["hearing"] = "hearing"
    hearing_status: str | None = None
    hearing_deadline: date | None = None
    hearing_letter_section_id: str | None = None
    hearing_note_attachment_ids: list[str] = Field(default_factory=list)
    hearing_recipients: list[OrganizationRef] = Field(default_factory=list)
    submission_url: str | None = None
    hearing_responses_url: str | None = None


class PropositionDocument(GovernmentDocument):
    document_type: Literal["proposition"] = "proposition"
    proposition_number: str
    proposition_kind: Literal["L", "S", "LS", "unknown"] = "unknown"
    parliamentary_session: str
    storting_case_url: str | None = None
    affected_laws: list[ExtractedReference] = Field(default_factory=list)


class StortingMessageDocument(GovernmentDocument):
    document_type: Literal["storting_message"] = "storting_message"
    message_number: str
    parliamentary_session: str
    main_policy_area: str | None = None
    chapters: list[DocumentSection] = Field(default_factory=list)


class NouDocument(GovernmentDocument):
    document_type: Literal["nou"] = "nou"
    nou_year: int
    nou_number: int
    committee_name: str | None = None
    mandate_section_id: str | None = None
    recommendations_section_ids: list[str] = Field(default_factory=list)
    appendices: list[Attachment] = Field(default_factory=list)
