# Implementation plan: Sculpin ingestion and knowledge organization for `regjeringen.no`

## 1. Executive summary

Build a Sculpin module that turns official Norwegian government document pages into governed, searchable, provenance-rich knowledge assets.

The core principle should be:

> **Store large source content outside the graph; store metadata, semantic links, provenance, concepts, relations, and source pointers in the graph.**

The current `regjeringen.no` document pages are suitable for this approach because the public listing pages expose stable-looking document URLs, category filters, dates, departments, topics, status/deadline fields for hearings and input processes, and detail pages with structured headings such as `Høringsbrev`, `Høringsnotat`, `Høringsinstanser`, `Tema`, `Relatert`, and `Kontakt`. For example, a hearing detail page exposes title, document type, date, department, status, deadline, hearing letter, hearing note PDF, hearing recipients, hearing responses link, topic, related links, and contact information. ([Regjeringen.no][1])

The ingestion system should start with `Høringer / Høyringar`, then generalize to `Innspill / Innspel`, `Prop.`, `Meld. St.`, and `NOU`. As of the inspected pages, the site exposes large but manageable category volumes: `Høyringar` shows 6,960 items, `Proposisjonar` 5,765, `Meldingar` 1,161, `NOU-ar` 775, and `Innspel` 48. ([Regjeringen.no][2])

A production-ready design should use:

| Layer                   | Responsibility                                                                 |
| ----------------------- | ------------------------------------------------------------------------------ |
| **Crawler/fetcher**     | Polite discovery, fetching, checksums, retries, incremental updates            |
| **Raw archive**         | Immutable HTML, headers, PDFs, DOCX, assets, parser logs                       |
| **Parser/extractor**    | Deterministic metadata extraction first, document text and section extraction  |
| **Canonical model**     | One normalized model across document types, with type-specific extensions      |
| **External text store** | Full text, chunks, PDF pages, extracted sections, tables                       |
| **Knowledge graph**     | Metadata, document relations, provenance, concepts, citations, source pointers |
| **Search/vector layer** | Full-text and semantic retrieval over chunks and attachments                   |
| **Validation workflow** | Human review for ontology additions and AI-derived facts                       |
| **Sculpin agent tools** | Search, retrieve, compare, summarize, query graph, track deadlines             |

---

## 2. Scope and document categories

### Initial document categories

| Category             | URL                                                         | Key characteristics                                                                                    |
| -------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `Høring / Høyring`   | `https://www.regjeringen.no/no/dokument/hoyringar/id1763/`  | Consultations with status, deadline, hearing letter, hearing note, recipients, attachments, responses  |
| `Innspill / Innspel` | `https://www.regjeringen.no/no/dokument/innspel/id3015054/` | Earlier/lighter input processes, often with deadline and open/closed status                            |
| `Prop.`              | `https://www.regjeringen.no/no/dokument/prop/id1753/`       | Propositions to Stortinget, document number, session, legal/budget proposals, Storting processing link |
| `Meld. St.`          | `https://www.regjeringen.no/no/dokument/meldst/id1754/`     | White-paper style reports to Stortinget, session references, chapters, PDFs/Word                       |
| `NOU`                | `https://www.regjeringen.no/no/dokument/nou-ar/id1767/`     | Public committee reports, often large, numbered, structured, with recommendations and appendices       |

### Category-specific observations

`Høyringar` are explicitly described as a way for citizens, organizations, and businesses to express views and control public administration. The listing page has topic filters and result rows with publication date, document type, department, deadline, and status. ([Regjeringen.no][2])

`Innspel` are described as a way to involve citizens, organizations, and business early in an investigation. The inspected listing shows document type, department, deadline, and status such as `Åpen`, `Ope`, `Lukket`, and `Lukket`. ([Regjeringen.no][3])

`Proposisjonar til Stortinget` are used when the government proposes that Stortinget should make a decision, and the category page indicates full-text availability from 1997/98 onward, with some documents from 1995/96. ([Regjeringen.no][4])

`Meldingar til Stortinget` are used when the government presents matters to Stortinget without proposing a decision, and also when withdrawing a legislative proposal. ([Regjeringen.no][5])

`NOU-ar` are public committee reports or investigations, with full text from 1994 and references to older scanned documents via National Library sources. ([Regjeringen.no][6])

---

## 3. Source analysis and discovery strategy

### 3.1 Source audit before implementation

The first technical task should be a **source audit**, not a crawler. It should produce a concrete report covering:

| Audit area        | What to inspect                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------ |
| `robots.txt`      | Allowed/disallowed URL patterns, sitemap references                                        |
| Sitemap           | Whether document URLs can be discovered from sitemap files                                 |
| Listing pages     | Pagination, item count, stable selectors, date sorting                                     |
| Query parameters  | Whether filter URLs can be crawled or should be avoided                                    |
| Detail pages      | Common headings, metadata blocks, attachments, related links                               |
| Asset URLs        | PDF/DOCX patterns, redirects, file names, content types                                    |
| Language variants | `no`, `nb`, `nn`, `en`, Sámi variants where applicable                                     |
| Structured data   | `meta`, JSON-LD, OpenGraph, canonical URL, hidden fields                                   |
| Update signals    | `Last-Modified`, `ETag`, canonical URL, content checksum                                   |
| Hearing responses | Whether response pages are directly linked, public, and technically appropriate to collect |

Important constraint: `robots.txt` currently disallows `/api/*`, language-specific `/api/*`, the historical archive paths, and many query-parameter filter URLs such as `?documenttype`, `?topic`, `?ownerid`, `?from`, `?to`, `?sortby`, `?pageRef`, and `?q`. It also exposes a sitemap at `https://www.regjeringen.no/globalassets/sitemap/sitemap.xml`. ([Regjeringen.no][7])

### 3.2 Discovery strategy

Use a layered discovery approach:

1. **Sitemap discovery**

   * Fetch sitemap index and relevant sitemap files.
   * Extract URLs under `/no/dokumenter/`, `/no/dokument/`, `/en/`, `/nb/`, `/nn/` where relevant.
   * Classify URLs by category using path, breadcrumb, page metadata, and page content.

2. **Category listing discovery**

   * Start from the five category URLs.
   * Parse visible results and pagination.
   * Avoid crawling disallowed filter URLs.
   * Prefer unfiltered, date-sorted category pages if permitted.
   * Store discovered detail URLs with `category_source_url`, `list_page_number`, `discovered_at`, and `crawl_batch_id`.

