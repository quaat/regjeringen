from pathlib import Path

SCHEMA = Path("schema/postgres/001_metadata.sql")


def test_production_metadata_schema_contains_required_tables_and_constraints() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    for table in [
        "documents",
        "document_versions",
        "document_attachments",
        "document_sections",
        "hearing_details",
        "hearing_recipients",
        "field_provenance",
        "crawl_batches",
        "fetch_events",
        "extraction_runs",
        "parser_errors",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "CHECK ((checksum_sha256 IS NULL AND object_uri IS NULL)" in sql
    assert "UNIQUE (document_id, html_checksum_sha256, parser_version)" in sql
    assert "Large artifacts" in sql
