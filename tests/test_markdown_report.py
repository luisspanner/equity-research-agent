"""Tests for deterministic Markdown rendering of completed research outputs."""

from datetime import date
from decimal import Decimal

from pydantic import HttpUrl

from equity_research_agent.filings.disclosed_risk_pipeline import (
    DisclosedRiskPipelineResult,
    DisclosedRiskUnavailableReason,
)
from equity_research_agent.filings.risk_factors import (
    RiskFactorsSectionUnavailableReason,
)
from equity_research_agent.models.bear_analysis import BearAnalysis, BearRisk
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.disclosed_risk_analysis import (
    DisclosedRisk,
    DisclosedRiskAnalysis,
)
from equity_research_agent.models.financial_quality import (
    FinancialQualityAnalysis,
    FinancialQualityEvidence,
)
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


def make_financial_quality_analysis() -> FinancialQualityAnalysis:
    """Create sourced financial-quality analysis for report rendering."""

    overall_assessment = FinancialQualityEvidence(
        claim="Profitability appears healthy based on the supplied metrics.",
        metric_names=("operating_margin",),
        source_ids=("TEST-overview",),
    )
    return FinancialQualityAnalysis(
        overall_assessment=overall_assessment,
        strengths=(
            FinancialQualityEvidence(
                claim="Free cash flow margin is a financial strength.",
                metric_names=("fcf_margin",),
                source_ids=("TEST-overview",),
            ),
        ),
        concerns=(
            FinancialQualityEvidence(
                claim="Net debt warrants continued monitoring.",
                metric_names=("net_debt",),
                source_ids=("TEST-overview",),
            ),
        ),
        limitations=("The supplied metrics do not include peer comparisons.",),
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


def make_disclosed_risk_source() -> SourceReference:
    """Create provenance for a filing section, distinct from the profile source."""

    return SourceReference(
        provider="sec_edgar",
        source_type="filing_section",
        source_id="0000000000-26-000000:risks",
        url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/1/000000000026000000/"
            "test-20251231.htm#risks"
        ),
        captured_on=date(2026, 2, 25),
    )


def make_disclosed_risk_result() -> DisclosedRiskPipelineResult:
    """Create an available filing-derived disclosed-risk result."""

    source = make_disclosed_risk_source()
    return DisclosedRiskPipelineResult(
        analysis=DisclosedRiskAnalysis(
            disclosed_risks=(
                DisclosedRisk(
                    risk="Regulatory changes could restrict product exports.",
                    source_ids=(source.source_id,),
                ),
            ),
            limitations=("The section covers only export-control risk factors.",),
            sources=(source,),
        )
    )


def render_fixture_report(
    disclosed_risk_result: DisclosedRiskPipelineResult | None = None,
) -> str:
    """Render one complete report from stable, representative input fixtures."""

    return render_research_report(
        make_profile(),
        make_metrics(),
        make_business_analysis(),
        make_bear_analysis(),
        make_financial_quality_analysis(),
        make_synthesis(),
        disclosed_risk_result
        if disclosed_risk_result is not None
        else make_disclosed_risk_result(),
    )


def test_render_report_contains_identity_sections_and_analyst_content() -> None:
    report = render_fixture_report()

    assert "# Test Company (TEST)" in report
    assert "## Deterministic Financial Metrics" in report
    assert "## Financial Quality (LLM Interpretation)" in report
    assert "## Business Analysis (LLM Interpretation)" in report
    assert "## Bear Case (LLM Interpretation)" in report
    assert "## Research Synthesis (LLM Interpretation)" in report
    assert "Subscription software provider." in report
    assert "Customer concentration could increase volatility." in report
    assert "Profitability appears healthy based on the supplied metrics." in report
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


def test_render_report_financial_quality_omits_validation_metric_names() -> None:
    report = render_fixture_report()

    assert "Free cash flow margin is a financial strength. [TEST-overview]" in report
    assert "Net debt warrants continued monitoring. [TEST-overview]" in report
    assert "fcf_margin" not in report
    assert "## Financial Quality (LLM Interpretation)" in report
    assert report.index("## Financial Quality (LLM Interpretation)") < report.index(
        "## Business Analysis (LLM Interpretation)"
    )


def test_render_report_omits_empty_financial_quality_finding_headings() -> None:
    analysis = make_financial_quality_analysis().model_copy(
        update={"strengths": (), "concerns": ()}
    )
    report = render_research_report(
        make_profile(),
        make_metrics(),
        make_business_analysis(),
        make_bear_analysis(),
        analysis,
        make_synthesis(),
        make_disclosed_risk_result(),
    )

    assert "### Overall Assessment" in report
    assert "### Strengths" not in report
    assert "### Concerns" not in report


def test_render_report_is_deterministic_for_identical_inputs() -> None:
    assert render_fixture_report() == render_fixture_report()


def test_render_report_includes_disclosed_risks_when_available() -> None:
    report = render_fixture_report()

    assert "## Disclosed Risks (Filing Interpretation)" in report
    assert (
        "Regulatory changes could restrict product exports. "
        "[0000000000-26-000000:risks]" in report
    )
    assert "The section covers only export-control risk factors." in report
    assert "[0000000000-26-000000:risks]" in report


def test_render_report_sources_section_reflects_synthesis_sources_only() -> None:
    """The Research Synthesizer merges disclosed-risk sources; rendering does not.

    ``make_synthesis()`` does not include the disclosed-risk fixture's source,
    so it must not appear in the consolidated Sources section even though the
    Disclosed Risks section above it is available and cites it.
    """

    report = render_fixture_report()

    sources_section = report.split("## Sources")[1]
    assert "TEST-overview" in sources_section
    assert "0000000000-26-000000:risks" not in sources_section


def test_render_report_states_disclosed_risk_unavailable_reason() -> None:
    unavailable = DisclosedRiskPipelineResult(
        unavailable_reason=DisclosedRiskUnavailableReason.CIK_UNRESOLVED
    )
    report = render_fixture_report(unavailable)

    assert "## Disclosed Risks (Filing Interpretation)" in report
    assert "Not available — cik unresolved" in report
    assert "0000000000-26-000000:risks" not in report


def test_render_report_states_specific_risk_factors_unavailable_reason() -> None:
    unavailable = DisclosedRiskPipelineResult(
        unavailable_reason=(
            DisclosedRiskUnavailableReason.RISK_FACTORS_SECTION_UNAVAILABLE
        ),
        risk_factors_reason=(
            RiskFactorsSectionUnavailableReason.EXPECTED_ITEM_NOT_FOUND
        ),
    )
    report = render_fixture_report(unavailable)

    assert (
        "Not available — risk factors section unavailable "
        "(expected item not found)" in report
    )
