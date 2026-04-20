-- =============================================================================
-- ContractEx Storage Schema v2
-- Generic extraction storage model supporting all document types.
--
-- Replaces schema_v1 (schema.sql).
-- Run migration script (migrations/v1_to_v2.sql) to upgrade existing data.
--
-- Key design decisions:
-- * legal_docs replaces documents — adds doc_type, privacy_profile, content_hash
-- * extracted_fields replaces the contract-specific clauses table;
--   it stores any field from any document type
-- * clauses is retained as a VIEW over extracted_fields for backward compat
-- * audit_log supports GDPR Art. 17 erasure — doc_id is hashed on deletion
-- * pgvector extension powers semantic search for RAG
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector for embeddings

-- ---------------------------------------------------------------------------
-- 1. legal_docs  — central registry for all document types
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS legal_docs (
    id              SERIAL PRIMARY KEY,
    doc_id          UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    doc_type        VARCHAR(50)  NOT NULL DEFAULT 'unknown',
                    -- DocType values: contract, statute, regulation, case_opinion,
                    --   identity_doc, government_form, pleading, correspondence, unknown

    jurisdiction    VARCHAR(100),
    language        CHAR(5) DEFAULT 'en',
    title           TEXT,

    -- Source provenance
    source_url      TEXT,
    content_hash    VARCHAR(64),           -- SHA-256 for deduplication

    -- Full text (may be omitted for large docs stored externally)
    full_text       TEXT,

    -- Privacy and sensitivity controls (serialised PrivacyProfile)
    privacy_profile JSONB NOT NULL DEFAULT '{}',

    -- Flexible metadata (LegalDocumentMetadata serialised)
    metadata        JSONB NOT NULL DEFAULT '{}',

    -- ETag-based freshness tracking for URL sources
    etag            VARCHAR(255),
    last_modified   TEXT,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_legal_docs_doc_type
    ON legal_docs (doc_type);

CREATE INDEX IF NOT EXISTS idx_legal_docs_source_url
    ON legal_docs (source_url)
    WHERE source_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_legal_docs_content_hash
    ON legal_docs (content_hash)
    WHERE content_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_legal_docs_jurisdiction
    ON legal_docs (jurisdiction)
    WHERE jurisdiction IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_legal_docs_metadata
    ON legal_docs USING GIN (metadata jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_legal_docs_privacy_profile
    ON legal_docs USING GIN (privacy_profile jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- 2. extracted_fields  — generic extraction results for any document type
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS extracted_fields (
    id              SERIAL PRIMARY KEY,
    doc_id          UUID NOT NULL REFERENCES legal_docs(doc_id) ON DELETE CASCADE,

    -- Field identity
    field_name      VARCHAR(200) NOT NULL,
                    -- e.g. "party_name", "clause_type", "expiry_date",
                    --      "passport_number", "governing_law"

    -- Value stored as JSONB to support scalar, list, and object values
    field_value     JSONB,

    -- Quality indicators
    confidence      FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    source_span     JSONB,
                    -- serialised SourceSpan:
                    -- { chunk_id, source_url, page, char_start, char_end, snippet }

    -- Privacy
    redacted        BOOLEAN NOT NULL DEFAULT FALSE,
                    -- True when field_value contains a placeholder (e.g. <PERSON_1>)
                    -- rather than the original value

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_doc_id
    ON extracted_fields (doc_id);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_field_name
    ON extracted_fields (field_name);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_doc_field
    ON extracted_fields (doc_id, field_name);

-- ---------------------------------------------------------------------------
-- 3. document_chunks  — embedding storage for RAG
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS document_chunks (
    id              SERIAL PRIMARY KEY,
    doc_id          UUID NOT NULL REFERENCES legal_docs(doc_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    chunk_metadata  JSONB NOT NULL DEFAULT '{}',
                    -- { page, char_start, char_end, section_title, ... }

    -- pgvector column — dimension determined by embedding model
    -- Default: 384 (all-MiniLM-L6-v2), override for larger models
    embedding       vector(384),

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
    ON document_chunks (doc_id);

-- IVFFlat index for approximate nearest-neighbour search
-- Tune lists = sqrt(rows) for balanced recall/speed
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_ivfflat
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- 4. audit_log  — GDPR-grade event log
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    doc_id          VARCHAR(200),
                    -- VARCHAR (not FK) because the doc may have been deleted.
                    -- On GDPR erasure: replaced with HMAC hash of original doc_id.

    event_type      VARCHAR(50) NOT NULL,
                    -- e.g. "extraction_started", "extraction_completed",
                    --      "pii_detected", "redaction_applied",
                    --      "llm_call", "gdpr_erasure_request", "doc_deleted"

    event_data      JSONB NOT NULL DEFAULT '{}',
                    -- Event-specific payload (no PII in event_data for
                    --   privacy-sensitive events)

    user_id         VARCHAR(200),
    session_id      VARCHAR(200),
    ip_address      INET,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for GDPR erasure queries and doc-level audit trails
CREATE INDEX IF NOT EXISTS idx_audit_doc_id
    ON audit_log (doc_id);

CREATE INDEX IF NOT EXISTS idx_audit_event_type
    ON audit_log (event_type);

CREATE INDEX IF NOT EXISTS idx_audit_created_at
    ON audit_log (created_at);

-- ---------------------------------------------------------------------------
-- 5. clauses  — backward-compatible VIEW over extracted_fields
--
-- Consumers that relied on the v1 clauses table continue to work via this view.
-- Writable via an INSTEAD OF trigger (not included here — add if needed).
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
-- 6. updated_at trigger
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_legal_docs_updated_at ON legal_docs;
CREATE TRIGGER trg_legal_docs_updated_at
    BEFORE UPDATE ON legal_docs
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ---------------------------------------------------------------------------
-- 7. GDPR right-to-erasure helper function
--
-- Cascades delete through extracted_fields and document_chunks.
-- Replaces doc_id in audit_log with HMAC-SHA256 hash to preserve the
-- audit trail without retaining the original identifier.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gdpr_erase_document(p_doc_id UUID, p_hmac_key TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    hashed_id TEXT;
BEGIN
    -- Hash the doc_id for audit log preservation
    hashed_id := encode(
        hmac(p_doc_id::TEXT, p_hmac_key, 'sha256'),
        'hex'
    );

    -- Update audit log before deletion (retain event history, anonymise ID)
    UPDATE audit_log
    SET doc_id = hashed_id
    WHERE doc_id = p_doc_id::TEXT;

    -- Delete the document (cascades to extracted_fields and document_chunks)
    DELETE FROM legal_docs WHERE doc_id = p_doc_id;

    -- Record the erasure itself
    INSERT INTO audit_log (doc_id, event_type, event_data)
    VALUES (
        hashed_id,
        'gdpr_erasure_completed',
        jsonb_build_object('original_doc_id_hash', hashed_id, 'erased_at', NOW())
    );
END;
$$;
