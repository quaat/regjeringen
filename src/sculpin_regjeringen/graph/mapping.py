"""Canonical model to RDF mapping."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, XSD

from sculpin_regjeringen.models.canonical import GovernmentDocument, HearingDocument

SCGOV = Namespace("https://w3id.org/sculpin/government/regjeringen#")
SCGOV_DOC = Namespace("https://w3id.org/sculpin/government/regjeringen/document/")
SCGOV_ATTACHMENT = Namespace("https://w3id.org/sculpin/government/regjeringen/attachment/")
SCGOV_SECTION = Namespace("https://w3id.org/sculpin/government/regjeringen/section/")
SCGOV_ORG = Namespace("https://w3id.org/sculpin/government/regjeringen/org/")
PROV = Namespace("http://www.w3.org/ns/prov#")


def document_to_graph(document: GovernmentDocument) -> Graph:
    """Export document metadata and source pointers, never full extracted text."""

    graph = Graph()
    graph.bind("scgov", SCGOV)
    graph.bind("dcterms", DCTERMS)
    graph.bind("prov", PROV)
    doc_uri = _document_uri(document.document_id)
    graph.add((doc_uri, RDF.type, SCGOV.GovernmentDocument))
    graph.add(
        (
            doc_uri,
            RDF.type,
            SCGOV.Consultation if document.document_type == "hearing" else SCGOV.Document,
        )
    )
    graph.add((doc_uri, DCTERMS.identifier, Literal(document.document_id)))
    graph.add((doc_uri, DCTERMS.title, Literal(document.title, lang=_lang(document.language))))
    graph.add((doc_uri, SCGOV.canonicalUrl, URIRef(document.canonical_url)))
    graph.add((doc_uri, SCGOV.sourceHtmlObjectUri, URIRef(document.source_html_object_uri)))
    graph.add((doc_uri, DCTERMS.language, Literal(document.language)))
    if document.publication_date is not None:
        graph.add(
            (
                doc_uri,
                DCTERMS.issued,
                Literal(document.publication_date.isoformat(), datatype=XSD.date),
            )
        )
    if document.status:
        graph.add((doc_uri, SCGOV.status, Literal(document.status)))
    if document.deadline is not None:
        graph.add(
            (doc_uri, SCGOV.deadline, Literal(document.deadline.isoformat(), datatype=XSD.date))
        )

    for department in document.responsible_departments:
        dept_uri = URIRef(department.uri or f"{SCGOV_ORG}{quote(department.label)}")
        graph.add((doc_uri, SCGOV.responsibleDepartment, dept_uri))
        graph.add((dept_uri, RDF.type, SCGOV.Department))
        graph.add((dept_uri, DCTERMS.title, Literal(department.label)))

    for theme in document.themes:
        theme_uri = URIRef(theme.uri or f"{SCGOV}theme/{quote(theme.label)}")
        graph.add((doc_uri, SCGOV.theme, theme_uri))
        graph.add((theme_uri, DCTERMS.title, Literal(theme.label)))

    for section in document.sections:
        section_uri = URIRef(
            f"{SCGOV_SECTION}{quote(document.document_id)}/{quote(section.section_id)}"
        )
        graph.add((doc_uri, SCGOV.hasSection, section_uri))
        graph.add((section_uri, RDF.type, SCGOV.DocumentSection))
        graph.add((section_uri, DCTERMS.title, Literal(section.heading)))
        if section.text_object_uri:
            graph.add((section_uri, SCGOV.textObjectUri, URIRef(section.text_object_uri)))
        for provenance in section.provenance:
            graph.add((section_uri, PROV.wasDerivedFrom, URIRef(provenance.source_artifact_uri)))

    for attachment in document.attachments:
        attachment_uri = URIRef(f"{SCGOV_ATTACHMENT}{quote(attachment.attachment_id)}")
        graph.add((doc_uri, SCGOV.hasAttachment, attachment_uri))
        graph.add((attachment_uri, RDF.type, SCGOV.Attachment))
        graph.add((attachment_uri, DCTERMS.title, Literal(attachment.original_label)))
        graph.add((attachment_uri, SCGOV.sourceUrl, URIRef(attachment.source_url)))
        graph.add((attachment_uri, SCGOV.attachmentRole, Literal(attachment.attachment_role)))
        if attachment.object_uri:
            graph.add((attachment_uri, SCGOV.objectUri, URIRef(attachment.object_uri)))

    if isinstance(document, HearingDocument):
        _add_hearing_extension(graph, doc_uri, document)

    for link in document.source_links:
        link_uri = URIRef(link.url)
        graph.add((doc_uri, SCGOV.sourceLink, link_uri))
        if link.label:
            graph.add((link_uri, DCTERMS.title, Literal(link.label)))
        if link.relation:
            graph.add((link_uri, SCGOV.linkRelation, Literal(link.relation)))

    for provenance in document.provenance:
        graph.add((doc_uri, PROV.wasDerivedFrom, URIRef(provenance.source_artifact_uri)))
        graph.add((doc_uri, SCGOV.hasProvenanceField, Literal(provenance.field_path)))
    return graph


def serialize_document_turtle(document: GovernmentDocument, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document_to_graph(document).serialize(format="turtle"), encoding="utf-8")


def _add_hearing_extension(graph: Graph, doc_uri: URIRef, document: HearingDocument) -> None:
    if document.hearing_deadline is not None:
        graph.add(
            (
                doc_uri,
                SCGOV.hearingDeadline,
                Literal(document.hearing_deadline.isoformat(), datatype=XSD.date),
            )
        )
    if document.hearing_status:
        graph.add((doc_uri, SCGOV.hearingStatus, Literal(document.hearing_status)))
    if document.submission_url:
        graph.add((doc_uri, SCGOV.submissionUrl, URIRef(document.submission_url)))
    if document.hearing_responses_url:
        graph.add((doc_uri, SCGOV.hearingResponsesUrl, URIRef(document.hearing_responses_url)))
    for recipient in document.hearing_recipients:
        recipient_uri = URIRef(recipient.uri or f"{SCGOV_ORG}{quote(recipient.label)}")
        graph.add((doc_uri, SCGOV.hearingRecipient, recipient_uri))
        graph.add((recipient_uri, RDF.type, SCGOV.HearingRecipient))
        graph.add((recipient_uri, DCTERMS.title, Literal(recipient.label)))


def _document_uri(document_id: str) -> URIRef:
    return URIRef(f"{SCGOV_DOC}{quote(document_id)}")


def _lang(language: str) -> str | None:
    return None if language == "unknown" else language
