"""In-memory vector storage and cosine-similarity retrieval over filing chunks.

Deliberately just a list: at the scale of one filing's chunks, brute-force
scoring against every stored vector is fast enough, and an approximate
nearest-neighbor index (pgvector/HNSW) is unjustified complexity until real
persistence and scale exist -- see ROADMAP.md Phase 2.5.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from equity_research_agent.models.filings import FilingChunk


@dataclass(frozen=True)
class VectorSearchResult:
    """One retrieved chunk together with its similarity to the query."""

    chunk: FilingChunk
    score: float


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the cosine of the angle between two equal-length vectors.

    Raises ``ValueError`` for mismatched lengths or a zero vector, since a
    zero vector has no direction and cosine similarity is undefined for it.
    """

    if len(a) != len(b):
        raise ValueError("vectors must have the same length")

    dot_product = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("cosine similarity is undefined for a zero vector")

    return dot_product / (norm_a * norm_b)


class InMemoryVectorStore:
    """A list of (chunk, vector) pairs searched by brute-force cosine similarity.

    Vectors are the caller's responsibility to produce: the store neither
    calls an ``EmbeddingProvider`` nor knows one exists, keeping it trivially
    testable with hand-written vectors.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[FilingChunk, list[float]]] = []
        self._dimension: int | None = None

    def add(
        self, chunks: Sequence[FilingChunk], vectors: Sequence[Sequence[float]]
    ) -> None:
        """Add chunks and their embedding vectors, in matching order."""

        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")

        for vector in vectors:
            if not vector:
                raise ValueError("vector must not be empty")
            if self._dimension is None:
                self._dimension = len(vector)
            elif len(vector) != self._dimension:
                raise ValueError(
                    f"vector has dimension {len(vector)}, expected {self._dimension}"
                )

        for chunk, vector in zip(chunks, vectors, strict=True):
            self._entries.append((chunk, list(vector)))

    def search(
        self, query_vector: Sequence[float], *, top_k: int
    ) -> list[VectorSearchResult]:
        """Return the ``top_k`` stored chunks most similar to ``query_vector``.

        Returns fewer than ``top_k`` results if the store holds fewer entries,
        and an empty list for an empty store.
        """

        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not self._entries:
            return []
        if self._dimension is not None and len(query_vector) != self._dimension:
            raise ValueError(
                f"query vector has dimension {len(query_vector)}, "
                f"expected {self._dimension}"
            )

        scored = [
            VectorSearchResult(
                chunk=chunk, score=cosine_similarity(query_vector, vector)
            )
            for chunk, vector in self._entries
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:top_k]
