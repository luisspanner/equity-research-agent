"""Voyage AI implementation of the embedding-provider contract.

Plain HTTP against Voyage's REST endpoint, with no SDK dependency: the
request/response shape is a single small JSON contract, so a dependency
would wrap something already this thin.
"""

import json
import os
from collections.abc import Sequence
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from equity_research_agent.embeddings.protocol import EmbeddingInputType

_VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
_VOYAGE_USER_AGENT = "equity-research-agent/0.1"


class VoyageEmbeddingProviderError(RuntimeError):
    """Raised when a Voyage AI response cannot be used safely."""


class VoyageEmbeddingProvider:
    """Embed text with Voyage AI's embeddings endpoint."""

    _DEFAULT_MODEL = "voyage-4"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Create a provider with explicit credentials and request settings."""

        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if not model.strip():
            raise ValueError("model must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "VoyageEmbeddingProvider":
        """Create a provider from the ``VOYAGE_API_KEY`` environment variable."""

        api_key = os.environ.get("VOYAGE_API_KEY")
        if api_key is None:
            raise ValueError("VOYAGE_API_KEY environment variable is not set")
        return cls(api_key)

    def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> list[list[float]]:
        """Return one embedding vector per text, in ``texts`` order.

        Raises ``ValueError`` for an empty ``texts`` sequence, which is a
        caller error rather than a transport failure.
        """

        if not texts:
            raise ValueError("texts must not be empty")

        request_body = {
            "input": list(texts),
            "model": self._model,
            "input_type": input_type,
        }
        request = Request(
            _VOYAGE_API_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": _VOYAGE_USER_AGENT,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, UnicodeDecodeError, JSONDecodeError):
            raise VoyageEmbeddingProviderError(
                "could not retrieve a valid Voyage AI response"
            ) from None

        return _parse_embeddings(payload, expected_count=len(texts))


def _parse_embeddings(payload: object, *, expected_count: int) -> list[list[float]]:
    """Extract embedding vectors from a Voyage response, restoring input order."""

    if not isinstance(payload, dict):
        raise VoyageEmbeddingProviderError("Voyage response must be a JSON object")

    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected_count:
        raise VoyageEmbeddingProviderError(
            "Voyage response data does not match the number of requested texts"
        )

    embeddings: list[list[float] | None] = [None] * expected_count
    for item in data:
        if not isinstance(item, dict):
            raise VoyageEmbeddingProviderError("Voyage response item must be an object")

        index = item.get("index")
        embedding = item.get("embedding")
        if (
            not isinstance(index, int)
            or not (0 <= index < expected_count)
            or embeddings[index] is not None
            or not isinstance(embedding, list)
            or not embedding
            or not all(isinstance(value, (int, float)) for value in embedding)
        ):
            raise VoyageEmbeddingProviderError("Voyage response item is malformed")

        embeddings[index] = [float(value) for value in embedding]

    return [embedding for embedding in embeddings if embedding is not None]
