"""Tests for source-bounded Bear Analyst preparation and output models."""

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.bear import build_bear_analysis_prompt
from equity_research_agent.models.bear_analysis import BearAnalysis, BearRisk
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
from equity_research_agent.models.provenance import SourceReference


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
    """Create normalized company context for Bear Analyst tests."""

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
    """Create sourced prior LLM interpretation for Bear Analyst tests."""

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
        limitations=("The profile does not identify competitors.",),
        sources=(make_source(),),
    )


def make_financial_risk_context() -> FinancialRiskContext:
    """Create sourced deterministic financial context for Bear Analyst tests."""

    financial_source = SourceReference(
        provider="test_provider",
        source_type="income_statement",
        source_id="TEST-income-2025",
        url=HttpUrl("https://example.com/income-statement"),
        captured_on=date(2026, 8, 18),
    )
    return FinancialRiskContext(
        metrics=(
            FinancialRiskMetric(
                metric="operating_margin",
                value=Decimal("0.25"),
                unit="percentage",
                source_ids=(financial_source.source_id,),
            ),
        ),
        sources=(financial_source,),
    )


def test_prompt_preserves_the_evidence_boundary_for_prior_analysis() -> None:
    prompt = build_bear_analysis_prompt(
        make_profile(), make_business_analysis(), make_financial_risk_context()
    )

    assert "Test Company" in prompt
    assert "Subscription software provider." in prompt
    assert "TEST-overview" in prompt
    assert "not as new evidence" in prompt
    assert "Do not invent facts" in prompt
    assert "financial\ncalculations" in prompt
    assert "cite the source IDs listed for that metric" in prompt


def test_prompt_includes_financial_metrics_and_merged_source_ids() -> None:
    prompt = build_bear_analysis_prompt(
        make_profile(), make_business_analysis(), make_financial_risk_context()
    )
    context = json.loads(prompt.split("Research context:\n", maxsplit=1)[1])

    assert context["financial_risk_context"] == {
        "metrics": [
            {
                "metric": "operating_margin",
                "source_ids": ["TEST-income-2025"],
                "unit": "percentage",
                "value": "0.25",
            }
        ]
    }
    assert [source["source_id"] for source in context["sources"]] == [
        "TEST-overview",
        "TEST-income-2025",
    ]


def test_bear_analysis_accepts_risks_that_reference_supplied_sources() -> None:
    analysis = BearAnalysis(
        risks=(
            BearRisk(
                risk="Customer concentration could increase revenue volatility.",
                downside_mechanism="The profile provides insufficient customer detail.",
                source_ids=("TEST-overview",),
            ),
        ),
        thesis_killers=("Evidence of sustained customer losses.",),
        limitations=("Customer concentration is not disclosed in the profile.",),
        sources=(make_source(),),
    )

    assert analysis.risks[0].source_ids == ("TEST-overview",)


def test_bear_analysis_rejects_risks_with_unknown_sources() -> None:
    with pytest.raises(ValueError, match="unknown source IDs: missing-source"):
        BearAnalysis(
            risks=(
                BearRisk(
                    risk="Customer concentration could increase revenue volatility.",
                    downside_mechanism=(
                        "The profile provides insufficient customer detail."
                    ),
                    source_ids=("missing-source",),
                ),
            ),
            thesis_killers=("Evidence of sustained customer losses.",),
            sources=(make_source(),),
        )
