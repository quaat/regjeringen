-- Production metadata schema for regjeringen.no ingestion.
-- Large artifacts (HTML, attachments, extracted full text, chunks, logs) live in object storage;
-- these tables keep normalized metadata, checksums, source pointers, and provenance only.

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    document_type TEXT NOT NULL CHECK (document_type IN ('hearing', 'input', 'proposition', 'storting_message', 'nou')),
    canonical_url TEXT NOT NULL UNIQUE,
    source_site TEXT NOT NULL DEFAULT 'regjeringen.no',
    title TEXT NOT NULL,
    subtitle TEXT,
    summary TEXT,
    language TEXT NOT NULL DEFAULT 'unknown',
    publication_date DATE,
    updated_date DATE,
    status TEXT,
    normalized_status TEXT,
    deadline DATE,
    source_html_object_uri TEXT NOT NULL,
    extracted_text_object_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    fetched_at TIMESTAMPTZ NOT NULL,
    html_checksum_sha256 TEXT NOT NULL,
    normalized_text_checksum_sha256 TEXT,
    attachment_manifest_checksum_sha256 TEXT,
    parser_version TEXT NOT NULL,
    extraction_status TEXT NOT NULL CHECK (extraction_status IN ('pending', 'success', 'partial', 'failed')),
    previous_version_id TEXT REFERENCES document_versions(version_id),
    source_artifact_uri TEXT NOT NULL,
    UNIQUE (document_id, html_checksum_sha256, parser_version)
);

CREATE TABLE IF NOT EXISTS document_departments (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    label TEXT NOT NULL,
    uri TEXT,
    PRIMARY KEY (document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS document_themes (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    label TEXT NOT NULL,
    uri TEXT,
    PRIMARY KEY (document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    final_url TEXT,
    original_label TEXT NOT NULL,
    original_filename TEXT,
    normalized_filename TEXT NOT NULL,
    media_type TEXT,
    file_extension TEXT,
    size_label TEXT,
    size_bytes BIGINT,
    checksum_sha256 TEXT,
    object_uri TEXT,
    attachment_role TEXT NOT NULL,
    extracted_text_uri TEXT,
    downloaded_at TIMESTAMPTZ,
    CHECK ((checksum_sha256 IS NULL AND object_uri IS NULL) OR (checksum_sha256 IS NOT NULL AND object_uri IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS document_sections (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    section_id TEXT NOT NULL,
    heading TEXT NOT NULL,
    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    text_object_uri TEXT,
    source_span_id TEXT,
    PRIMARY KEY (document_id, section_id)
);

CREATE TABLE IF NOT EXISTS document_links (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    url TEXT NOT NULL,
    label TEXT,
    relation TEXT,
    PRIMARY KEY (document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS hearing_details (
    document_id TEXT PRIMARY KEY REFERENCES documents(document_id) ON DELETE CASCADE,
    hearing_status TEXT,
    hearing_deadline DATE,
    hearing_letter_section_id TEXT,
    hearing_note_attachment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    submission_url TEXT,
    hearing_responses_url TEXT
);

CREATE TABLE IF NOT EXISTS hearing_recipients (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    label TEXT NOT NULL,
    uri TEXT,
    PRIMARY KEY (document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS contacts (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    label TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    organization TEXT,
    PRIMARY KEY (document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS field_provenance (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    field_path TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_artifact_uri TEXT NOT NULL,
    css_selector TEXT,
    source_span_id TEXT,
    extraction_method TEXT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL,
    confidence DOUBLE PRECISION,
    PRIMARY KEY (document_id, field_path, source_artifact_uri)
);

CREATE TABLE IF NOT EXISTS crawl_batches (
    crawl_batch_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    user_agent TEXT NOT NULL,
    seed_url TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_events (
    fetch_event_id BIGSERIAL PRIMARY KEY,
    crawl_batch_id TEXT REFERENCES crawl_batches(crawl_batch_id),
    request_url TEXT NOT NULL,
    final_url TEXT,
    status_code INTEGER,
    fetched_at TIMESTAMPTZ NOT NULL,
    checksum_sha256 TEXT,
    object_uri TEXT,
    error_type TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    version_id TEXT PRIMARY KEY REFERENCES document_versions(version_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    parser_version TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    error_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS parser_errors (
    parser_error_id BIGSERIAL PRIMARY KEY,
    document_id TEXT REFERENCES documents(document_id) ON DELETE CASCADE,
    version_id TEXT REFERENCES document_versions(version_id) ON DELETE CASCADE,
    field_path TEXT,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_attachments_document ON document_attachments(document_id);
CREATE INDEX IF NOT EXISTS idx_document_attachments_checksum ON document_attachments(checksum_sha256);
CREATE INDEX IF NOT EXISTS idx_documents_type_date ON documents(document_type, publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_events_request_url ON fetch_events(request_url);