3. **Detail-page self-classification**

   * Never rely only on listing category.
   * Reclassify each detail page using:

     * breadcrumb
     * visible document type line
     * title pattern, such as `NOU 2026: 9`, `Prop. 44 L`, `Meld. St. 12`
     * metadata block
     * structured links and headings

4. **Related-link expansion**

   * Extract related documents from `Relatert`, `Videre behandling av saken`, `Høringssvar`, and references inside text.
   * Add related URLs to a queue, but mark them as `secondary_discovery`.
   * Do not recursively crawl arbitrary external websites by default.

5. **Hearing-response discovery**

   * Collect hearing response links only when:

     * they are publicly linked from the hearing page,
     * they are not disallowed,
     * the source terms and legal assessment permit it,
     * the system can preserve response provenance and submitter visibility.
   * Hearing pages may state that hearing responses are public and will be published on `regjeringen.no`, but the implementation should still treat response harvesting as a separate legal/compliance decision. ([Regjeringen.no][1])

---

## 4. Proposed architecture

```text
                           regjeringen.no
                                │
                                ▼
                    Source discovery service
                  sitemap + category listings
                                │
                                ▼
                        Polite fetcher
              httpx + robots + rate limits + cache
                                │
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
 Raw object storage      Fetch metadata DB        Crawl event log
 HTML, headers, PDFs     URL state, hashes        parser version,
 DOCX, assets            crawl status             errors, timings
        │                       │
        └──────────────┬────────┘
                       ▼
                Parser/extractor layer
   list parser | detail parser | attachment parser | text extractor
                       │
                       ▼
                Canonical document model
        GovernmentDocument + type-specific extensions
                       │
        ┌──────────────┼────────────────┬────────────────┐
        ▼              ▼                ▼                ▼
 PostgreSQL      S3/MinIO extracted   Search index     Sculpin KG
 metadata        text/chunks/tables    vector/fulltext  RDF/provenance
        │              │                │                │
        └──────────────┴────────────────┴────────────────┘
                       ▼
                 Sculpin agent tools
 search | retrieve | cite | compare | SPARQL | summarize | monitor
```

### Recommended implementation stack

| Concern                 | Recommended technology                                                                  |
| ----------------------- | --------------------------------------------------------------------------------------- |
| Language                | Python `3.12+`                                                                          |
| HTTP                    | `httpx`, `tenacity`, `aiolimiter`, `urllib.robotparser` or `reppy`/custom robots parser |
| HTML parsing            | `selectolax` for speed, `BeautifulSoup4`/`lxml` for fallback                            |
| Main-content extraction | Deterministic selectors first; `trafilatura` only as fallback                           |
| PDF extraction          | `pymupdf` for text and page geometry, `pdfplumber` for tables                           |
| DOCX extraction         | `python-docx` or `mammoth`                                                              |
| OCR fallback            | `ocrmypdf` + Tesseract only for scanned PDFs; mark as OCR-derived                       |
| Metadata model          | Pydantic v2 models                                                                      |
| Metadata DB             | PostgreSQL                                                                              |
| Raw storage             | S3/MinIO with versioned immutable objects                                               |
| Extracted chunks        | JSONL in S3/MinIO; optional Parquet                                                     |
| Analytical layer        | DuckDB over Parquet                                                                     |
| Search                  | OpenSearch, PostgreSQL full-text, or Sculpin-native index                               |
| Vector search           | pgvector, Qdrant, or Sculpin vector layer                                               |
| Knowledge graph         | Sculpin RDF backend / SPARQL endpoint                                                   |
| Workflow                | Temporal for production; Prefect/Celery/simple cron for MVP                             |
| Validation              | SHACL for graph constraints; Sculpin human approval workflow                            |
| Observability           | OpenTelemetry, Prometheus, Grafana, structured logs                                     |

---

## 5. Data storage strategy

### 5.1 Raw object storage

Use S3/MinIO as the immutable source archive.

Example layout:

```text
s3://sculpin-government-docs/
  regjeringen/
    raw-html/
      document_id=id3151708/
        fetched_at=2026-07-03T20-15-00Z/
          page.html
          headers.json
          fetch.json
          normalized-text.txt
          body.sha256

    assets/
      document_id=id3151708/
        asset_id=sha256-...
          original-filename.pdf
          headers.json
          asset-metadata.json
          content.sha256

    extracted/
      document_id=id3151708/
        parser_version=regjeringen-parser-0.3.0/
          document.json
          sections.json
          chunks.jsonl
          references.jsonl
          tables.jsonl
          pdf-pages.jsonl

    provenance/
      document_id=id3151708/
        extraction_run=2026-07-03T20-20-00Z.json
```

Rules:

* Never overwrite raw source artifacts.
* Store request URL, final URL, redirect chain, HTTP status, headers, fetch timestamp, user agent, parser version, and checksum.
* Use content-addressed storage for attachments.
* Store both `source_url` and `object_uri`.
* Normalize filenames but preserve original filenames.

### 5.2 Normalized metadata store

Use PostgreSQL for canonical operational metadata:

```text
documents
document_versions
document_identifiers
document_categories
document_departments
document_themes
document_attachments
document_sections
document_links
document_references
crawl_batches
fetch_events
extraction_runs
parser_errors
validation_findings
```

This provides:

* idempotent re-runs,
* incremental updates,
* parser QA,
* operational dashboards,
* graph export staging,
* reconciliation before promotion to Sculpin.

### 5.3 Knowledge graph

The graph should contain:

* document identity and metadata,
* document type,
* departments,
* topics,
* deadlines/status,
* attachments as distributions,
* document relations,
* references to laws/regulations/EU acts,
* extracted concepts and relations,
* provenance and validation status,
* source pointers into external text and files.

The graph should **not** contain full document text, complete PDFs, or thousands of paragraphs unless they are short, curated, and semantically important.

### 5.4 Search index / vector index

Use hybrid retrieval:

| Index type | Content                                                    |
| ---------- | ---------------------------------------------------------- |
| Full-text  | titles, summaries, sections, extracted text, PDF/DOCX text |
| Vector     | chunks, summaries, attachment text, concept definitions    |
| Graph      | structured metadata and relations                          |
| Relational | operational filtering, QA, incremental state               |

Chunk format:

```json
{
  "chunk_id": "id3151708:html:høringsbrev:p4",
  "document_id": "id3151708",
  "source_artifact_uri": "s3://.../page.html",
  "source_type": "html",
  "section_id": "høringsbrev",
  "heading_path": ["Høringsbrev"],
  "text": "...",
  "language": "nb",
  "char_start": 10342,
  "char_end": 12880,
  "page_number": null,
  "checksum": "sha256:..."
}
```

