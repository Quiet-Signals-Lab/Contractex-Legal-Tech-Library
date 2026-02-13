# Building a Clause Retrieval System — Implementation Guide

This guide walks you through building a full RAG retrieval pipeline on top of the
existing ContractEx infrastructure. The goal is that you implement each step
yourself, understanding **why** each piece exists and how it connects to the others.

---

## How the system fits together

Before touching any code, here is the mental model. There are two distinct phases:

**Ingestion** (happens once, or when new documents arrive):
```
stored clauses → generate embeddings (Ollama) → save vectors to pgvector
                                               → update full-text search index
```

**Query** (happens on every search request):
```
user query → embed query → vector search (semantic)
                        → lexical search (keyword)  → RRF fusion → rerank → results
                        → metadata filter
```

These two phases are kept intentionally separate. If Ollama is down you can still
do lexical searches. If embeddings haven't been generated yet for a document, it
just won't appear in vector results.

---

## Prerequisites

### 1. Install pgvector in PostgreSQL

pgvector is a PostgreSQL extension. You need to install it on the server before
you can use it in SQL.

On macOS with Homebrew:
```bash
brew install pgvector
```

Then inside psql, for your database:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Tip**: The extension only needs to be created once per database, not per table.
If you run `\dx` in psql and see `vector` listed, you're good.

### 2. Pull the Ollama embedding model

```bash
ollama pull nomic-embed-text
```

