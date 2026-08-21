"""Provider-agnostic contract for turning text into embedding vectors."""

from collections.abc import Sequence
from typing import Literal, Protocol, TypeAlias

EmbeddingInputType: TypeAlias = Literal["query", "document"]
"""Which side of a retrieval search a text belongs to.

Voyage AI, like several embedding APIs, encodes queries and the documents
they search over slightly differently, so callers must state which one a
text is: filing chunks are always embedded as ``"document"`` at indexing
time, and a retrieval question is always embedded as ``"query"`` at search
time.
"""


class EmbeddingProvider(Protocol):
    """A provider that turns text into fixed-length embedding vectors.

    Implementations return one vector per input text, in the same order as
    ``texts``, so callers can zip the result back onto whatever the texts
    came from without needing an explicit identifier round-trip.
    """

    def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> list[list[float]]: ...