### 5.5 Optional analytical store

Use Parquet/DuckDB for:

* document counts by department/year/topic,
* response volume analysis,
* concept frequency,
* citation graph exports,
* parser coverage reports,
* QA dashboards.

Example Parquet datasets:

```text
parquet/
  documents/year=2026/document_type=hearing/*.parquet
  attachments/year=2026/*.parquet
  references/year=2026/*.parquet
  concepts/year=2026/*.parquet
  extraction_quality/year=2026/*.parquet
```

---

## 6. Extraction pipeline

### 6.1 Discovery

Implement category crawlers:

```text
GovernmentDocumentCrawler
├── HearingCrawler
├── InputCrawler
├── PropositionCrawler
├── StortingMessageCrawler
└── NouCrawler
```

Each crawler should emit `DiscoveredUrl` records:

```python
class DiscoveredUrl(BaseModel):
    url: AnyUrl
    canonical_candidate: AnyUrl | None
    source_category: Literal["hearing", "input", "proposition", "storting_message", "nou"]
    source_list_url: AnyUrl
    page_number: int | None
    title_hint: str | None
    publication_date_hint: date | None
    department_hint: list[str] = []
    discovered_at: datetime
    crawl_batch_id: str
```

### 6.2 Fetching

Fetcher requirements:

* Identify itself with a clear user agent.
* Respect `robots.txt`.
* Avoid disallowed filter and API URLs.
* Use low concurrency, e.g. `1–3` concurrent requests per host for MVP.
* Use exponential backoff for `429`, `500`, `502`, `503`, `504`.
* Store every HTTP response and failure.
* Use conditional requests when headers allow it.
* Detect canonical URL and redirects.
* Compute:

  * raw body checksum,
  * normalized body checksum,
  * attachment checksum.

### 6.3 HTML parsing

Use deterministic selectors and heading-aware extraction.

The parser should extract:

| Field                         | Strategy                                                  |
| ----------------------------- | --------------------------------------------------------- |
| Title                         | `h1`                                                      |
| Document type/date/department | visible metadata line under title                         |
| Summary/ingress               | first paragraph after metadata                            |
| Status/deadline               | regex over visible labels                                 |
| Sections                      | heading segmentation from `h2`, `h3`                      |
| Attachments                   | links with file extension/content type/size labels        |
| Topics                        | `Tema` section links                                      |
| Related docs                  | `Relatert`, `Videre behandling`, in-text links            |
| Contact                       | `Kontakt` section                                         |
| Language                      | HTML lang, URL prefix, labels, language detector fallback |
| Breadcrumb                    | visible breadcrumb and document category links            |

Example hearing parser targets:

```text
h1
metadata line: "Høring | Dato: ... | Department"
Status:
Høringsfrist:
Høringsbrev
Høringsnotat
Høringsinstanser
Høringssvar
Tema
Relatert
Kontakt
```

The inspected hearing page confirms these section labels and fields. ([Regjeringen.no][1])

### 6.4 Attachment extraction

For every asset link:

```python
class Attachment(BaseModel):
    attachment_id: str
    document_id: str
    source_url: AnyUrl
    final_url: AnyUrl | None
    original_label: str
    original_filename: str | None
    normalized_filename: str
    media_type: str | None
    file_extension: str | None
    size_label: str | None
    size_bytes: int | None
    checksum_sha256: str
    object_uri: str
    attachment_role: Literal[
        "hearing_note",
        "hearing_letter",
        "main_document",
        "appendix",
        "report",
        "form",
        "unknown"
    ]
    extracted_text_uri: str | None
    provenance: list["FieldProvenance"]
```

Attachment role classification should be deterministic first:

| Pattern                           | Role                  |
| --------------------------------- | --------------------- |
| `høringsnotat`, `høyringsnotat`   | `hearing_note`        |
| `høringsbrev`, `høyringsbrev`     | `hearing_letter`      |
| `dokumentet i PDF format`         | `main_document`       |
| `vedlegg`, `appendiks`, `rapport` | `appendix` / `report` |
| `skjema`, `form`                  | `form`                |

### 6.5 PDF/DOCX text extraction

PDF extraction output should preserve page-level evidence:

```json
{
  "document_id": "id3152698",
  "attachment_id": "sha256-...",
  "page_number": 12,
  "text": "...",
  "blocks": [
    {
      "block_id": "p12-b3",
      "text": "...",
      "bbox": [72.0, 142.0, 510.0, 188.0]
    }
  ],
  "tables": [],
  "extraction_method": "pymupdf",
  "confidence": null
}
```

Rules:

* Prefer text extraction over OCR.
* Use OCR only if the PDF has insufficient embedded text.
* Mark OCR-derived chunks with `extraction_method = "ocr"`.
* Keep PDF page numbers in every source span.
* Do not put extracted full PDF text directly into the graph.

### 6.6 Metadata normalization

Normalize:

| Raw value                  | Normalized representation                    |
| -------------------------- | -------------------------------------------- |
| `På høring`, `På høyring`  | `scgov:OpenForConsultation`                  |
| `Under behandling`         | `scgov:UnderReview`                          |
| `Åpen`, `Ope`              | `scgov:Open`                                 |
| `Lukket`, `Stengt`         | `scgov:Closed`                               |
| `Finansdepartementet`      | canonical department URI                     |
| `Skatter og avgifter`      | SKOS concept URI                             |
| `Prop. 44 L (2025–2026)`   | document number + document subtype + session |
| `NOU 2026: 9`              | NOU year + sequence number                   |
| `Meld. St. 12 (2025–2026)` | message number + session                     |

### 6.7 Incremental updates

Reprocess a document when:

* HTML checksum changes,
* normalized main content checksum changes,
* attachment list changes,
* deadline/status changes,
* response link appears or changes,
* parser version changes,
* ontology mapping version changes,
* LLM extraction prompt/schema version changes.

Use `document_version` records:

```python
class DocumentVersion(BaseModel):
    document_id: str
    version_id: str
    fetched_at: datetime
    html_checksum: str
    normalized_text_checksum: str
    attachment_manifest_checksum: str
    parser_version: str
    extraction_status: Literal["pending", "success", "partial", "failed"]
    previous_version_id: str | None
```

### 6.8 Error handling

Use explicit error classes:

