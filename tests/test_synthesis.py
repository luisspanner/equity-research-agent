"""Tests for source-bounded research-synthesis preparation and output models."""

from datetime import date

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.synthesis import build_research_synthesis_prompt
from equity_research_agent.models.bear_analysis import BearAnalysis, BearRisk
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.provenance import SourceReference
from equity_research_agent.models.synthesis import ResearchSynthesis, SynthesisEvidence


def make_source(source_id: str = "TEST-overview") -> SourceReference:
    """Create stable provenance for research-synthesis fixtures."""

    return SourceReference(
        provider="test_provider",
        source_type="company_overview",
        source_id=source_id,
        url=HttpUrl("https://example.com/company-overview"),
        captured_on=date(2026, 8, 18),
    )


def make_profile() -> CompanyProfile:
    """Create normalized company context for synthesis tests."""

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


def make_business_analysis(
    sources: tuple[SourceReference, ...] | None = None,
) -> BusinessAnalysis:
    """Create sourced prior business analysis for synthesis tests."""

    analysis_sources = sources or (make_source(),)
    return BusinessAnalysis(
        business_model="Subscription software provider.",
        primary_offerings=("Enterprise software",),
        customers_and_end_markets="Business customers.",
        revenue_model="Recurring subscriptions.",
        competitive_positioning="Not established by the supplied profile.",
        evidence=(
            BusinessAnalysisEvidence(
                claim="The company sells enterprise software subscriptions.",
                source_ids=(analysis_sources[0].source_id,),
            ),
        ),
        sources=analysis_sources,
    )


def make_bear_analysis(
    sources: tuple[SourceReference, ...] | None = None,
) -> BearAnalysis:
    """Create sourced prior bear analysis for synthesis tests."""

    analysis_sources = sources or (make_source(),)
    return BearAnalysis(
        risks=(
            BearRisk(
                risk="Customer concentration could increase volatility.",
                downside_mechanism="Limited customer detail raises uncertainty.",
                source_ids=(analysis_sources[0].source_id,),
            ),
        ),
        thesis_killers=("Evidence of sustained customer losses.",),
        sources=analysis_sources,
    )


def test_prompt_preserves_the_evidence_boundary_and_deduplicates_sources() -> None:
    prompt = build_research_synthesis_prompt(
        make_profile(), make_business_analysis(), make_bear_analysis()
    )

    assert "Test Company" in prompt
    assert "Subscription software provider." in prompt
    assert "Customer concentration could increase volatility." in prompt
    assert "not as new evidence" in prompt
    assert "not an investment\nrecommendation" in prompt
    assert prompt.count('"source_id": "TEST-overview"') == 1


def test_prompt_rejects_conflicting_source_references() -> None:
    conflicting_source = SourceReference(
        provider="other_provider",
        source_type="company_overview",
        source_id="TEST-overview",
        url=HttpUrl("https://example.com/other-overview"),
        captured_on=date(2026, 8, 18),
    )

    with pytest.raises(ValueError, match="conflicting source references"):
        build_research_synthesis_prompt(
            make_profile(),
            make_business_analysis(),
            make_bear_analysis((conflicting_source,)),
        )


def test_research_synthesis_accepts_evidence_with_a_supplied_source() -> None:
    synthesis = ResearchSynthesis(
        investment_thesis="A balanced research summary is warranted.",
        supporting_points=("The company sells enterprise software subscriptions.",),
        risk_summary=("Customer concentration could increase volatility.",),
        open_research_questions=("Which customers drive the largest revenue share?",),
        evidence=(
            SynthesisEvidence(
                claim="The company sells enterprise software subscriptions.",
                source_ids=("TEST-overview",),
            ),
        ),
        sources=(make_source(),),
    )

    assert synthesis.evidence[0].source_ids == ("TEST-overview",)


def test_research_synthesis_rejects_evidence_with_unknown_sources() -> None:
    with pytest.raises(ValueError, match="unknown source IDs: missing-source"):
        ResearchSynthesis(
            investment_thesis="A balanced research summary is warranted.",
            supporting_points=("The company sells enterprise software subscriptions.",),
            risk_summary=("Customer concentration could increase volatility.",),
            open_research_questions=(
                "Which customers drive the largest revenue share?",
            ),
            evidence=(
                SynthesisEvidence(
                    claim="The company sells enterprise software subscriptions.",
                    source_ids=("missing-source",),
                ),
            ),
            sources=(make_source(),),
        )
