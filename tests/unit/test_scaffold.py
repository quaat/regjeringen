from datetime import UTC, datetime

from sculpin_regjeringen.models.canonical import HearingDocument
from sculpin_regjeringen.models.provenance import FieldProvenance
from sculpin_regjeringen.parsers.html_common import extract_document_id


def test_extract_document_id_from_regjeringen_url() -> None:
    assert (
        extract_document_id(
            "https://www.regjeringen.no/no/dokumenter/horing-register/id3151708/"
        )
        == "id3151708"
    )


def test_hearing_document_accepts_field_level_provenance() -> None:
    provenance = FieldProvenance(
        field_path="title",
        value_hash="sha256:abc",
        extraction_method="html_selector",
        source_artifact_uri="s3://bucket/page.html",
        source_url="https://www.regjeringen.no/no/dokumenter/example/id3151708/",
        extractor_version="regjeringen-parser-0.1.0",
        extracted_at=datetime.now(UTC),
    )
    document = HearingDocument(
        document_id="id3151708",
        canonical_url="https://www.regjeringen.no/no/dokumenter/example/id3151708/",
        title="Example hearing",
        language="nb",
        source_html_object_uri="s3://bucket/page.html",
        provenance=[provenance],
    )

    assert document.document_type == "hearing"
    assert document.provenance[0].field_path == "title"