```text
DiscoveryError
RobotsDisallowedError
FetchTimeoutError
HttpStatusError
HtmlStructureError
MissingRequiredFieldError
AttachmentDownloadError
PdfExtractionError
DocxExtractionError
NormalizationError
GraphExportError
ValidationError
```

Each error must include:

* URL,
* crawl batch ID,
* document ID if known,
* parser version,
* retryable flag,
* source artifact URI if available,
* traceback hash,
* human-readable message.

---

## 7. Canonical data model

Use one base model plus extensions.

```python
class GovernmentDocument(BaseModel):
    document_id: str
    canonical_url: str
    source_site: Literal["regjeringen.no"] = "regjeringen.no"
    document_type: Literal[
        "hearing",
        "input",
        "proposition",
        "storting_message",
        "nou"
    ]

    title: str
    subtitle: str | None = None
    summary: str | None = None
    language: Literal["nb", "nn", "en", "se", "unknown"]

    publication_date: date | None = None
    updated_date: date | None = None

    responsible_departments: list["DepartmentRef"] = []
    themes: list["ThemeRef"] = []

    status: str | None = None
    normalized_status: str | None = None
    deadline: date | None = None

    document_number: str | None = None
    parliamentary_session: str | None = None
    reference_number: str | None = None

    source_html_object_uri: str
    extracted_text_object_uri: str | None = None

    attachments: list["Attachment"] = []
    sections: list["DocumentSection"] = []
    contacts: list["ContactPoint"] = []
    source_links: list["SourceLink"] = []
    references: list["ExtractedReference"] = []

    provenance: list["FieldProvenance"]
```

### Hearing extension

```python
class HearingDocument(GovernmentDocument):
    document_type: Literal["hearing"] = "hearing"

    hearing_status: str | None = None
    hearing_deadline: date | None = None

    hearing_letter_section_id: str | None = None
    hearing_note_attachment_ids: list[str] = []

    hearing_recipients: list["OrganizationRef"] = []
    submission_url: str | None = None
    hearing_responses_url: str | None = None
```

### Proposition extension

```python
class PropositionDocument(GovernmentDocument):
    document_type: Literal["proposition"] = "proposition"

    proposition_number: str
    proposition_kind: Literal["L", "S", "LS", "unknown"]
    parliamentary_session: str
    storting_case_url: str | None = None
    affected_laws: list["LegalReference"] = []
```

### Storting message extension

```python
class StortingMessageDocument(GovernmentDocument):
    document_type: Literal["storting_message"] = "storting_message"

    message_number: str
    parliamentary_session: str
    main_policy_area: str | None = None
    chapters: list["DocumentSection"] = []
```

### NOU extension

```python
class NouDocument(GovernmentDocument):
    document_type: Literal["nou"] = "nou"

    nou_year: int
    nou_number: int
    committee_name: str | None = None
    mandate_section_id: str | None = None
    recommendations_section_ids: list[str] = []
    appendices: list["Attachment"] = []
```

### Provenance model

```python
class FieldProvenance(BaseModel):
    field_path: str
    value_hash: str
    extraction_method: Literal[
        "html_selector",
        "regex",
        "pdf_text",
        "docx_text",
        "llm",
        "manual"
    ]
    source_artifact_uri: str
    source_url: str
    css_selector: str | None = None
    heading_path: list[str] = []
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    quote: str | None = None
    extractor_version: str
    extracted_at: datetime
    confidence: float | None = None
```

---

## 8. Initial ontology design

Use namespace:

```text
https://w3id.org/sculpin/government/regjeringen#
prefix scgov:
```

### 8.1 Core classes

```text
scgov:GovernmentDocument
scgov:Consultation
scgov:InputProcess
scgov:Proposition
scgov:StortingMessage
scgov:NOU
scgov:DocumentVersion
scgov:DocumentSection
scgov:Attachment
scgov:Department
scgov:GovernmentBody
scgov:Theme
scgov:ContactPoint
scgov:Person
scgov:Organization
scgov:HearingRecipient
scgov:HearingResponse
scgov:ParliamentarySession
scgov:LegalReference
scgov:RegulationReference
scgov:EUActReference
scgov:PolicyConcept
scgov:ExtractionRun
scgov:SourceArtifact
scgov:SourceSpan
scgov:ValidationDecision
```

### 8.2 Core relations

```text
scgov:publishedBy
scgov:responsibleDepartment
scgov:hasTheme
scgov:hasStatus
scgov:hasDeadline
scgov:hasAttachment
scgov:hasSection
scgov:hasDocumentVersion
scgov:hasHearingLetter
scgov:hasHearingNote
scgov:hasRecipient
scgov:hasResponse
scgov:hasContactPoint
scgov:referencesDocument
scgov:referencesLaw
scgov:referencesRegulation
scgov:referencesEUAct
scgov:mentionsConcept
scgov:proposesMeasure
scgov:affectsSector
scgov:affectsActor
scgov:hasSourceArtifact
scgov:hasSourceSpan
scgov:derivedFrom
scgov:validatedBy
scgov:reviewStatus
```

### 8.3 Controlled vocabularies

Represent these as SKOS concept schemes:

```text
scgov:DocumentTypeScheme
scgov:ConsultationStatusScheme
scgov:DepartmentScheme
scgov:GovernmentThemeScheme
scgov:LegalReferenceTypeScheme
scgov:AttachmentRoleScheme
scgov:LanguageScheme
scgov:ReviewStatusScheme
```

Example statuses:

```text
scgov:OpenForConsultation
  skos:prefLabel "På høring"@nb ;
  skos:altLabel "På høyring"@nn ;
  skos:broader scgov:OpenStatus .

scgov:Closed
  skos:prefLabel "Lukket"@nb ;
  skos:altLabel "Stengt"@nn, "Lukka"@nn .
```

SKOS is suitable because it is a W3C model for sharing and linking thesauri, taxonomies, classification schemes, and similar knowledge organization systems. ([W3C][8])

### 8.4 Mapping to existing vocabularies

| Sculpin need                               | Recommended vocabulary                                        |
| ------------------------------------------ | ------------------------------------------------------------- |
| Generic metadata                           | Dublin Core Terms                                             |
| Catalog/distribution/file assets           | DCAT                                                          |
| Topic concepts and controlled vocabularies | SKOS                                                          |
| Organizations/departments                  | W3C ORG                                                       |
| Provenance                                 | PROV-O                                                        |
| Web/document representation                | schema.org `CreativeWork` / `DigitalDocument` where useful    |
| Validation                                 | SHACL                                                         |
| Domain-specific legal references           | `scgov` extension, optionally mapped to ELI where appropriate |

