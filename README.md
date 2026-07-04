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

Implemented local CLI entry points:

```bash
sculpin-regjeringen audit-sources --categories hearing --sample-size 50 --output reports/source-audit.md
sculpin-regjeringen parse-fixture tests/fixtures/regjeringen/hearings/id3167072/page.html --document-type hearing
sculpin-regjeringen process-fixture tests/fixtures/regjeringen/hearings/id3167072/page.html --graph-output tmp/id3167072.ttl
sculpin-regjeringen export-graph --fixture tests/fixtures/regjeringen/hearings/id3167072/page.html --output tmp/id3167072.ttl
sculpin-regjeringen export-graph --document-json tmp/document.json --output tmp/document.ttl
```

The current production slice adds fixture/test-backed attachment downloading and a PostgreSQL metadata schema under `schema/postgres/001_metadata.sql`. Planned later CLI work includes production batch orchestration, PDF/DOCX text extraction, graph publication to Sculpin, and agent-facing search tools.

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

By default this remains offline: it writes raw HTML, canonical `document.json`, section text files, and a manifest to a local SHA-256 content-addressed object layout without fetching attachment bytes. Enable live attachment downloads explicitly with `--download-attachments` and, for tests or strict runs, optionally `--attachment-fail-fast`. Live downloads respect robots policy by default; use `--no-respect-robots` only for controlled tests.

Downloaded attachments are stored as immutable object-store bytes and the canonical document records only `final_url`, `checksum_sha256`, `size_bytes`, `media_type`, and `object_uri`. PostgreSQL stores normalized document metadata, attachment metadata, provenance, extraction runs, and attachment download events. Graph export contains metadata plus source/object pointers only; raw HTML, section text, attachment bytes, extracted full text, and chunks remain outside the graph.

Idempotency boundary for this local workflow:

- raw HTML object URIs are stable for identical fixture bytes,
- section text object URIs are stable for identical extracted section text,
- metadata document/version records are idempotent for the same `document_id`, HTML checksum, and parser version,
- manifest and canonical JSON artifact URIs may be run-specific because they include timestamps and provenance extraction timestamps.

You can also export Turtle directly from a canonical JSON file or fixture:

```bash
sculpin-regjeringen export-graph --document-json tmp/document.json --output tmp/document.ttl
sculpin-regjeringen export-graph \
  --fixture tests/fixtures/regjeringen/hearings/id3167072/page.html \
  --output tmp/id3167072.ttl
```

## Hearing batch ingestion

Live hearing ingestion is explicit and production-shaped, but still bounded to graph-safe local exports. Use `ingest-hearings` with either one or more explicit hearing URLs or a newline-delimited URL file:

```bash
sculpin-regjeringen ingest-hearings \
  --url https://www.regjeringen.no/no/dokumenter/example/id3167072/ \
  --artifact-root data/local-artifacts \
  --metadata-db data/local-metadata/metadata.json \
  --graph-output-dir tmp/graphs
```

```bash
sculpin-regjeringen ingest-hearings \
  --url-file tmp/hearing-urls.txt \
  --artifact-root data/local-artifacts \
  --postgres-dsn "$REGJERINGEN_POSTGRES_DSN" \
  --graph-output-dir tmp/graphs
```

Attachment bytes are never downloaded unless requested. When enabled, supported attachments are stored as immutable object-store objects and represented in canonical JSON, metadata, and Turtle only by safe metadata such as checksum, size, media type, URL, and object URI:

```bash
sculpin-regjeringen ingest-hearings \
  --url-file tmp/hearing-urls.txt \
  --artifact-root data/local-artifacts \
  --metadata-db data/local-metadata/metadata.json \
  --download-attachments \
  --respect-robots \
  --graph-output-dir tmp/graphs
```

The command respects `regjeringen.no` robots policy by default, uses a clear user agent, enforces a concurrency limit, records per-URL failures in a batch manifest, and continues past failed pages unless `--fail-fast` is set. The summary printed by the command includes attempted/succeeded/failed page counts, attachment downloaded/skipped/failed counts, the metadata backend, artifact root, graph output directory, and batch manifest URI.

Metadata backend selection is explicit: `--postgres-dsn` uses PostgreSQL, `--metadata-db` uses the local JSON store, and omitting both still writes object artifacts, document manifests, graph files when requested, and a batch manifest. Supplying both metadata flags is rejected.

The graph/object-store safety boundary remains unchanged: Turtle output contains metadata and source/object pointers only. Raw HTML, raw attachment bytes, full section text, extracted full text, chunks, embeddings, and vector indexes are not written to the graph.

Deferred Phase 3 work still includes PDF/DOCX full-text extraction, OCR, chunking, vector indexes, embedding storage, agent-facing semantic search tools, and Sculpin backend publication beyond local graph-safe export files/manifests.
