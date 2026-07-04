from pathlib import Path

from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser

FIXTURES = Path("tests/fixtures/regjeringen/hearings")


def parse_fixture(document_id: str):
    html = (FIXTURES / document_id / "page.html").read_text(encoding="utf-8")
    url = f"https://www.regjeringen.no/no/dokumenter/example/{document_id}/"
    return HearingPageParser().parse(
        html,
        source_url=url,
        source_artifact_uri=f"file://fixtures/{document_id}/page.html",
    )


def test_parser_extracts_bokmal_hearing_detail_fields() -> None:
    document = parse_fixture("id3167072")

    assert document.document_id == "id3167072"
    assert (
        document.title
        == "Kort høring - Avskogingsforordningen og forbud mot eksport til tredjeland"
    )
    assert document.language == "nb"
    assert document.publication_date and document.publication_date.isoformat() == "2026-07-03"
    assert document.responsible_departments[0].label == "Klima- og miljødepartementet"
    assert document.status == "På høring"
    assert document.deadline and document.deadline.isoformat() == "2026-08-07"
    assert document.summary and document.summary.startswith("Denne høringen gjelder innføring")
    assert document.hearing_letter_section_id == "section-1-horingsbrev"
    assert document.hearing_note_attachment_ids == ["id3167072-attachment-1"]
    assert (
        document.submission_url
        == "https://svar.regjeringen.no/nb/registrer_horingsuttalelse/H3167072/"
    )
    assert any(theme.label == "Naturmangfold" for theme in document.themes)
    assert len(document.hearing_recipients) > 50


def test_parser_extracts_nynorsk_labels_and_provenance() -> None:
    document = parse_fixture("id3168525")

    assert document.language == "nn"
    assert document.status == "På høyring"
    assert document.hearing_letter_section_id == "section-1-hoyringsbrev"
    assert document.hearing_note_attachment_ids == ["id3168525-attachment-1"]
    assert (
        document.submission_url
        == "https://svar.regjeringen.no/nn/registrer_horingsuttalelse/H3168525/"
    )

    provenance_paths = {item.field_path for item in document.provenance}
    for field_path in [
        "document_id",
        "canonical_url",
        "document_type",
        "title",
        "language",
        "publication_date",
        "responsible_departments",
        "status",
        "deadline",
        "summary",
        "hearing_letter_section_id",
        "hearing_note_attachment_ids",
        "hearing_recipients",
        "submission_url",
    ]:
        assert field_path in provenance_paths
    assert all(item.source_artifact_uri.endswith("/page.html") for item in document.provenance)