Dublin Core Metadata Terms are maintained as an authoritative metadata term set by DCMI. ([DCMI][9]) DCAT is an RDF vocabulary for interoperability between data catalogs on the Web and includes distributions such as downloadable files. ([W3C][10]) PROV-O provides classes and properties for representing and exchanging provenance across systems. ([W3C][11]) ORG is a W3C ontology for organizational structures and linked-data publishing of organizational information. ([W3C][12]) schema.org `CreativeWork` can be used as a broad web/document superclass when pragmatic interoperability is useful. ([Schema.org][13])

Example mapping:

```turtle
scgov:GovernmentDocument
    rdfs:subClassOf dcterms:BibliographicResource ;
    rdfs:subClassOf schema:CreativeWork .

scgov:Department
    rdfs:subClassOf org:Organization .

scgov:Theme
    rdfs:subClassOf skos:Concept .

scgov:Attachment
    rdfs:subClassOf dcat:Distribution .

scgov:ExtractionRun
    rdfs:subClassOf prov:Activity .

scgov:SourceArtifact
    rdfs:subClassOf prov:Entity .
```

### 8.5 Example document triples

```turtle
scgov-doc:id3151708
    a scgov:Consultation ;
    dcterms:identifier "id3151708" ;
    dcterms:title "Høring - registerordning under Tolletaten"@nb ;
    dcterms:issued "2026-03-10"^^xsd:date ;
    scgov:responsibleDepartment scgov-org:finansdepartementet ;
    scgov:hasStatus scgov:UnderReview ;
    scgov:hasDeadline "2026-04-13"^^xsd:date ;
    scgov:hasTheme scgov-theme:skatter-og-avgifter ;
    scgov:hasAttachment scgov-asset:id3151708-horingsnotat ;
    scgov:hasRecipient scgov-org:sintef ;
    prov:wasDerivedFrom scgov-artifact:id3151708-html-20260703 .
```

---

## 9. AI-assisted concept and relation extraction

### 9.1 Principle

Use AI only after deterministic extraction has captured the document structure and evidence.

Three levels:

| Level | Extraction type       | Method                                                   |
| ----- | --------------------- | -------------------------------------------------------- |
| 1     | Metadata              | Deterministic HTML/PDF/DOCX parsing                      |
| 2     | Structured references | Regex, pattern matching, named entity dictionaries       |
| 3     | Concepts/relations    | LLM-assisted extraction with source spans and validation |

### 9.2 Deterministic reference extraction

Use pattern extraction for:

```text
NOU 2026: 9
Prop. 44 L (2025–2026)
Prop. 95 LS (2025–2026)
Meld. St. 12 (2025–2026)
lov 19. juni 2009 nr. 58
forskrift 29. januar 2025 nr. 115
§ 7-22
direktiv (EU) 2019/2121
forordning (EU) 2025/2518
EØS-komiteens beslutning nr. ...
```

### 9.3 LLM extraction schema

```json
{
  "document_id": "id3151708",
  "section_id": "høringsbrev",
  "concepts": [
    {
      "label": "registreringsordning under Tolletaten",
      "language": "nb",
      "concept_type": "policy_measure",
      "definition_candidate": "...",
      "source_quote": "...",
      "source_span": {
        "artifact_uri": "s3://...",
        "char_start": 1234,
        "char_end": 1390,
        "page_number": null
      },
      "confidence": 0.82,
      "review_status": "proposed"
    }
  ],
  "relations": [
    {
      "subject_label": "registreringsordning under Tolletaten",
      "predicate": "implements_or_supports",
      "object_label": "EU-rettsakter om varer fra tredjeland",
      "source_quote": "...",
      "confidence": 0.76,
      "review_status": "proposed"
    }
  ]
}
```

### 9.4 Extraction targets

The LLM should identify:

* policy areas,
* affected sectors,
* affected organizations,
* affected citizen groups,
* affected laws and regulations,
* proposed measures,
* obligations,
* rights,
* deadlines,
* responsible authorities,
* risk/impact statements,
* committee recommendations,
* economic consequences,
* environmental consequences,
* EU/EØS dependencies,
* cross-document conceptual overlap.

### 9.5 Guardrails

Every LLM-derived fact must have:

* source document ID,
* section or page,
* exact quote or source span,
* extraction prompt version,
* model version,
* confidence,
* review status,
* provenance link,
* deterministic fallback if possible.

No LLM-derived concept should become authoritative ontology content without validation.

---

## 10. Human validation workflow

```text
Raw extraction
   │
   ▼
Deterministic metadata accepted automatically if validation passes
   │
   ▼
AI concept/relation candidates
   │
   ▼
Sculpin review queue
   ├── approve
   ├── reject
   ├── merge with existing concept
   ├── rename / normalize label
   ├── add synonym
   └── request re-extraction
   │
   ▼
Promote to approved ontology / KG
```

### Review UI requirements

Reviewers should see:

* candidate concept/relation,
* source quote,
* source page/section,
* original document link,
* existing similar concepts,
* proposed normalized label,
* language labels,
* confidence,
* extractor version,
* impact preview: “this will affect N documents / M relations”.

### Validation states

```text
proposed
approved
rejected
merged
deprecated
needs_review
```

### Concept merge example

| Raw labels                                         | Normalized concept           |
| -------------------------------------------------- | ---------------------------- |
| `Nav`, `NAV`, `Arbeids- og velferdsetaten`         | `Arbeids- og velferdsetaten` |
| `EØS-regler`, `EØS-rettsakter`, `EU/EØS-regelverk` | `EU/EØS legal act`           |
| `høringsinstans`, `høyringsinstans`                | `Consultation recipient`     |

---

## 11. Sculpin agent tools

Expose these tools through Sculpin.

### 11.1 `search_government_documents`

```python
search_government_documents(
    query: str,
    document_types: list[str] | None = None,
    departments: list[str] | None = None,
    themes: list[str] | None = None,
    status: list[str] | None = None,
    deadline_from: date | None = None,
    deadline_to: date | None = None,
    publication_from: date | None = None,
    publication_to: date | None = None,
    referenced_law: str | None = None,
    limit: int = 20
)
```

Uses graph filters + full-text/vector search.

### 11.2 `get_government_document`

Returns canonical metadata, source links, attachments, sections, provenance summary.

### 11.3 `get_document_sections`

Returns section tree and selected section text from external storage.

