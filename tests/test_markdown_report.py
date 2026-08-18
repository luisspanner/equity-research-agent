"""Tests for deterministic Markdown rendering of completed research outputs."""

from datetime import date
from decimal import Decimal

from pydantic import HttpUrl

from equity_research_agent.models.bear_analysis import BearAnalysis, BearRisk
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.metrics import FinancialMetrics, MetricUnavailability
from equity_research_agent.models.provenance import SourceReference
from equity_research_agent.models.synthesis import ResearchSynthesis, SynthesisEvidence
from equity_research_agent.reports.markdown import render_research_report


def make_source() -> SourceReference:
    """Create stable provenance for rendered-report fixtures."""

    return SourceReference(
        provider="test_provider",
        source_type="company_overview",
        source_id="TEST-overview",
        url=HttpUrl("https://example.com/company-overview"),
        captured_on=date(2026, 8, 18),
    )


def make_profile() -> CompanyProfile:
    """Create company context for report rendering."""

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


def make_metrics() -> FinancialMetrics:
    """Create deterministic metrics with available and unavailable values."""

    return FinancialMetrics(
        latest_period_end=date(2025, 12, 31),
        reporting_currency="EUR",
        revenue_cagr=Decimal("0.21"),
        eps_cagr=None,
        share_count_cagr=Decimal("0.10"),
        fcf=Decimal("2000000"),
        fcf_margin=Decimal("0.20"),
        gross_margin=Decimal("0.60"),
        operating_margin=Decimal("0.25"),
        ebitda=Decimal("3000000"),
        net_debt=Decimal("250000"),
        net_debt_to_ebitda=Decimal("0.0833"),
        roe=Decimal("0.20"),
        roic=Decimal("0.15"),
        pe_ratio=None,
        fcf_yield=Decimal("0.02"),
        ev_to_ebitda=Decimal("10.25"),
        market_metric_unavailabilities=(
            MetricUnavailability(
                metric="pe_ratio", reason="net income must be positive"
            ),
        ),
    )


def make_business_analysis() -> BusinessAnalysis:
    """Create sourced business analysis for report rendering."""

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


def make_bear_analysis() -> BearAnalysis:
    """Create sourced bear analysis for report rendering."""

    return BearAnalysis(
        risks=(
            BearRisk(
                risk="Customer concentration could increase volatility.",
                downside_mechanism="Limited customer detail raises uncertainty.",
                source_ids=("TEST-overview",),
            ),
        ),
        thesis_killers=("Evidence of sustained customer losses.",),
        limitations=("Customer concentration is not disclosed in the profile.",),
        sources=(make_source(),),
    )


def make_synthesis() -> ResearchSynthesis:
    """Create sourced final synthesis for report rendering."""

    return ResearchSynthesis(
        investment_thesis="A balanced research summary is warranted.",
        supporting_points=("The company sells enterprise software subscriptions.",),
        risk_summary=("Customer concentration could increase volatility.",),
        open_research_questions=("Which customers drive revenue?",),
        evidence=(
            SynthesisEvidence(
                claim="The company sells enterprise software subscriptions.",
                source_ids=("TEST-overview",),
            ),
        ),
        limitations=("The profile does not identify competitors.",),
        sources=(make_source(),),
    )


def render_fixture_report() -> str:
    """Render one complete report from stable, representative input fixtures."""

    return render_research_report(
        make_profile(),
        make_metrics(),
        make_business_analysis(),
        make_bear_analysis(),
        make_synthesis(),
    )


def test_render_report_contains_identity_sections_and_analyst_content() -> None:
    report = render_fixture_report()

    assert "# Test Company (TEST)" in report
    assert "## Deterministic Financial Metrics" in report
    assert "## Business Analysis (LLM Interpretation)" in report
    assert "## Bear Case (LLM Interpretation)" in report
    assert "## Research Synthesis (LLM Interpretation)" in report
    assert "Subscription software provider." in report
    assert "Customer concentration could increase volatility." in report
    assert "A balanced research summary is warranted." in report
    assert "not an investment recommendation" in report


def test_render_report_formats_metrics_and_keeps_missing_data_explicit() -> None:
    report = render_fixture_report()

    assert "- Revenue CAGR: 21.00%" in report
    assert "- Free cash flow: EUR 2,000,000" in report
    assert "- Net debt / EBITDA: 0.08x" in report
    assert "- EPS CAGR: Not available" in report
    assert "- P/E: Not available — net income must be positive" in report
    assert "- FCF yield: 2.00%" in report


def test_render_report_includes_citations_and_consolidated_sources() -> None:
    report = render_fixture_report()

    assert "[TEST-overview]" in report
    assert "https://example.com/company-overview" in report
    assert "captured 2026-08-18" in report


def test_render_report_is_deterministic_for_identical_inputs() -> None:
    assert render_fixture_report() == render_fixture_report()