nomic-embed-text generates **768-dimensional** vectors. You must know this number
before creating the column — it's baked into the schema. Different models produce
different dimensions (OpenAI's ada-002 is 1536, MiniLM-L6 is 384).

### 3. Install Python dependencies

```bash
pip install pgvector sentence-transformers ollama
```

Or add to pyproject.toml under a new `retrieval` optional extra:
```toml
retrieval = ["pgvector>=0.3.0", "sentence-transformers>=2.0.0", "ollama>=0.1.0"]
```

---

## Step 1 — Database migration

**File to create**: `contractex/storage/migrations/001_add_embeddings.sql`

You need to add two new columns to the existing `clauses` table:

1. `embedding VECTOR(768)` — the pgvector type for storing floating-point vectors
2. `search_vector TSVECTOR` — PostgreSQL's built-in full-text search type

```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE clauses ADD COLUMN IF NOT EXISTS embedding VECTOR(768);
ALTER TABLE clauses ADD COLUMN IF NOT EXISTS search_vector TSVECTOR;
```

**Why VECTOR(768)?** pgvector needs to know the dimension at column-creation time
so it can validate inputs and build efficient indexes. 768 matches nomic-embed-text.

**Why TSVECTOR?** PostgreSQL has built-in full-text search. A `tsvector` is a
pre-processed, indexed representation of text — it strips stop words, applies
stemming, etc. You populate it once from `clause_text` and then query with
`tsquery`. No extra database or service needed.

Next, add a **trigger** to keep `search_vector` automatically in sync:

```sql
CREATE OR REPLACE FUNCTION clauses_fts_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', coalesce(NEW.clause_text, ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clauses_fts
    BEFORE INSERT OR UPDATE ON clauses
    FOR EACH ROW EXECUTE FUNCTION clauses_fts_update();

-- Backfill existing rows
UPDATE clauses
SET search_vector = to_tsvector('english', coalesce(clause_text, ''))
WHERE search_vector IS NULL;
```

**Tip**: A trigger means you never have to remember to update the FTS column in
your Python code. It happens automatically every time a clause is inserted or
updated.

Then add indexes. These make queries fast but take space and slow down writes
slightly — a worthwhile trade-off for search:

```sql
-- IVFFlat for approximate nearest-neighbour vector search
-- 'lists' = roughly sqrt(number of rows) is a good starting value
CREATE INDEX IF NOT EXISTS idx_clauses_embedding
    ON clauses USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- GIN for full-text search (standard approach)
CREATE INDEX IF NOT EXISTS idx_clauses_fts
    ON clauses USING GIN (search_vector);
```

**Tip**: The IVFFlat index needs data to train on. Create it after you have at
least a few hundred rows, otherwise it falls back to a sequential scan anyway.

Run the migration:
```bash
psql clause_docs < contractex/storage/migrations/001_add_embeddings.sql
```

---

## Step 2 — The `SearchResult` model

**File to create**: `contractex/retrieval/models.py`

Every search strategy should return a consistent type. Define a `SearchResult`
dataclass that carries all the information a caller might need:

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SearchResult:
    clause_id: int
    document_id: int
    document_filename: str
    clause_text: str
    clause_type: Optional[str]
    page_number: Optional[int]
    confidence_score: Optional[float]
    score: float           # 0.0 – 1.0, higher is more relevant
    search_type: str       # 'vector' | 'lexical' | 'hybrid'
    rank: int              # 1-based position in the result list
    metadata: dict = field(default_factory=dict)
```

**Tip**: Using a dataclass (rather than a dict) means you get autocomplete, type
checking, and a clear contract about what callers can expect.

---

## Step 3 — The embedder

**File to create**: `contractex/retrieval/embedder.py`

The embedder has one job: turn text into a list of floats. Wrap the `ollama`
package (already in your dependencies under `[local]`):

```python
import ollama

class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text"):
        self.model = model

    def embed(self, text: str) -> list[float]:
        response = ollama.embeddings(model=self.model, prompt=text)
        return response["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # ollama doesn't have a native batch API, so call embed() in a loop
        # You can make this concurrent with ThreadPoolExecutor if speed matters
        return [self.embed(t) for t in texts]
```

**Tip**: Keep the embedder stateless and simple. Don't put retry logic, caching,
or batch optimisation in here yet — that can come later. The `embed_batch` method
exists so callers can express intent; the optimisation is an implementation detail.

**Testing**: Before wiring this into the pipeline, test it directly:
```python
embedder = OllamaEmbedder()
vec = embedder.embed("termination for convenience")
assert len(vec) == 768
assert all(isinstance(v, float) for v in vec)
```

---

## Step 4 — Extend the storage layer

**File to modify**: `contractex/storage/models.py`

Add the `embedding` field to the existing `Clause` dataclass. Make it optional
so existing code that creates `Clause` objects without embeddings still works:

```python
embedding: Optional[list[float]] = None
```

**File to modify**: `contractex/storage/repository.py`

Add these methods to `ClauseRepository`:

```python
def update_embedding(self, clause_id: int, embedding: list[float]) -> None:
    """Store a vector embedding for a clause."""
    query = "UPDATE clauses SET embedding = %s WHERE id = %s"
    with get_cursor() as cur:
        cur.execute(query, (embedding, clause_id))

def update_embeddings_batch(self, pairs: list[tuple[int, list[float]]]) -> None:
    """Bulk-update embeddings. pairs = [(clause_id, embedding), ...]"""
    query = "UPDATE clauses SET embedding = %s WHERE id = %s"
    with get_cursor() as cur:
        cur.executemany(query, [(emb, cid) for cid, emb in pairs])

def get_unembedded(self, document_id: Optional[int] = None) -> list[Clause]:
    """Return clauses that don't have embeddings yet."""
    query = "SELECT ... FROM clauses WHERE embedding IS NULL"
    if document_id:
        query += " AND document_id = %s"
    # ... fetch and return list[Clause]
```

**Tip**: The `pgvector` Python package registers a custom psycopg2 adapter so
you can pass a plain Python `list[float]` and it handles the `::vector` casting.
You need to call `register_vector(conn)` once after connecting. The cleanest place
is in `get_cursor()` in `connection.py`, or you can do it in each repository method.

```python
from pgvector.psycopg2 import register_vector

# Add this after creating the connection in get_connection():
register_vector(conn)
```

---

## Step 5 — The ingestion pipeline

**File to create**: `contractex/retrieval/ingest.py`

This orchestrates the flow: fetch unembedded clauses → generate embeddings → store.

```python
class EmbeddingPipeline:
    def __init__(
        self,
        embedder: OllamaEmbedder,
        clause_repo: ClauseRepository,
        batch_size: int = 32,
    ):
        self.embedder = embedder
        self.clause_repo = clause_repo
        self.batch_size = batch_size

    def ingest_document(self, document_id: int) -> int:
        """Embed all unembedded clauses for one document. Returns count."""
        clauses = self.clause_repo.get_unembedded(document_id=document_id)
        return self._process(clauses)

    def ingest_all(self) -> int:
        """Embed all unembedded clauses across the whole database."""
        clauses = self.clause_repo.get_unembedded()
        return self._process(clauses)

    def _process(self, clauses: list[Clause]) -> int:
        count = 0
        for i in range(0, len(clauses), self.batch_size):
            batch = clauses[i : i + self.batch_size]
            texts = [c.clause_text for c in batch]
            embeddings = self.embedder.embed_batch(texts)
            pairs = [(c.id, emb) for c, emb in zip(batch, embeddings)]
            self.clause_repo.update_embeddings_batch(pairs)
            count += len(batch)
        return count
```

**Tip**: Process in batches rather than one-at-a-time. Each Ollama call has
network overhead; batching amortises that cost. `batch_size=32` is a safe default
— increase it if Ollama handles it without OOM errors.

---

## Step 6 — Vector search

**File to create**: `contractex/retrieval/strategies/vector_search.py`

```python
class VectorSearch:
    def __init__(self, embedder: OllamaEmbedder):
        self.embedder = embedder

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[SearchResult]:
        embedding = self.embedder.embed(query)
        # Build SQL with optional filters, then execute
        ...
```

The core SQL query:
```sql
SELECT
    c.id, c.document_id, d.filename, c.clause_text, c.clause_type,
    c.page_number, c.confidence_score, c.metadata,
    1 - (c.embedding <=> %s::vector) AS score
FROM clauses c
JOIN documents d ON c.document_id = d.id
WHERE c.embedding IS NOT NULL
ORDER BY c.embedding <=> %s::vector    -- ASC = closest first
LIMIT %s
```

**Why `1 - distance`?** pgvector's `<=>` is cosine **distance** (0 = identical,
2 = opposite). Subtracting from 1 turns it into a **similarity** score (1 = identical).
This makes it consistent with other scores where higher = better.

**Tip on filters**: Build the WHERE clause dynamically. Keep a list of conditions
and a list of params, then join with `AND`. Never do string interpolation with
user input — always use parameterised queries:
```python
conditions = ["c.embedding IS NOT NULL"]
params = [embedding]
if filters and "clause_type" in filters:
    conditions.append("c.clause_type = %s")
    params.append(filters["clause_type"])
where = " AND ".join(conditions)
```

---

## Step 7 — Lexical search

**File to create**: `contractex/retrieval/strategies/lexical_search.py`

```python
class LexicalSearch:
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[SearchResult]:
        ...
```

Core SQL:
```sql
SELECT
    c.id, c.document_id, d.filename, c.clause_text, c.clause_type,
    c.page_number, c.confidence_score, c.metadata,
    ts_rank(c.search_vector, plainto_tsquery('english', %s)) AS score
FROM clauses c
JOIN documents d ON c.document_id = d.id
WHERE c.search_vector @@ plainto_tsquery('english', %s)
ORDER BY score DESC
LIMIT %s
```

**`plainto_tsquery` vs `phraseto_tsquery` vs `websearch_to_tsquery`?**
- `plainto_tsquery`: treats the query as a bag of words (AND logic). Good default.
- `phraseto_tsquery`: matches words in the exact order. Use for exact phrases.
- `websearch_to_tsquery`: supports `+`, `-`, `"phrase"` syntax like Google. Most user-friendly.

Start with `plainto_tsquery` — it's the safest and most predictable.

**Tip**: `ts_rank` scores are not normalised to 0–1. They depend on document length
and term frequency. This matters when fusing with vector scores in hybrid search —
you may want to normalise lexical scores before combining them.

---

## Step 8 — Metadata filter

**File to create**: `contractex/retrieval/strategies/metadata_filter.py`

This is a utility, not a standalone search strategy. It generates SQL WHERE clauses
from a dict. Both `VectorSearch` and `LexicalSearch` can call it internally.

```python
class MetadataFilter:
    @staticmethod
    def build(filters: dict) -> tuple[str, list]:
        """
        Returns (where_clause, params) for use in SQL queries.

        Supported filter keys:
            document_id: int | list[int]
            clause_type: str | list[str]
            min_confidence: float
            max_confidence: float
        """
        conditions = []
        params = []

        if "document_id" in filters:
            val = filters["document_id"]
            if isinstance(val, list):
                conditions.append(f"c.document_id = ANY(%s)")
                params.append(val)
            else:
                conditions.append("c.document_id = %s")
                params.append(val)

        if "clause_type" in filters:
            val = filters["clause_type"]
            if isinstance(val, list):
                conditions.append("c.clause_type = ANY(%s)")
                params.append(val)
            else:
                conditions.append("c.clause_type = %s")
                params.append(val)

        if "min_confidence" in filters:
            conditions.append("c.confidence_score >= %s")
            params.append(filters["min_confidence"])

        return (" AND ".join(conditions), params)
```

**Tip**: Keeping filter logic in one place means you don't duplicate the same
`if "clause_type" in filters` logic across every search class.

---

## Step 9 — Hybrid search with RRF

**File to create**: `contractex/retrieval/strategies/hybrid_search.py`

**Reciprocal Rank Fusion** is a simple, parameter-light algorithm for combining
ranked lists from different retrieval methods. The idea: if a document appears
in position 3 in the vector results AND position 5 in the lexical results, it
probably is genuinely relevant. The formula:

```
RRF_score(doc) = Σ  weight_i / (k + rank_i)
```

Where `k=60` is a constant that dampens the impact of high rankings (the "60"
is empirically derived — it works well in practice), and `rank_i` is the 1-based
position of the document in list `i`.

```python
def _reciprocal_rank_fusion(
    vector_results: list[SearchResult],
    lexical_results: list[SearchResult],
    k: int = 60,
    vector_weight: float = 0.7,
    lexical_weight: float = 0.3,
) -> list[SearchResult]:
    scores: dict[int, float] = {}  # clause_id -> fused score
    all_results: dict[int, SearchResult] = {}

    for rank, result in enumerate(vector_results, start=1):
        scores[result.clause_id] = scores.get(result.clause_id, 0.0)
        scores[result.clause_id] += vector_weight / (k + rank)
        all_results[result.clause_id] = result

    for rank, result in enumerate(lexical_results, start=1):
        scores[result.clause_id] = scores.get(result.clause_id, 0.0)
        scores[result.clause_id] += lexical_weight / (k + rank)
        all_results[result.clause_id] = result

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)

    fused = []
    for rank, cid in enumerate(sorted_ids, start=1):
        result = all_results[cid]
        fused.append(SearchResult(
            **{f: getattr(result, f) for f in result.__dataclass_fields__ if f not in ('score', 'search_type', 'rank')},
            score=scores[cid],
            search_type="hybrid",
            rank=rank,
        ))
    return fused
```

**Tip**: Fetch `top_k * 3` results from each sub-search before fusing. RRF
combines ranked lists, so you need more candidates than you ultimately return
(some might not appear in both lists).

---

## Step 10 — Cross-encoder reranker

**File to create**: `contractex/retrieval/rerankers/cross_encoder_reranker.py`

The previous steps used **bi-encoders**: embed query independently, embed each
clause independently, compare dot products. Fast but lossy.

A **cross-encoder** sees the query AND the clause together in a single forward
pass, which gives much better relevance scores — but it's too slow to run on
thousands of documents. The standard pattern: use bi-encoder to get top 50
candidates cheaply, then rerank the 50 with a cross-encoder.

```python
from sentence_transformers.cross_encoder import CrossEncoder

class CrossEncoderReranker:
    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        # ms-marco-MiniLM-L-6-v2 is ~85MB, fast, and good for passage relevance
        self.model = CrossEncoder(model)

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: Optional[int] = None,
    ) -> list[SearchResult]:
        if not results:
            return results

        # Build (query, passage) pairs for the cross-encoder
        pairs = [(query, r.clause_text) for r in results]

        # Get scores — these are logits/raw scores, not necessarily 0-1
        scores = self.model.predict(pairs)

        # Sort by score descending and reassign ranks
        ranked = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)

        reranked = []
        for rank, (score, result) in enumerate(ranked[:top_k], start=1):
            reranked.append(SearchResult(
                **{f: getattr(result, f) for f in result.__dataclass_fields__ if f not in ('score', 'rank')},
                score=float(score),
                rank=rank,
            ))
        return reranked
