from pathlib import Path

from typer.testing import CliRunner

from sculpin_regjeringen.cli import app
from sculpin_regjeringen.parsers.hearing_parser import HearingPageParser
from sculpin_regjeringen.validation.parser_coverage import hearing_parser_coverage

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
    assert document.canonical_url == (
        "https://www.regjeringen.no/no/dokumenter/"
        "kort-horing-avskogingsforordningen-og-forbud-mot-eksport-til-tredjeland/id3167072/"
    )
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
    assert document.attachments[0].attachment_role == "hearing_note"
    assert document.attachments[0].checksum_sha256 is None
    assert document.attachments[0].object_uri is None
    assert (
        document.submission_url
        == "https://svar.regjeringen.no/nb/registrer_horingsuttalelse/H3167072/"
    )
    assert any(theme.label == "Naturmangfold" for theme in document.themes)
    assert any(link.relation == "related" for link in document.source_links)
    assert len(document.hearing_recipients) > 50
    assert any(contact.email == "postmottak@kld.dep.no" for contact in document.contacts)

    sections_by_heading = {section.heading: section for section in document.sections}
    assert sections_by_heading["Høringsbrev"].visible_text
    assert sections_by_heading["Høringsnotat"].visible_text == "Høringsnotat (pdf)"
    assert "Animalia" in (sections_by_heading["Høringsinstanser"].visible_text or "")


def test_parser_extracts_nynorsk_labels_and_item_provenance() -> None:
    document = parse_fixture("id3168525")

    assert document.canonical_url == (
        "https://www.regjeringen.no/no/dokumenter/"
        "hoyring-framlegg-om-presiseringar-i-reglane-om-nav-si-opplysingsplikt-"
        "overfor-skattestyresmaktene/id3168525/"
    )
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
        "responsible_departments[0].label",
        "status",
        "deadline",
        "summary",
        "sections[0].heading",
        "sections[0].visible_text",
        "attachments[0].source_url",
        "attachments[0].attachment_role",
        "hearing_letter_section_id",
        "hearing_note_attachment_ids[0]",
        "hearing_recipients[0].label",
        "themes[0].label",
        "themes[0].uri",
        "source_links[0].url",
        "contacts[0].label",
        "submission_url",
    ]:
        assert field_path in provenance_paths
    assert all(item.source_artifact_uri.endswith("/page.html") for item in document.provenance)
    assert all(item.css_selector for item in document.provenance)


def test_parser_falls_back_from_canonical_to_og_and_dc_identifier_url() -> None:
    html = """
    <html lang="no"><head>
      <meta property="og:url" content="/no/dokumenter/og-url/id9999000/">
      <meta name="DC.Identifier.URL" content="/no/dokumenter/dc-url/id9999000/">
    </head><body>
      <h1>Høring uten canonical</h1>
      <div class="article-info"><p><span class="date">Dato: 01.02.2026</span></p></div>
    </body></html>
    """
    document = HearingPageParser().parse(
        html,
        source_url="https://www.regjeringen.no/no/dokumenter/source/id9999000/",
        source_artifact_uri="memory://og",
    )
    assert document.canonical_url == "https://www.regjeringen.no/no/dokumenter/og-url/id9999000/"

    dc_only = html.replace(
        '<meta property="og:url" content="/no/dokumenter/og-url/id9999000/">', ""
    )
    document = HearingPageParser().parse(
        dc_only,
        source_url="https://www.regjeringen.no/no/dokumenter/source/id9999000/",
        source_artifact_uri="memory://dc",
    )
    assert document.canonical_url == "https://www.regjeringen.no/no/dokumenter/dc-url/id9999000/"


def test_parser_handles_missing_deadline_and_attachment_role_variants() -> None:
    html = """
    <html lang="nb"><head>
      <link rel="canonical" href="/no/dokumenter/variant/id9999001/">
    </head><body><main id="mainContent">
      <h1>Høring med vedlegg</h1>
      <div class="article-info"><p>
        <span class="type">Høring</span>
        <span class="date">Dato: 02.03.2026</span>
      </p></div>
      <div class="article-body">
        <div class="horing-meta"><p>Status: På høring</p></div>
        <div class="factbox">
          <h2 class="factbox-title">Høringsbrev</h2>
          <div class="factbox-content"><a href="/brev.pdf">Høringsbrev</a></div>
        </div>
        <div class="factbox">
          <h2 class="factbox-title">Vedlegg</h2>
          <div class="factbox-content"><a href="/vedlegg.pdf">Vedlegg 1</a></div>
        </div>
        <div class="factbox">
          <h2 class="factbox-title">Skjema</h2>
          <div class="factbox-content"><a href="/skjema.docx">Skjema</a></div>
        </div>
        <div class="factbox">
          <h2 class="factbox-title">Annet</h2>
          <div class="factbox-content"><a href="/annet.pdf">Annet</a></div>
        </div>
      </div>
    </main></body></html>
    """
    document = HearingPageParser().parse(
        html,
        source_url="https://www.regjeringen.no/no/dokumenter/source/id9999001/",
        source_artifact_uri="memory://variant",
    )

    assert document.deadline is None
    assert [attachment.attachment_role for attachment in document.attachments] == [
        "hearing_letter",
        "appendix",
        "form",
        "unknown",
    ]


def test_parser_coverage_reports_required_presence_for_current_fixtures() -> None:
    for document_id in ["id3167072", "id3168525"]:
        coverage = hearing_parser_coverage(parse_fixture(document_id))
        assert coverage.title
        assert coverage.document_id
        assert coverage.canonical_url
        assert coverage.language
        assert coverage.publication_date
        assert coverage.department
        assert coverage.status
        assert coverage.deadline
        assert coverage.summary
        assert coverage.sections
        assert coverage.attachments
        assert coverage.recipients
        assert coverage.themes
        assert coverage.source_links
        assert coverage.contacts
        assert coverage.provenance


def test_parse_fixture_cli_prints_json_and_writes_output(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = FIXTURES / "id3167072" / "page.html"

    result = runner.invoke(app, ["parse-fixture", str(fixture), "--document-type", "hearing"])
    assert result.exit_code == 0
    assert '"document_id": "id3167072"' in result.stdout
    assert "kort-horing-avskogingsforordningen" in result.stdout

    output = tmp_path / "parsed.json"
    result = runner.invoke(
        app,
        ["parse-fixture", str(fixture), "--document-type", "hearing", "--output", str(output)],
    )
    assert result.exit_code == 0
    assert output.exists()
    assert '"document_id": "id3167072"' in output.read_text(encoding="utf-8")


def test_parse_fixture_cli_rejects_unsupported_document_type() -> None:
    runner = CliRunner()
    fixture = FIXTURES / "id3167072" / "page.html"

    result = runner.invoke(app, ["parse-fixture", str(fixture), "--document-type", "nou"])

    assert result.exit_code == 2
    assert "Unsupported document type: nou" in result.stderr