### 11.4 `get_document_attachments`

Returns attachment metadata, roles, extracted text availability, object URIs, checksums.

### 11.5 `query_government_kg`

SPARQL access with safe query templates and policy controls.

### 11.6 `search_extracted_concepts`

Searches approved and proposed concepts, supports `review_status`.

### 11.7 `compare_documents`

Compares two or more documents by:

* topics,
* departments,
* references,
* affected laws,
* concepts,
* proposed measures,
* deadlines/status,
* related hearings/propositions/NOU/Meld. St.

### 11.8 `track_consultation_deadlines`

Returns open hearings/inputs with deadlines by department/topic/date window.

### 11.9 `generate_summary_with_citations`

Generates summaries only from retrieved source chunks and graph metadata.

---

## 12. Example SPARQL queries and natural-language questions

### 12.1 Open hearings from Finansdepartementet in next 60 days

```sparql
PREFIX scgov: <https://w3id.org/sculpin/government/regjeringen#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT ?doc ?title ?deadline
WHERE {
  ?doc a scgov:Consultation ;
       dcterms:title ?title ;
       scgov:responsibleDepartment scgov-org:finansdepartementet ;
       scgov:hasStatus scgov:OpenForConsultation ;
       scgov:hasDeadline ?deadline .
  FILTER(?deadline >= NOW() && ?deadline <= NOW() + "P60D"^^xsd:duration)
}
ORDER BY ?deadline
```

Natural language:

> “Which open hearings from Finansdepartementet have deadlines in the next 60 days?”

### 12.2 Hearings that reference a NOU

```sparql
PREFIX scgov: <https://w3id.org/sculpin/government/regjeringen#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT ?hearing ?hearingTitle ?nou ?nouTitle
WHERE {
  ?hearing a scgov:Consultation ;
           dcterms:title ?hearingTitle ;
           scgov:referencesDocument ?nou .
  ?nou a scgov:NOU ;
       dcterms:title ?nouTitle .
}
```

Natural language:

> “Which hearings reference NOUs?”

### 12.3 Documents related to EØS legal acts

```sparql
PREFIX scgov: <https://w3id.org/sculpin/government/regjeringen#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT ?doc ?title ?ref
WHERE {
  ?doc dcterms:title ?title ;
       scgov:referencesEUAct ?ref .
}
ORDER BY ?title
```

Natural language:

> “Find all propositions and hearings that reference EU or EØS acts.”

### 12.4 Most frequent hearing recipients

```sparql
PREFIX scgov: <https://w3id.org/sculpin/government/regjeringen#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?recipient ?label (COUNT(?doc) AS ?count)
WHERE {
  ?doc a scgov:Consultation ;
       scgov:hasRecipient ?recipient .
  ?recipient rdfs:label ?label .
}
GROUP BY ?recipient ?label
ORDER BY DESC(?count)
LIMIT 50
```

Natural language:

> “Which organizations appear most often as hearing recipients?”

### 12.5 Documents connected to a policy concept

```sparql
PREFIX scgov: <https://w3id.org/sculpin/government/regjeringen#>
PREFIX dcterms: <http://purl.org/dc/terms/>

SELECT ?doc ?title ?section
WHERE {
  ?concept skos:prefLabel "digital bokføring"@nb .
  ?doc scgov:mentionsConcept ?concept ;
       dcterms:title ?title .
  OPTIONAL { ?doc scgov:hasSection ?section . }
}
```

Natural language:

> “Show all documents connected to digital bookkeeping and e-invoicing.”

---

## 13. Implementation phases

### Phase 1: Source audit and fixtures

Deliverables:

* `robots.txt` and sitemap report.
* HTML structure report for each category.
* 20–50 saved fixtures per category.
* Attachment pattern inventory.
* Pagination/discovery strategy.
* Field availability matrix.
* Compliance/risk assessment for hearing responses.

Acceptance criteria:

* At least 100 representative pages archived as fixtures.
* Each target category has a documented parser strategy.
* Disallowed URL patterns are encoded in crawler policy.
* Fixture set includes Bokmål and Nynorsk examples.

### Phase 2: Hearing ingestion MVP

Deliverables:

* `HearingCrawler`
* `HearingPageParser`
* raw object storage writer
* PostgreSQL schema
* Pydantic models
* attachment downloader
* parser regression tests
* initial Sculpin KG export

Acceptance criteria:

* `95%+` of crawled hearing pages produce valid `GovernmentDocument`.
* `90%+` of pages with visible deadlines produce a normalized date.
* `95%+` of visible PDF/DOCX attachments are downloaded and checksummed.
* Every extracted field has provenance.
* Re-running the crawler is idempotent.

### Phase 3: Attachment and full-text extraction

Deliverables:

* PDF extractor.
* DOCX extractor.
* OCR fallback.
* section/chunk model.
* full-text index.
* vector index.
* citation source-span model.

Acceptance criteria:

* `95%+` of text-bearing PDFs produce page-level text.
* Every chunk has source artifact URI and source span.
* Agent summaries include citations to exact sections/pages.

### Phase 4: Other document types

Deliverables:

* `InputCrawler`
* `PropositionCrawler`
* `StortingMessageCrawler`
* `NouCrawler`
* type-specific parser extensions
* shared `GovernmentDocument` model
* document-number/session parser

Acceptance criteria:

* Each category reaches `90%+` parser success on fixture corpus.
* `Prop.`, `Meld. St.`, and `NOU` numbering is normalized.
* Main document PDF/Word assets are classified correctly.

### Phase 5: Ontology bootstrapping

Deliverables:

* `scgov` ontology.
* SKOS concept schemes.
* department registry.
* topic registry.
* SHACL shapes.
* graph export pipeline.
* ontology review workflow.

Acceptance criteria:

* Graph validates with SHACL.
* No full-text dumping into graph.
* All document nodes link to source artifacts.
* All AI-derived concepts have `review_status`.

### Phase 6: AI extraction and human validation

Deliverables:

* reference extractor.
* LLM concept extraction.
* relation extraction.
* validation UI/process.
* merge/deduplication workflow.
* provenance-aware promotion to approved KG.

Acceptance criteria:

* No LLM fact is promoted without source quote/span.
* Reviewer can approve/reject/merge concepts.
* Concept merge decisions preserve old labels as `skos:altLabel`.

### Phase 7: Sculpin agent tools

Deliverables:

* search tool.
* metadata retrieval tool.
* attachment retrieval tool.
* SPARQL query tool.
* comparison tool.
* summary-with-citations tool.
* deadline tracking tool.

