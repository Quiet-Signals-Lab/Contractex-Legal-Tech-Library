-- Database creation (run separately or handle in setup.py)
-- CREATE DATABASE clause_docs
--     WITH OWNER = aahepburn
--     ENCODING = 'UTF8'
--     LC_COLLATE = 'en_US.UTF-8'
--     LC_CTYPE = 'en_US.UTF-8'
--     TABLESPACE = pg_default
--     CONNECTION LIMIT = -1;

-- Enable pgvector extension (deferred until embeddings needed)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- ==============================================================================
-- CORE SCHEMA: Minimal Viable Tables for Document Analysis
-- Following the principle of building only what's needed now
-- ==============================================================================

-- -------------------------
-- 1. DOCUMENTS TABLE
-- Central registry for all source files
-- -------------------------
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    -- File identification
    filename VARCHAR(500) UNIQUE NOT NULL,
    file_hash VARCHAR(64),  -- SHA-256 for deduplication
    
    -- Binary storage
    file_data BYTEA,  -- Original PDF/DOCX binary
    
    -- Extracted content (added during processing)
    extracted_text TEXT,
    
    -- Flexible metadata for legal document attributes
    -- Expected fields: contract_type, parties[], effective_date, expiration_date, 
    -- governing_law, amendment_to, custom_tags[]
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    uploaded_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast metadata queries (e.g., "all NDAs from 2024")
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN (metadata jsonb_path_ops);

-- Index for hash-based deduplication
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);

-- -------------------------
-- 2. CLAUSES TABLE
-- Extracted text segments with structure
-- -------------------------
CREATE TABLE IF NOT EXISTS clauses (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Clause content
    clause_text TEXT NOT NULL,
    clause_type VARCHAR(100),  -- termination, payment, liability, indemnification, etc.
    
    -- Spatial metadata for vision/document grounding
    page_number INTEGER,
    bbox_x FLOAT,
    bbox_y FLOAT,
    bbox_width FLOAT,
    bbox_height FLOAT,
    
    -- Extraction metadata
    confidence_score FLOAT,  -- Extraction model confidence
    parent_clause_id INTEGER REFERENCES clauses(id),  -- For hierarchical structures
    
    -- Flexible metadata (clause-specific attributes)
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_clauses_document ON clauses(document_id);
CREATE INDEX IF NOT EXISTS idx_clauses_type ON clauses(clause_type);
CREATE INDEX IF NOT EXISTS idx_clauses_parent ON clauses(parent_clause_id);
CREATE INDEX IF NOT EXISTS idx_clauses_metadata ON clauses USING GIN (metadata jsonb_path_ops);

-- -------------------------
-- 3. PROCESSING_LOG TABLE
-- Audit trail for document lifecycle
-- -------------------------
CREATE TABLE IF NOT EXISTS processing_log (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Processing stage tracking
    processing_stage VARCHAR(50) NOT NULL,  -- uploaded, extracted, embedded, indexed
    status VARCHAR(20) NOT NULL,  -- pending, completed, failed
    
    -- Error handling
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for querying processing status
CREATE INDEX IF NOT EXISTS idx_processing_log_document ON processing_log(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_log_status ON processing_log(status, processing_stage);

-- ==============================================================================
-- FUTURE TABLES (NOT YET IMPLEMENTED)
-- ==============================================================================
-- When ready for embeddings, add:
-- - text_embedding VECTOR(1536) to clauses table OR
-- - separate embeddings table with clause_id, embedding_type, model_version, vector
--
-- When ready for multimodal vision:
-- - document_images table with page_number, image_data, ocr_text, layout_type
--
-- When scaling to multi-user:
-- - users, roles, permissions tables with owner_id in documents
--
-- When implementing contract comparison:
-- - document_relationships table with relationship_type (amendment, related, supersedes)
-- ==============================================================================

