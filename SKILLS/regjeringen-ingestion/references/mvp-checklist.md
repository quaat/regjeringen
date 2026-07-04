# MVP Checklist

Use this checklist when implementing or reviewing the hearing-only milestone.

## Source Audit

- Fetch and summarize `robots.txt`.
- Record sitemap availability and relevant URL patterns.
- Inspect category listing pagination and avoid disallowed filter/query URLs.
- Save representative fixtures across departments, years, statuses, and Bokmal/Nynorsk pages.
- Build a field availability matrix for title, URL, `id...`, document type, date, department, status, deadline, summary, sections, attachments, recipients, responses link, themes, related links, and contact details.
- Keep hearing responses as metadata/link-only until legal review approves deeper harvesting.

## Parser

- Extract `document_id` from canonical URL or detail URL.
- Extract title from `h1`, not only `<title>`.
- Segment visible content by `h2`/`h3` headings.
- Classify attachments deterministically from label, filename, extension, and surrounding heading.
- Normalize language, dates, statuses, departments, and themes.
- Emit `FieldProvenance` for every extracted value.
- Preserve parser version and source artifact URI.

## Graph Export

- Include document identity, type, title, date, departments, themes, status, deadline, attachments, sections, relations, and provenance links.
- Link to source artifacts and source spans.
- Keep full text, complete PDFs, and bulk extracted chunks outside the graph.
- Validate exported graph with SHACL once shapes are available.

## Agent Tools

- Start with `search_government_documents` and `get_government_document`.
- Return citations or source pointers for any answer based on extracted content.
- Support filters for department, status, deadline, theme, and document type.
