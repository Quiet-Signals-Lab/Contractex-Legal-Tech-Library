# Re-export the canonical OllamaEmbedder from the retrieval package.
# The retrieval implementation is more complete (host support, error handling,
# dimensions property) so we keep a single definition there.
from contractex.retrieval.embedder import EmbeddingError, OllamaEmbedder

__all__ = ["OllamaEmbedder", "EmbeddingError"]