```

**Tip**: `ms-marco-MiniLM-L-6-v2` is fine for English legal text. If you need
to match exact CUAD clause types, consider fine-tuning on CUAD data later.

---

## Step 11 — The main `ClauseRetriever`

**File to modify**: `contractex/retrieval/retrieval.py` (currently empty)

This is the public-facing class. Callers should only need to interact with this,
not with the individual strategies:

```python
class ClauseRetriever:
    def __init__(
        self,
        embedder: Optional[OllamaEmbedder] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        search_mode: str = "hybrid",  # 'vector' | 'lexical' | 'hybrid'
        rerank: bool = True,
    ):
        self.embedder = embedder or OllamaEmbedder()
        self.reranker = reranker or CrossEncoderReranker() if rerank else None
        self.search_mode = search_mode

        # Compose strategies
        vector = VectorSearch(self.embedder)
        lexical = LexicalSearch()
        self._hybrid = HybridSearch(vector, lexical)
        self._vector = vector
        self._lexical = lexical

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[dict] = None,
        rerank: Optional[bool] = None,
    ) -> list[SearchResult]:

        # Fetch more candidates than needed if we're going to rerank
        fetch_k = top_k * 3 if (rerank or self.reranker) else top_k

        if self.search_mode == "hybrid":
            results = self._hybrid.search(query, top_k=fetch_k, filters=filters)
        elif self.search_mode == "vector":
            results = self._vector.search(query, top_k=fetch_k, filters=filters)
        else:
            results = self._lexical.search(query, top_k=fetch_k, filters=filters)

        should_rerank = rerank if rerank is not None else (self.reranker is not None)
        if should_rerank and self.reranker:
            results = self.reranker.rerank(query, results, top_k=top_k)
        else:
            results = results[:top_k]

        return results

    def find_similar(
        self,
        clause_text: str,
        top_k: int = 5,
        exclude_clause_id: Optional[int] = None,
    ) -> list[SearchResult]:
        """Find clauses semantically similar to the given text."""
        results = self._vector.search(clause_text, top_k=top_k + 1)
        if exclude_clause_id:
            results = [r for r in results if r.clause_id != exclude_clause_id]
        return results[:top_k]
