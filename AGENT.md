# Agent Instructions

Use `devel_plan.md` as the source of truth for architecture, scope, and sequencing. The first milestone is a hearing-only source audit and parser prototype.

## Project Priorities

- Keep large source content out of the graph. Store raw HTML, PDFs, DOCX files, extracted text, chunks, and parser logs in external storage.
- Put metadata, semantic links, normalized concepts, provenance, validation state, and source pointers in the graph.
- Start with `Horinger / Hoyringar`; do not broaden to `Innspill`, `Prop.`, `Meld. St.`, or `NOU` until the hearing parser and provenance model are stable.
- Preserve field-level provenance for every extracted field.
- Respect `robots.txt`, avoid disallowed `/api/*` and disallowed query/filter URLs, and use conservative crawl rates.
- Treat hearing response harvesting as separately approved work because it can involve personal data and retention questions.

## Implementation Rules

- Prefer deterministic selectors, headings, regexes, and controlled vocabularies before AI extraction.
- Add parser fixtures before broadening extraction logic.
- Make re-runs idempotent by using stable document IDs, content checksums, parser versions, and crawl batch IDs.
- Keep module boundaries aligned with the scaffold:
  - `crawler/` for discovery, robots policy, fetching, and category crawlers.
  - `parsers/` for HTML/detail/attachment parsing.
  - `extractors/` for PDF, DOCX, references, and concepts.
  - `models/` for canonical Pydantic models and graph payloads.
  - `storage/` for object, relational, and analytical stores.
  - `graph/` for RDF mapping, SPARQL templates, and SHACL.
  - `agents/` for Sculpin-facing tools.
  - `validation/` for data quality and review queue logic.

## Quality Bar

- Unit tests cover URL normalization, ID extraction, date parsing, status normalization, and reference regexes.
- Parser tests use saved fixtures and expected normalized JSON.
- Integration tests cover crawler to storage to parser to graph export once those pieces exist.
- Parser changes should report field coverage and drift against fixture output.
- AI-derived concepts must include source spans and remain proposed until reviewed.

## Local Skills

Use `SKILLS/regjeringen-ingestion` for repeatable project workflows and domain-specific guidance. Keep that skill concise and move detailed checklists or schemas into its `references/` folder.
