"""Canonical model to RDF mapping scaffold."""

from __future__ import annotations

from sculpin_regjeringen.models.canonical import GovernmentDocument
from sculpin_regjeringen.models.graph import GraphExport, GraphNamespace, Triple

SCGOV = "https://w3id.org/sculpin/government/regjeringen#"
DCTERMS = "http://purl.org/dc/terms/"
PROV = "http://www.w3.org/ns/prov#"


def document_to_graph(document: GovernmentDocument) -> GraphExport:
    subject = f"scgov-doc:{document.document_id}"
    return GraphExport(
        document_id=document.document_id,
        namespaces=[
            GraphNamespace(prefix="scgov", iri=SCGOV),
            GraphNamespace(prefix="dcterms", iri=DCTERMS),
            GraphNamespace(prefix="prov", iri=PROV),
        ],
        triples=[
            Triple(subject=subject, predicate="a", object=f"scgov:{document.document_type}"),
            Triple(
                subject=subject,
                predicate="dcterms:identifier",
                object=document.document_id,
                object_type="literal",
            ),
            Triple(
                subject=subject,
                predicate="dcterms:title",
                object=document.title,
                object_type="literal",
                language=None if document.language == "unknown" else document.language,
            ),
        ],
    )
