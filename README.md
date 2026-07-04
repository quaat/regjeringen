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
