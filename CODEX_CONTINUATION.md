# Codex Continuation Instruction

Continue this project by treating `devel_plan.md` as the source of truth for architecture, sequencing, and acceptance criteria. Also read `README.md`, `AGENT.md`, and `SKILLS/regjeringen-ingestion/SKILL.md` before making changes.

Current state:

- The repository scaffold exists for the Sculpin `regjeringen.no` ingestion module.
- The first scraper slice is implemented: robots-aware source audit, hearing listing discovery, detail-page audit inspection, fixture saving, and Markdown/JSON audit reporting.
- A small live audit was run and saved reports plus fixtures under `reports/` and `tests/fixtures/regjeringen/`.
- Validation currently passes with:

```bash
.venv/bin/ruff check . --no-cache
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider
```

Recommended next task:

1. Implement the fixture-backed hearing detail parser described in `devel_plan.md` sections 6.3, 7, 13, 18, and 20.
2. Parse saved hearing detail fixtures into `HearingDocument`.
3. Extract title, URL, stable `id...`, document type, publication date, departments, status, deadline, summary, hearing letter section, hearing note attachment links, recipients, response/submission links, themes, related links, contact details, headings, language, canonical URL, and update signals.
4. Emit `FieldProvenance` for every extracted field.
5. Add parser fixture tests before broadening behavior.
6. Keep hearing response harvesting link-only unless explicitly approved after legal/compliance review.
7. Keep large source content out of the graph; store raw HTML, attachments, full text, chunks, and logs outside graph storage.

Do not broaden to `Innspill`, `Prop.`, `Meld. St.`, or `NOU` until the hearing parser and provenance model are stable.