Acceptance criteria:

* Agents can answer structured deadline/department/theme questions.
* Agents cite exact source sections or attachments.
* Agents can move from KG result to source text and back.

### Phase 8: Production hardening

Deliverables:

* scheduling.
* retry queues.
* monitoring dashboards.
* parser drift alerts.
* data quality reports.
* deployment documentation.
* backup/restore.
* security review.

Acceptance criteria:

* Failed pages are retryable.
* Parser regressions are detected by fixture tests.
* Crawl jobs are observable.
* Operational dashboards show coverage and data quality.

---

## 14. Testing and quality assurance

### 14.1 Test pyramid

| Level          | Tests                                                                |
| -------------- | -------------------------------------------------------------------- |
| Unit           | URL normalization, ID extraction, date parsing, status normalization |
| Parser fixture | Saved HTML/PDF/DOCX fixtures with expected JSON                      |
| Integration    | crawler → storage → parser → DB → KG                                 |
| Regression     | parser output diffs across fixture corpus                            |
| Property-based | date/status/reference regex robustness                               |
| E2E            | agent question → graph/search retrieval → cited answer               |
| Data quality   | missing fields, duplicate IDs, invalid links, broken attachments     |

### 14.2 Required fixture cases

* Bokmål hearing.
* Nynorsk hearing.
* hearing with multiple departments.
* hearing with no deadline.
* hearing with expired deadline.
* hearing with responses link.
* hearing with many recipients.
* hearing with PDF hearing note.
* proposition with `L`, `S`, and `LS`.
* Meld. St. with chapters.
* NOU with subtitle, committee, PDF, appendices.
* old documents with different structure.
* page with changed title/deadline between versions.

### 14.3 Data quality checks

Examples:

```text
documents_without_title = 0
documents_without_document_id = 0
hearing_with_deadline_label_but_no_deadline < 2%
attachment_links_without_checksum = 0
graph_documents_without_source_artifact = 0
llm_concepts_without_source_quote = 0
approved_concepts_without_language_label = 0
```

---

## 15. Monitoring, observability, and data quality checks

Dashboards should show:

| Dashboard           | Metrics                                                        |
| ------------------- | -------------------------------------------------------------- |
| Crawl health        | pages fetched, failures, retries, response codes, latency      |
| Parser coverage     | required-field extraction rate by category                     |
| Attachment health   | downloaded assets, failed downloads, MIME mismatches           |
| Incremental changes | changed pages, changed attachments, changed deadlines          |
| KG export           | triples generated, validation errors, rejected records         |
| Search/vector index | indexed chunks, embedding failures, stale chunks               |
| AI extraction       | proposed concepts, confidence distribution, validation backlog |
| Agent quality       | citation coverage, retrieval failures, unanswered questions    |

Use structured logs:

```json
{
  "event": "document_parsed",
  "document_id": "id3151708",
  "document_type": "hearing",
  "parser_version": "0.3.0",
  "fields_extracted": 18,
  "required_fields_missing": [],
  "attachments": 1,
  "duration_ms": 243
}
```

---

## 16. Security, compliance, copyright, and ethical considerations

### 16.1 Crawling compliance

* Respect `robots.txt`.
* Do not crawl disallowed `/api/*` paths or disallowed filter URLs.
* Use conservative rate limits.
* Use caching and conditional requests.
* Identify the crawler clearly.
* Provide contact information in user agent or project documentation.

### 16.2 Copyright and reuse

* Store official source artifacts for internal knowledge organization and traceable retrieval.
* Do not republish full documents unless rights and use terms permit it.
* Prefer snippets and citations for agent answers.
* Keep source URLs and provenance visible.

### 16.3 Hearing responses

* Treat hearing responses as a separate module.
* Even when linked and public, consider:

  * personal data,
  * submitter identity,
  * anonymized/private-person responses,
  * terms of use,
  * GDPR expectations,
  * retention policy.
* Store response metadata and source links first; defer full response harvesting until legal review.

### 16.4 AI governance

* AI-extracted facts must not be authoritative by default.
* Store model, prompt, schema version, confidence, source span.
* Require human approval for ontology promotion.
* Separate `proposed` from `approved`.

---

## 17. Risks and mitigations

| Risk                               | Mitigation                                                                  |
| ---------------------------------- | --------------------------------------------------------------------------- |
| HTML structure changes             | Fixture-based parser tests, parser drift alerts, fallback extraction        |
| No stable public API               | Treat HTML and sitemap as primary sources; do not depend on disallowed APIs |
| Disallowed filter URLs             | Use sitemap and allowed category pagination; encode crawl policy            |
| Large PDFs                         | Store externally, extract page chunks, keep graph lightweight               |
| OCR noise                          | Use OCR only as fallback and mark provenance clearly                        |
| Duplicate concepts                 | SKOS alt labels, merge workflow, human validation                           |
| Deadline/status changes            | Incremental recrawl, checksum comparison, status history                    |
| Hallucinated AI extraction         | Require source spans, confidence, and review status                         |
| Legal uncertainty around responses | Make response harvesting optional and separately approved                   |
| Nynorsk/Bokmål variation           | Language-tagged labels and normalized concept mappings                      |
| Broken links/assets                | Retry, checksum, link validation dashboard                                  |
| Graph bloat                        | Enforce graph content policy and SHACL constraints                          |

---

## 18. MVP definition

The MVP should focus on **Høringer / Høyringar**.

### MVP features

* Crawl hearing category pages.
* Discover hearing detail URLs.
* Fetch and archive raw HTML.
* Extract:

  * title,
  * URL,
  * stable `id...`,
  * document type,
  * publication date,
  * department(s),
  * status,
  * deadline,
  * summary,
  * `Høringsbrev`,
  * `Høringsnotat` link/PDF,
  * `Høringsinstanser`,
  * `Høringssvar` link if visible,
  * themes,
  * related links,
  * contact details.
* Download visible PDF/DOCX attachments.
* Store raw files in S3/MinIO.
* Store normalized metadata in PostgreSQL.
* Export graph triples to Sculpin.
* Chunk extracted text.
* Add `search_government_documents` and `get_government_document`.
* Add parser coverage report.

### MVP acceptance criteria

