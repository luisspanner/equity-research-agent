"""Tests for source-bounded Business Analyst preparation and output models."""

from datetime import date

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.business import build_business_analysis_prompt
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.provenance import SourceReference


def make_source() -> SourceReference:
    """Create stable provenance for a company-profile fixture."""

    return SourceReference(
        provider="test_provider",
        source_type="company_overview",
        source_id="TEST-overview",
        url=HttpUrl("https://example.com/company-overview"),
        captured_on=date(2026, 8, 17),
    )


def make_profile() -> CompanyProfile:
    """Create a normalized company profile for Business Analyst tests."""

    return CompanyProfile(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency="USD",
        ),
        name="Test Company",
        description="Test Company sells enterprise software subscriptions.",
        country="United States",
        sector="Technology",
        industry="Software",
        sources=(make_source(),),
    )


def test_prompt_contains_only_normalized_company_context_and_instructions() -> None:
    prompt = build_business_analysis_prompt(make_profile())

    assert "Test Company" in prompt
    assert "enterprise software subscriptions" in prompt
    assert "TEST-overview" in prompt
    assert "Do not invent facts" in prompt
    assert "financial calculations" in prompt


def test_business_analysis_accepts_evidence_that_references_a_supplied_source() -> None:
    analysis = BusinessAnalysis(
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

    assert analysis.evidence[0].source_ids == ("TEST-overview",)


def test_business_analysis_rejects_evidence_with_an_unknown_source() -> None:
    with pytest.raises(ValueError, match="unknown source IDs: missing-source"):
        BusinessAnalysis(
            business_model="Subscription software provider.",
            primary_offerings=("Enterprise software",),
            customers_and_end_markets="Business customers.",
            revenue_model="Recurring subscriptions.",
            competitive_positioning="Not established by the supplied profile.",
            evidence=(
                BusinessAnalysisEvidence(
                    claim="The company sells enterprise software subscriptions.",
                    source_ids=("missing-source",),
                ),
            ),
            sources=(make_source(),),
        )
