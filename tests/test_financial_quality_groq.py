"""Tests for the synchronous Groq Financial Quality Analyst adapter."""

import json
from datetime import date
from decimal import Decimal
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.financial_quality_groq import (
    GroqFinancialQualityAnalyst,
    GroqFinancialQualityAnalystError,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
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
    """Create stable financial provenance for Groq adapter fixtures."""

    return SourceReference(
        provider="test_provider",
        source_type="income_statement",
        source_id="TEST-income-2025",
        url=HttpUrl("https://example.com/income-statement"),
        captured_on=date(2026, 8, 19),
    )


def make_profile() -> CompanyProfile:
    """Create source-bearing company context for a Groq request."""

    profile_source = SourceReference(
        provider="test_provider",
        source_type="company_overview",
        source_id="TEST-overview",
        url=HttpUrl("https://example.com/company-overview"),
        captured_on=date(2026, 8, 19),
    )
    return CompanyProfile(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency="USD",
        ),
        name="Test Company",
        description="Test Company sells enterprise software subscriptions.",
        sources=(profile_source,),
    )


def make_financial_risk_context() -> FinancialRiskContext:
    """Create source-aware financial context for a Groq request."""

    source = make_source()
    revenue_source = SourceReference(
        provider="test_provider",
        source_type="income_statement",
        source_id="TEST-revenue-2025",
        url=HttpUrl("https://example.com/revenue-statement"),
        captured_on=date(2026, 8, 19),
    )
    return FinancialRiskContext(
        metrics=(
            FinancialRiskMetric(
                metric="operating_margin",
                value=Decimal("0.25"),
                unit="percentage",
                source_ids=(source.source_id,),
            ),
            FinancialRiskMetric(
                metric="revenue_growth",
                value=Decimal("0.10"),
                unit="percentage",
                source_ids=(revenue_source.source_id,),
            ),
        ),
        sources=(source, revenue_source),
    )


def make_completion(content: object) -> bytes:
    """Create a minimal successful Groq chat-completions payload."""

    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def valid_analysis_content(source_id: str = "TEST-income-2025") -> str:
    """Create an LLM JSON object that matches FinancialQualityAnalysis."""

    return json.dumps(
        {
            "overall_assessment": {
                "claim": "The supplied metric indicates profitability.",
                "metric_names": ["operating_margin"],
                "source_ids": [source_id],
            },
            "strengths": [
                {
                    "claim": "The supplied operating margin is positive.",
                    "metric_names": ["operating_margin"],
                    "source_ids": [source_id],
                }
            ],
            "concerns": [
                {
                    "claim": "The supplied context has limited coverage.",
                    "metric_names": ["operating_margin"],
                    "source_ids": [source_id],
                }
            ],
            "limitations": ["Cash-flow metrics are unavailable in this context."],
        }
    )


def test_analyze_sends_json_mode_and_attaches_only_context_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        recorded_requests.append(request)
        return FakeResponse(make_completion(valid_analysis_content()))

    monkeypatch.setattr(
        "equity_research_agent.agents.financial_quality_groq.urlopen", fake_urlopen
    )

    analysis = GroqFinancialQualityAnalyst("test-key").analyze(
        make_profile(), make_financial_risk_context()
    )

    assert [source.source_id for source in analysis.sources] == [
        "TEST-income-2025",
        "TEST-revenue-2025",
    ]
    assert analysis.overall_assessment.source_ids == ("TEST-income-2025",)
    request = recorded_requests[0]
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("User-agent") == "equity-research-agent/0.1"
    assert request.data is not None
    request_body = json.loads(request.data.decode("utf-8"))
    assert request_body["model"] == "openai/gpt-oss-120b"
    assert request_body["response_format"] == {"type": "json_object"}


def test_analyze_rejects_unknown_response_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(make_completion(valid_analysis_content("unknown-source")))

    monkeypatch.setattr(
        "equity_research_agent.agents.financial_quality_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqFinancialQualityAnalystError, match="schema"):
        GroqFinancialQualityAnalyst("test-key").analyze(
            make_profile(), make_financial_risk_context()
        )


def test_analyze_rejects_known_source_not_used_by_referenced_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(
            make_completion(valid_analysis_content("TEST-revenue-2025"))
        )

    monkeypatch.setattr(
        "equity_research_agent.agents.financial_quality_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqFinancialQualityAnalystError, match="do not match"):
        GroqFinancialQualityAnalyst("test-key").analyze(
            make_profile(), make_financial_risk_context()
        )


def test_analyze_rejects_unknown_metric_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads(valid_analysis_content())
    payload["overall_assessment"]["metric_names"] = ["unknown_metric"]

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(make_completion(json.dumps(payload)))

    monkeypatch.setattr(
        "equity_research_agent.agents.financial_quality_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqFinancialQualityAnalystError, match="unknown metric names"):
        GroqFinancialQualityAnalyst("test-key").analyze(
            make_profile(), make_financial_risk_context()
        )


def test_analyze_rejects_duplicate_context_metric_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_financial_risk_context()
    duplicate_metric = context.metrics[0].model_copy(
        update={"source_ids": ("TEST-revenue-2025",)}
    )
    duplicate_context = context.model_copy(
        update={"metrics": (*context.metrics, duplicate_metric)}
    )

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(make_completion(valid_analysis_content()))

    monkeypatch.setattr(
        "equity_research_agent.agents.financial_quality_groq.urlopen", fake_urlopen
    )

    with pytest.raises(
        GroqFinancialQualityAnalystError, match="duplicate metric names"
    ):
        GroqFinancialQualityAnalyst("test-key").analyze(
            make_profile(), duplicate_context
        )


def test_from_environment_reads_groq_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "environment-key")

    analyst = GroqFinancialQualityAnalyst.from_environment()

    assert analyst._api_key == "environment-key"


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
        "equity_research_agent.agents.financial_quality_groq.urlopen", failing_urlopen
    )

    with pytest.raises(GroqFinancialQualityAnalystError) as error:
        GroqFinancialQualityAnalyst("test-key").analyze(
            make_profile(), make_financial_risk_context()
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
        "equity_research_agent.agents.financial_quality_groq.urlopen", fake_urlopen
    )

    with pytest.raises(GroqFinancialQualityAnalystError, match=message):
        GroqFinancialQualityAnalyst("test-key").analyze(
            make_profile(), make_financial_risk_context()
        )
