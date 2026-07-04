"""Data quality checks for canonical documents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sculpin_regjeringen.models.canonical import GovernmentDocument


class QualityFinding(BaseModel):
    code: str
    message: str
    severity: str = "error"
    field_path: str | None = None


def validate_required_document_fields(document: GovernmentDocument) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    if not document.document_id:
        findings.append(QualityFinding(code="missing_document_id", message="Missing document id"))
    if not document.title:
        findings.append(QualityFinding(code="missing_title", message="Missing title"))
    if not document.source_html_object_uri:
        findings.append(
            QualityFinding(
                code="missing_source_artifact",
                message="Missing source HTML object URI",
                field_path="source_html_object_uri",
            )
        )
    return findings


class CoverageReport(BaseModel):
    total_documents: int = 0
    findings: list[QualityFinding] = Field(default_factory=list)
