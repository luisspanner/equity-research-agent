"""Tests for the synchronous Groq Bear Analyst adapter."""

import json
from datetime import date
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.bear_groq import (
    GroqBearAnalyst,
    GroqBearAnalystError,
)
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.provenance import SourceReference


class FakeResponse:
    """Minimal context-managed HTTP response for Groq adapter tests."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def make_source() -> SourceReference:
    """Create stable provenance for Bear Analyst fixtures."""

    return SourceReference(
        provider="test_provider",
        source_type="company_overview",
        source_id="TEST-overview",
        url=HttpUrl("https://example.com/company-overview"),
        captured_on=date(2026, 8, 18),
    )


def make_profile() -> CompanyProfile:
    """Create source-bearing company context for a Groq request."""

    return CompanyProfile(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency="USD",
        ),
        name="Test Company",
        description="Test Company sells enterprise software subscriptions.",
        sources=(make_source(),),
    )


def make_business_analysis() -> BusinessAnalysis:
    """Create sourced prior LLM interpretation for a Groq request."""

    return BusinessAnalysis(
        business_model="Subscription software provider.",
        primary_offerings=("Enterprise software",),
        customers_and_end_markets="Business customers.",
        revenue_model="Recurring subscriptions.",
        competitive_positioning="Not established by the supplied profile.",
        evidence=(
            BusinessAnalysisEvidence(
                claim="The company sells enterprise software subscriptions.",
                source_ids=("TEST-overview",),
            ),
        ),
        sources=(make_source(),),
    )


def make_completion(content: object) -> bytes:
    """Create a minimal successful Groq chat-completions payload."""

    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def valid_analysis_content() -> str:
    """Create an LLM JSON object that matches the BearAnalysis schema."""

    return json.dumps(
        {
            "risks": [
                {
                    "risk": "Customer concentration could increase volatility.",
                    "downside_mechanism": "Limited customer detail raises uncertainty.",
                    "source_ids": ["TEST-overview"],
                }
            ],
            "thesis_killers": ["Evidence of sustained customer losses."],
            "limitations": ["Customer concentration is not disclosed in the profile."],
        }
    )


def test_analyze_sends_json_mode_request_and_attaches_business_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        recorded_requests.append(request)
        return FakeResponse(make_completion(valid_analysis_content()))

    monkeypatch.setattr(
        "equity_research_agent.agents.bear_groq.urlopen", fake_urlopen
    )

    analysis = GroqBearAnalyst("test-key").analyze(
        make_profile(), make_business_analysis()
    )

    assert analysis.sources[0].source_id == "TEST-overview"
    assert analysis.risks[0].source_ids == ("TEST-overview",)
    request = recorded_requests[0]
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("User-agent") == "equity-research-agent/0.1"
    assert request.data is not None
    request_body = json.loads(request.data.decode("utf-8"))
    assert request_body["model"] == "openai/gpt-oss-120b"
    assert request_body["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("api_key", ["", "   "])
def test_constructor_rejects_blank_api_key(api_key: str) -> None:
    with pytest.raises(ValueError, match="api_key"):
        GroqBearAnalyst(api_key)


def test_from_environment_reads_groq_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "environment-key")

    analyst = GroqBearAnalyst.from_environment()

    assert analyst._api_key == "environment-key"


def test_from_environment_requires_groq_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        GroqBearAnalyst.from_environment()


@pytest.mark.parametrize(
    "network_error",
    [
        HTTPError("https://example.test", 429, "rate limit", Message(), None),
        URLError("connection unavailable"),
    ],
)
def test_network_errors_are_safely_wrapped(
    monkeypatch: pytest.MonkeyPatch, network_error: Exception
) -> None:
    def failing_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise network_error

    monkeypatch.setattr(
        "equity_research_agent.agents.bear_groq.urlopen", failing_urlopen
    )

    with pytest.raises(GroqBearAnalystError) as error:
        GroqBearAnalyst("test-key").analyze(
            make_profile(), make_business_analysis()
        )

    assert "test-key" not in str(error.value)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"not json", "could not retrieve"),
        (b"[]", "must be a JSON object"),
        (json.dumps({"choices": []}).encode(), "no completion choices"),
        (make_completion("not json"), "content must be valid JSON"),
    ],
)
def test_invalid_groq_responses_are_rejected(
    monkeypatch: pytest.MonkeyPatch, body: bytes, message: str
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(body)

    monkeypatch.setattr(
        "equity_research_agent.agents.bear_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqBearAnalystError, match=message):
        GroqBearAnalyst("test-key").analyze(
            make_profile(), make_business_analysis()
        )


def test_schema_invalid_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_content = json.dumps(
        {
            "risks": [
                {
                    "risk": "Untraceable risk.",
                    "downside_mechanism": "No sourced mechanism.",
                    "source_ids": ["unknown-source"],
                }
            ],
            "thesis_killers": ["Evidence of sustained customer losses."],
        }
    )

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(make_completion(invalid_content))

    monkeypatch.setattr(
        "equity_research_agent.agents.bear_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqBearAnalystError, match="BearAnalysis schema"):
        GroqBearAnalyst("test-key").analyze(
            make_profile(), make_business_analysis()
        )
