-- =============================================================================
-- ContractEx Storage: Migration v1 → v2
--
-- Run this script ONCE on an existing v1 database to upgrade to schema_v2.
-- Always take a full backup before running migrations.
--
-- Migration steps:
--   1. Create new tables (legal_docs, extracted_fields, document_chunks)
--   2. Migrate existing documents data → legal_docs
--   3. Migrate existing clauses data → extracted_fields
--   4. Rename old tables to _v1_archive (do not drop — allows rollback)
--   5. Create clauses VIEW over extracted_fields
--   6. Create audit_log table
--   7. Create pgvector extension and document_chunks table
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 0 — Guard: abort if already migrated
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'legal_docs'
    ) THEN
        RAISE EXCEPTION 'Migration already applied: legal_docs table already exists.';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Step 1 — Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ---------------------------------------------------------------------------
-- Step 2 — Create new tables
-- ---------------------------------------------------------------------------

CREATE TABLE legal_docs (
    id              SERIAL PRIMARY KEY,
    doc_id          UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    doc_type        VARCHAR(50)  NOT NULL DEFAULT 'contract',
    jurisdiction    VARCHAR(100),
    language        CHAR(5) DEFAULT 'en',
    title           TEXT,
    source_url      TEXT,
    content_hash    VARCHAR(64),
    full_text       TEXT,
    privacy_profile JSONB NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    etag            VARCHAR(255),
    last_modified   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE extracted_fields (
    id              SERIAL PRIMARY KEY,
    doc_id          UUID NOT NULL REFERENCES legal_docs(doc_id) ON DELETE CASCADE,
    field_name      VARCHAR(200) NOT NULL,
    field_value     JSONB,
    confidence      FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    source_span     JSONB,
    redacted        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE document_chunks (
    id              SERIAL PRIMARY KEY,
    doc_id          UUID NOT NULL REFERENCES legal_docs(doc_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    chunk_metadata  JSONB NOT NULL DEFAULT '{}',
    embedding       vector(384),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    doc_id          VARCHAR(200),
    event_type      VARCHAR(50) NOT NULL,
    event_data      JSONB NOT NULL DEFAULT '{}',
    user_id         VARCHAR(200),
    session_id      VARCHAR(200),
    ip_address      INET,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Step 3 — Migrate documents → legal_docs
-- ---------------------------------------------------------------------------

INSERT INTO legal_docs (
    doc_type, title, content_hash, full_text, metadata, created_at
)
SELECT
    'contract',
    COALESCE(metadata->>'contract_type', filename),
    file_hash,
    extracted_text,
    jsonb_build_object(
        'filename', filename,
        'original_metadata', metadata
    ),
    uploaded_at
FROM documents
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Step 4 — Migrate clauses → extracted_fields
-- ---------------------------------------------------------------------------

INSERT INTO extracted_fields (
    doc_id, field_name, field_value, confidence, created_at
)
SELECT
    ld.doc_id,
    'clause_' || COALESCE(c.clause_type, 'unknown'),
    jsonb_build_object(
        'text',           c.clause_text,
        'clause_type',    c.clause_type,
        'page_number',    c.page_number,
        'section_number', c.section_number
    ),
    c.confidence_score,
    c.created_at
FROM clauses c
JOIN documents d ON d.id = c.document_id
JOIN legal_docs ld ON ld.content_hash = d.file_hash
    OR ld.title = COALESCE(d.metadata->>'contract_type', d.filename);

-- ---------------------------------------------------------------------------
-- Step 5 — Archive old tables
-- ---------------------------------------------------------------------------

ALTER TABLE documents RENAME TO documents_v1_archive;
ALTER TABLE clauses   RENAME TO clauses_v1_archive;

-- ---------------------------------------------------------------------------
-- Step 6 — Create clauses VIEW for backward compatibility
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW clauses AS
SELECT
    ef.id,
    ld.id                                       AS document_id,
    ef.doc_id,
    (ef.field_value ->> 'text')                 AS clause_text,
    ef.field_name                               AS clause_type,
    (ef.field_value ->> 'page_number')::INTEGER AS page_number,
    (ef.field_value ->> 'section_number')       AS section_number,
    ef.confidence,
    ef.redacted,
    ef.source_span,
    ef.created_at
FROM extracted_fields ef
JOIN legal_docs ld ON ld.doc_id = ef.doc_id
WHERE ld.doc_type = 'contract'
  AND ef.field_name LIKE 'clause_%'
  AND ef.field_value IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Step 7 — Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX idx_legal_docs_doc_type      ON legal_docs (doc_type);
CREATE INDEX idx_legal_docs_source_url    ON legal_docs (source_url) WHERE source_url IS NOT NULL;
CREATE INDEX idx_legal_docs_content_hash  ON legal_docs (content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX idx_legal_docs_metadata      ON legal_docs USING GIN (metadata jsonb_path_ops);
CREATE INDEX idx_legal_docs_privacy       ON legal_docs USING GIN (privacy_profile jsonb_path_ops);
CREATE INDEX idx_extracted_fields_doc_id  ON extracted_fields (doc_id);
CREATE INDEX idx_extracted_fields_name    ON extracted_fields (field_name);
CREATE INDEX idx_chunks_doc_id            ON document_chunks (doc_id);
CREATE INDEX idx_audit_doc_id             ON audit_log (doc_id);
CREATE INDEX idx_audit_event_type         ON audit_log (event_type);

-- IVFFlat vector index (adjust lists based on expected row count)
CREATE INDEX idx_chunks_embedding
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- Step 8 — updated_at trigger on legal_docs
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_legal_docs_updated_at
    BEFORE UPDATE ON legal_docs
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ---------------------------------------------------------------------------
-- Step 9 — GDPR erasure function
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gdpr_erase_document(p_doc_id UUID, p_hmac_key TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    hashed_id TEXT;
BEGIN
    hashed_id := encode(hmac(p_doc_id::TEXT, p_hmac_key, 'sha256'), 'hex');
    UPDATE audit_log SET doc_id = hashed_id WHERE doc_id = p_doc_id::TEXT;
    DELETE FROM legal_docs WHERE doc_id = p_doc_id;
    INSERT INTO audit_log (doc_id, event_type, event_data)
    VALUES (hashed_id, 'gdpr_erasure_completed',
            jsonb_build_object('original_doc_id_hash', hashed_id, 'erased_at', NOW()));
END;
$$;

COMMIT;
