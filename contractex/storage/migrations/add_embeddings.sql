-- Migration: Add vector embeddings and full-text search to clauses table
-- Run with: psql clause_docs < contractex/storage/migrations/add_embeddings.sql

-- Enable pgvector extension (requires pgvector installed on the PostgreSQL server)
-- macOS: brew install pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column (nomic-embed-text produces 768-dimensional vectors)
ALTER TABLE clauses ADD COLUMN IF NOT EXISTS embedding VECTOR(768);

-- Add full-text search column
ALTER TABLE clauses ADD COLUMN IF NOT EXISTS search_vector TSVECTOR;

-- Trigger: auto-update search_vector whenever clause_text is inserted or changed
CREATE OR REPLACE FUNCTION clauses_fts_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', coalesce(NEW.clause_text, ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_clauses_fts ON clauses;
CREATE TRIGGER trg_clauses_fts
    BEFORE INSERT OR UPDATE ON clauses
    FOR EACH ROW EXECUTE FUNCTION clauses_fts_update();

-- Backfill search_vector for existing rows
UPDATE clauses
SET search_vector = to_tsvector('english', coalesce(clause_text, ''))
WHERE search_vector IS NULL;

-- IVFFlat index for approximate nearest-neighbour vector search
-- Note: build this after loading data; with few rows Postgres falls back to seq scan
CREATE INDEX IF NOT EXISTS idx_clauses_embedding
    ON clauses USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_clauses_fts
    ON clauses USING GIN (search_vector);