| Criterion                                  | Target                                            |
| ------------------------------------------ | ------------------------------------------------- |
| Hearing pages parsed into valid model      | `95%+`                                            |
| Visible deadlines normalized               | `90%+`                                            |
| Visible attachments downloaded/checksummed | `95%+`                                            |
| Required provenance coverage               | `100%` for extracted fields                       |
| Re-run behavior                            | idempotent                                        |
| Change detection                           | HTML and attachment checksums                     |
| Agent search                               | can filter by department, status, deadline, theme |
| Agent citation                             | answers cite source page/section/attachment       |
| Failure handling                           | failed pages logged and retryable                 |

---

## 19. Future extensions

1. **Full hearing-response ingestion**

   * After legal review, ingest published responses, submitter metadata, attachments, and response themes.

2. **Cross-document policy lifecycle**

   * Link NOU → hearing → proposition → Storting case → adopted law/regulation.

3. **Storting integration**

   * Use Stortinget links from proposition pages to follow parliamentary treatment where appropriate. Proposition detail pages may include `Følg proposisjonen på Stortinget`. ([Regjeringen.no][14])

4. **Lovdata / legal reference enrichment**

   * Resolve laws, regulations, and paragraphs to canonical legal identifiers where licensing permits.

5. **EU/EØS reference enrichment**

   * Resolve directives, regulations, and EØS committee decisions.

6. **Policy impact ontology**

   * Model affected sectors, obligations, rights, costs, environmental impacts, and implementation timelines.

7. **Alerting**

   * Deadline alerts by topic/department.
   * New consultation alerts.
   * Changed status/deadline alerts.

8. **Analytics**

   * Department publishing trends.
   * Topic evolution.
   * Consultation response volume.
   * Most cited NOUs/propositions.
   * Cross-sector policy maps.

9. **Multilingual alignment**

   * Align Bokmål, Nynorsk, English, and Sámi labels where available.

10. **Sculpin-generated briefings**

* Weekly briefings with citations and graph-backed change summaries.

---

## 20. Concrete next steps for implementation

### Step 1: Create repository module structure

```text
sculpin-regjeringen-ingest/
  README.md
  pyproject.toml
  src/
    sculpin_regjeringen/
      crawler/
        robots.py
        discovery.py
        fetcher.py
        hearing.py
        input_process.py
        proposition.py
        storting_message.py
        nou.py
      parsers/
        base.py
        html_common.py
        hearing_parser.py
        proposition_parser.py
        storting_message_parser.py
        nou_parser.py
        attachment_parser.py
      extractors/
        pdf.py
        docx.py
        references.py
        concepts.py
      models/
        canonical.py
        provenance.py
        graph.py
      storage/
        object_store.py
        postgres.py
        parquet.py
      graph/
        mapping.py
        sparql_templates.py
        shacl/
      agents/
        tools.py
      validation/
        quality.py
        review_queue.py
  tests/
    fixtures/
      regjeringen/
        hearings/
        propositions/
        meldst/
        nou/
        innspill/
    unit/
    parser/
    integration/
```

### Step 2: Implement source audit script

```bash
sculpin-regjeringen audit-sources \
  --categories hearing,input,proposition,storting-message,nou \
  --sample-size 50 \
  --output reports/source-audit-2026-07-03.md
```

The audit should save HTML fixtures, extract available fields, and generate a field coverage matrix.

### Step 3: Implement hearing-only parser

Target output:

```bash
sculpin-regjeringen parse-fixture \
  tests/fixtures/regjeringen/hearings/id3151708/page.html \
  --document-type hearing \
  --output tmp/id3151708.document.json
```

### Step 4: Add raw storage and metadata DB

Minimum tables:

```sql
documents
document_versions
attachments
document_sections
field_provenance
crawl_batches
fetch_events
extraction_runs
parser_errors
```

### Step 5: Add graph mapping

Generate Turtle/JSON-LD from canonical model:

```bash
sculpin-regjeringen export-graph \
  --document-id id3151708 \
  --format turtle \
  --output tmp/id3151708.ttl
```

### Step 6: Add Sculpin tools

Start with:

```text
search_government_documents
get_government_document
get_document_sections
get_document_attachments
query_government_kg
```

### Step 7: Define MVP demo questions

The MVP should answer these with citations:

* “Which open hearings from Finansdepartementet have deadlines this quarter?”
* “Show the hearing note for `id3151708`.”
* “Who are the hearing recipients for this hearing?”
* “Which hearings mention EØS?”
* “Which hearings are related to Skatter og avgifter?”
* “Summarize this hearing letter with citations.”

---

## Recommended first milestone

Start with a **hearing-only source audit and parser prototype** using 30–50 hearing pages across departments, years, statuses, and both Bokmål/Nynorsk. The most important early deliverable is the **canonical model with field-level provenance**, because that determines whether the content can become reliable Sculpin knowledge rather than just another scraped document archive.

[1]: https://www.regjeringen.no/no/dokumenter/horing-registerordning-under-tolletaten/id3151708/ "Høring - registerordning under Tolletaten - regjeringen.no"
[2]: https://www.regjeringen.no/no/dokument/hoyringar/id1763/ "Høyringar - regjeringen.no"
[3]: https://www.regjeringen.no/no/dokument/innspel/id3015054/ "Innspel - regjeringen.no"
[4]: https://www.regjeringen.no/no/dokument/prop/id1753/ "Proposisjonar til Stortinget - regjeringen.no"
[5]: https://www.regjeringen.no/no/dokument/meldst/id1754/ "Meldingar til Stortinget - regjeringen.no"
[6]: https://www.regjeringen.no/no/dokument/nou-ar/id1767/ "NOU-ar - regjeringen.no"
[7]: https://www.regjeringen.no/robots.txt "www.regjeringen.no"
[8]: https://www.w3.org/TR/skos-reference/?utm_source=chatgpt.com "SKOS Simple Knowledge Organization System Reference"
[9]: https://www.dublincore.org/documents/dcmi-terms/?utm_source=chatgpt.com "DCMI Metadata Terms"
[10]: https://www.w3.org/TR/vocab-dcat-3/?utm_source=chatgpt.com "Data Catalog Vocabulary (DCAT) - Version 3"
[11]: https://www.w3.org/TR/prov-o/?utm_source=chatgpt.com "PROV-O: The PROV Ontology"
[12]: https://www.w3.org/TR/vocab-org/?utm_source=chatgpt.com "The Organization Ontology"
[13]: https://schema.org/CreativeWork?utm_source=chatgpt.com "CreativeWork - Schema.org Type"
[14]: https://www.regjeringen.no/no/dokumenter/prop.-44-l-20252026/id3152698/ "Prop. 44 L (2025–2026) - regjeringen.no"
