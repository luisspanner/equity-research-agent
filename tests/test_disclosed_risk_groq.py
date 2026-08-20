"""Tests for the synchronous Groq Disclosed Risk Analyst adapter."""

import json
from datetime import date, datetime, timezone
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.disclosed_risk import filing_section_source
from equity_research_agent.agents.disclosed_risk_groq import (
    GroqDisclosedRiskAnalyst,
    GroqDisclosedRiskAnalystError,
)
from equity_research_agent.models.filings import FilingReference, FilingSection
from equity_research_agent.models.provenance import SourceReference

DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/1045810/"
    "000104581026000021/nvda-20260125.htm"
)


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


def make_filing(**overrides: Any) -> FilingReference:
    """Create the filing reference a Groq request's section belongs to."""

    fields: dict[str, Any] = {
        "cik": "1045810",
        "form_type": "10-K",
        "accession_number": "0001045810-26-000021",
        "period_end": date(2026, 1, 25),
        "filed_on": date(2026, 2, 25),
        "document_url": HttpUrl(DOCUMENT_URL),
        "sources": (
            SourceReference(
                provider="sec_edgar",
                source_type="submissions_index",
                source_id="CIK0001045810-submissions",
                url=HttpUrl("https://data.sec.gov/submissions/CIK0001045810.json"),
                retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            ),
        ),
    }
    return FilingReference(**{**fields, **overrides})


def make_section(**overrides: Any) -> FilingSection:
    """Create a filing section for a Groq request."""

    fields: dict[str, Any] = {
        "label": "Item 1A. Risk Factors",
        "anchor_id": "i82ea215a7c1f4862b6518f1348ddc832_16",
        "text": "Competition could adversely impact our market share and results.",
    }
    return FilingSection(**{**fields, **overrides})


def make_completion(content: object) -> bytes:
    """Create a minimal successful Groq chat-completions payload."""

    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def valid_analysis_content(source_id: str) -> str:
    """Create an LLM JSON object that matches the DisclosedRiskAnalysis schema."""

    return json.dumps(
        {
            "disclosed_risks": [
                {
                    "risk": "Competition could adversely impact market share.",
                    "source_ids": [source_id],
                }
            ],
            "limitations": ["The section text may omit context from elsewhere."],
        }
    )


def test_analyze_sends_json_mode_request_and_attaches_the_section_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filing = make_filing()
    section = make_section()
    source_id = filing_section_source(filing, section).source_id
    recorded_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        recorded_requests.append(request)
        return FakeResponse(make_completion(valid_analysis_content(source_id)))

    monkeypatch.setattr(
        "equity_research_agent.agents.disclosed_risk_groq.urlopen", fake_urlopen
    )

    analysis = GroqDisclosedRiskAnalyst("test-key").analyze(filing, section)

    assert analysis.sources[0].source_id == source_id
    assert analysis.disclosed_risks[0].source_ids == (source_id,)
    request = recorded_requests[0]
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.data is not None
    request_body = json.loads(request.data.decode("utf-8"))
    assert request_body["model"] == "openai/gpt-oss-120b"
    assert request_body["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("api_key", ["", "   "])
def test_constructor_rejects_blank_api_key(api_key: str) -> None:
    with pytest.raises(ValueError, match="api_key"):
        GroqDisclosedRiskAnalyst(api_key)


def test_from_environment_reads_groq_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "environment-key")

    analyst = GroqDisclosedRiskAnalyst.from_environment()

    assert analyst._api_key == "environment-key"


def test_from_environment_requires_groq_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        GroqDisclosedRiskAnalyst.from_environment()


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
        "equity_research_agent.agents.disclosed_risk_groq.urlopen", failing_urlopen
    )

    with pytest.raises(GroqDisclosedRiskAnalystError) as error:
        GroqDisclosedRiskAnalyst("test-key").analyze(make_filing(), make_section())

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
        "equity_research_agent.agents.disclosed_risk_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqDisclosedRiskAnalystError, match=message):
        GroqDisclosedRiskAnalyst("test-key").analyze(make_filing(), make_section())


def test_schema_invalid_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_content = json.dumps(
        {
            "disclosed_risks": [
                {
                    "risk": "Untraceable risk.",
                    "source_ids": ["unknown-source"],
                }
            ],
            "limitations": [],
        }
    )

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(make_completion(invalid_content))

    monkeypatch.setattr(
        "equity_research_agent.agents.disclosed_risk_groq.urlopen", fake_urlopen
    )

    with pytest.raises(
        GroqDisclosedRiskAnalystError, match="DisclosedRiskAnalysis schema"
    ):
        GroqDisclosedRiskAnalyst("test-key").analyze(make_filing(), make_section())
