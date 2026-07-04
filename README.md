# Sculpin regjeringen.no ingestion

Python module scaffold for turning `regjeringen.no` document pages into provenance-rich Sculpin knowledge assets.

The implementation follows `devel_plan.md` and starts with a hearing-only MVP:

- discover allowed hearing pages from public listings and sitemap data
- fetch and archive raw HTML and attachments
- parse canonical document metadata with field-level provenance
- store raw/extracted artifacts outside the graph
- export metadata, links, concepts, and source pointers to Sculpin

## Project layout

```text
src/sculpin_regjeringen/   Python package
tests/                     Unit, parser, integration tests, and fixtures
reports/                   Source-audit and parser-coverage reports
data/                      Local development artifact storage
SKILLS/                    Project-local Codex skills
AGENT.md                   Agent operating instructions for this project
```

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Planned CLI entry points:

```bash
sculpin-regjeringen audit-sources --categories hearing --sample-size 50 --output reports/source-audit.md
sculpin-regjeringen parse-fixture tests/fixtures/regjeringen/hearings/id3151708/page.html --document-type hearing
sculpin-regjeringen export-graph --document-id id3151708 --format turtle --output tmp/id3151708.ttl
```

## Local fixture-to-graph workflow

The hearing-only MVP can now parse a saved fixture, write immutable local artifacts,
upsert lightweight metadata, and optionally export graph-safe Turtle:

```bash
sculpin-regjeringen process-fixture \
  tests/fixtures/regjeringen/hearings/id3167072/page.html \
  --artifact-root data/local-artifacts \
  --metadata-db data/local-metadata/metadata.json \
  --graph-output tmp/id3167072.ttl
```

This writes raw HTML, canonical `document.json`, section text files, and a manifest to
a local SHA-256 content-addressed object layout. Attachment files remain metadata-only
until the downloader phase. The graph export contains metadata and source/text-object
pointers only; raw HTML, section text, attachment bytes, extracted full text, and chunks
remain outside the graph.

You can also export Turtle directly from a canonical JSON file or fixture:

```bash
sculpin-regjeringen export-graph --document-json tmp/document.json --output tmp/document.ttl
sculpin-regjeringen export-graph \
  --fixture tests/fixtures/regjeringen/hearings/id3167072/page.html \
  --output tmp/id3167072.ttl
```
