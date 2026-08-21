"""Tests for the Voyage AI embedding-provider adapter."""

import json
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from equity_research_agent.embeddings.voyage import (
    VoyageEmbeddingProvider,
    VoyageEmbeddingProviderError,
)


class FakeResponse:
    """Minimal context-managed HTTP response for Voyage adapter tests."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self, exception_type: object, exception: object, traceback: object
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _response(payload: object) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"))


def test_embed_returns_vectors_in_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return _response(
            {
                "data": [
                    {"embedding": [0.2, 0.3], "index": 1},
                    {"embedding": [0.0, 0.1], "index": 0},
                ]
            }
        )

    monkeypatch.setattr(
        "equity_research_agent.embeddings.voyage.urlopen", fake_urlopen
    )

    provider = VoyageEmbeddingProvider("test-key")
    result = provider.embed(["first", "second"], input_type="document")

    assert result == [[0.0, 0.1], [0.2, 0.3]]


def test_embed_sends_input_type_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        assert request.data is not None
        assert isinstance(request.data, bytes)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = dict(request.headers)
        return _response({"data": [{"embedding": [1.0], "index": 0}]})

    monkeypatch.setattr(
        "equity_research_agent.embeddings.voyage.urlopen", fake_urlopen
    )

    provider = VoyageEmbeddingProvider("test-key", model="voyage-3-lite")
    provider.embed(["a query"], input_type="query")

    body = captured["body"]
    assert isinstance(body, dict)
    assert body == {
        "input": ["a query"],
        "model": "voyage-3-lite",
        "input_type": "query",
    }
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-key"


def test_embed_rejects_empty_texts() -> None:
    provider = VoyageEmbeddingProvider("test-key")

    with pytest.raises(ValueError):
        provider.embed([], input_type="document")


@pytest.mark.parametrize("network_error", [URLError("boom"), UnicodeDecodeError(
    "utf-8", b"\xff", 0, 1, "invalid"
)])
def test_embed_raises_on_transport_failure(
    monkeypatch: pytest.MonkeyPatch, network_error: Exception
) -> None:
    def failing_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise network_error

    monkeypatch.setattr(
        "equity_research_agent.embeddings.voyage.urlopen", failing_urlopen
    )

    provider = VoyageEmbeddingProvider("test-key")
    with pytest.raises(VoyageEmbeddingProviderError):
        provider.embed(["text"], input_type="document")


def test_embed_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise HTTPError(
            "https://api.voyageai.com/v1/embeddings",
            401,
            "unauthorized",
            Message(),
            None,
        )

    monkeypatch.setattr(
        "equity_research_agent.embeddings.voyage.urlopen", failing_urlopen
    )

    provider = VoyageEmbeddingProvider("test-key")
    with pytest.raises(VoyageEmbeddingProviderError):
        provider.embed(["text"], input_type="document")


@pytest.mark.parametrize(
    "payload",
    [
        {"data": "not-a-list"},
        {"data": [{"embedding": [1.0], "index": 0}, {"embedding": [1.0], "index": 0}]},
        {"data": [{"embedding": [1.0], "index": 5}]},
        {"data": [{"index": 0}]},
        {"data": [{"embedding": [], "index": 0}]},
        {"data": [{"embedding": ["not-a-float"], "index": 0}]},
        "not-a-dict",
    ],
)
def test_embed_raises_on_malformed_response(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return _response(payload)

    monkeypatch.setattr(
        "equity_research_agent.embeddings.voyage.urlopen", fake_urlopen
    )

    provider = VoyageEmbeddingProvider("test-key")
    with pytest.raises(VoyageEmbeddingProviderError):
        provider.embed(["text"], input_type="document")


def test_settings_validation_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        VoyageEmbeddingProvider("")
    with pytest.raises(ValueError):
        VoyageEmbeddingProvider("key", model=" ")
    with pytest.raises(ValueError):
        VoyageEmbeddingProvider("key", timeout_seconds=0)


def test_from_environment_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "environment-key")

    provider = VoyageEmbeddingProvider.from_environment()

    assert provider._api_key == "environment-key"


def test_from_environment_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    with pytest.raises(ValueError):
        VoyageEmbeddingProvider.from_environment()