```

---

## Step 12 — Wire up the public API

**File to modify**: `contractex/retrieval/__init__.py`

```python
from contractex.retrieval.retrieval import ClauseRetriever
from contractex.retrieval.models import SearchResult
from contractex.retrieval.embedder import OllamaEmbedder
from contractex.retrieval.ingest import EmbeddingPipeline

__all__ = ["ClauseRetriever", "SearchResult", "OllamaEmbedder", "EmbeddingPipeline"]
```

---

## How to test as you go

Test each layer independently before wiring them together.

**Test the embedder first** (requires Ollama running):
```python
from contractex.retrieval.embedder import OllamaEmbedder
e = OllamaEmbedder()
v = e.embed("indemnification for third party claims")
assert len(v) == 768
print(v[:5])  # Should be small floats like [0.032, -0.14, ...]
```

**Test vector search in isolation** (requires embedded rows in DB):
```python
from contractex.retrieval.strategies.vector_search import VectorSearch
from contractex.retrieval.embedder import OllamaEmbedder
vs = VectorSearch(OllamaEmbedder())
results = vs.search("termination clause")
for r in results:
    print(r.clause_type, r.score, r.clause_text[:80])
```

**Test lexical search** (works without embeddings):
```python
from contractex.retrieval.strategies.lexical_search import LexicalSearch
ls = LexicalSearch()
results = ls.search("net 30 payment")
```

**End-to-end**:
```python
from contractex.retrieval import ClauseRetriever
r = ClauseRetriever()
results = r.search("automatic renewal without notice")
```

---

## Common gotchas

- **"column embedding does not exist"** — you haven't run the migration yet, or
  ran it against the wrong database.
- **"extension vector does not exist"** — pgvector isn't installed on the Postgres
  server. On macOS: `brew install pgvector`.
- **Zero vector search results** — embeddings haven't been generated yet. Run
  `EmbeddingPipeline.ingest_all()` first.
- **pgvector type error from psycopg2** — you need to call `register_vector(conn)`
  after opening the connection. See Step 4.
- **IVFFlat index not used** — the index needs at least `lists * 3` rows to be
  useful. With a small dataset, Postgres will use a sequential scan instead (which
  is fine for development).
- **Cross-encoder downloading 85MB on first run** — expected behaviour from
  `sentence-transformers`. The model is cached in `~/.cache/torch/` after that.
