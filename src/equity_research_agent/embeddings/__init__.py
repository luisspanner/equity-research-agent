"""Text-to-vector embedding for retrieval over filing chunks."""

from equity_research_agent.embeddings.protocol import (
    EmbeddingInputType,
    EmbeddingProvider,
)
from equity_research_agent.embeddings.store import (
    InMemoryVectorStore,
    VectorSearchResult,
    cosine_similarity,
)
from equity_research_agent.embeddings.voyage import (
    VoyageEmbeddingProvider,
    VoyageEmbeddingProviderError,
)

__all__ = [
    "EmbeddingInputType",
    "EmbeddingProvider",
    "InMemoryVectorStore",
    "VectorSearchResult",
    "VoyageEmbeddingProvider",
    "VoyageEmbeddingProviderError",
    "cosine_similarity",
]
