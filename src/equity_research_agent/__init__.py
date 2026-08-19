"""Command-line entry point for the V0 equity research workflow."""

import argparse
import os
from collections.abc import Sequence
from typing import Protocol

from equity_research_agent.agents import (
    GroqBearAnalyst,
    GroqBusinessAnalyst,
    GroqResearchSynthesizer,
)
from equity_research_agent.agents.financial_quality import (
    validate_financial_quality_provenance,
)
from equity_research_agent.agents.financial_quality_groq import (
    GroqFinancialQualityAnalyst,
)
from equity_research_agent.analytics.financial_risk import build_financial_risk_context
from equity_research_agent.analytics.metrics import assemble_financial_metrics
from equity_research_agent.data.providers import (
    AlphaVantageProvider,
    FinancialDataProvider,
)
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_quality import FinancialQualityAnalysis
from equity_research_agent.models.financial_risk import FinancialRiskContext
from equity_research_agent.models.synthesis import ResearchSynthesis
from equity_research_agent.reports import render_research_report


class BusinessAnalyst(Protocol):
    """Produce a structured business analysis for a company profile."""

    def analyze(self, profile: CompanyProfile) -> BusinessAnalysis:
        """Analyze the company's business model and qualitative position."""


class BearAnalyst(Protocol):
    """Produce a structured downside analysis from business context."""

    def analyze(
        self,
        profile: CompanyProfile,
        business_analysis: BusinessAnalysis,
        financial_risk_context: FinancialRiskContext,
    ) -> BearAnalysis:
        """Analyze the company's plausible downside risks."""


class FinancialQualityAnalyst(Protocol):
    """Produce a structured financial-quality interpretation from risk metrics."""

    def analyze(
        self,
        profile: CompanyProfile,
        financial_risk_context: FinancialRiskContext,
    ) -> FinancialQualityAnalysis:
        """Interpret deterministic financial metrics with their source evidence."""


class ResearchSynthesizer(Protocol):
    """Produce a structured synthesis from completed qualitative analyses."""

    def analyze(
        self,
        profile: CompanyProfile,
        business_analysis: BusinessAnalysis,
        bear_analysis: BearAnalysis,
        financial_quality_analysis: FinancialQualityAnalysis,
    ) -> ResearchSynthesis:
        """Synthesize business and bear analyses into a research summary."""


def run_research(
    ticker: str,
    provider: FinancialDataProvider,
    business_analyst: BusinessAnalyst,
    bear_analyst: BearAnalyst,
    financial_quality_analyst: FinancialQualityAnalyst,
    synthesizer: ResearchSynthesizer,
) -> str:
    """Run the V0 workflow and return its sourced Markdown research report."""

    profile = provider.get_company_profile(ticker)
    financials = provider.get_annual_financials(ticker)
    market_snapshot = provider.get_market_snapshot(ticker)
    metrics = assemble_financial_metrics(financials, market_snapshot)
    financial_risk_context = build_financial_risk_context(
        metrics, financials, market_snapshot
    )
    business_analysis = business_analyst.analyze(profile)
    bear_analysis = bear_analyst.analyze(
        profile, business_analysis, financial_risk_context
    )
    financial_quality_analysis = financial_quality_analyst.analyze(
        profile, financial_risk_context
    )
    validate_financial_quality_provenance(
        financial_quality_analysis, financial_risk_context
    )
    synthesis = synthesizer.analyze(
        profile, business_analysis, bear_analysis, financial_quality_analysis
    )
    return render_research_report(
        profile,
        metrics,
        business_analysis,
        bear_analysis,
        financial_quality_analysis,
        synthesis,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Parse CLI configuration, run V0 research, and print its Markdown report."""

    parser = argparse.ArgumentParser(
        description="Generate a sourced V0 equity research report for one ticker."
    )
    parser.add_argument("ticker", help="Listed company ticker, for example ASML")
    arguments = parser.parse_args(argv)

    alpha_vantage_api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if alpha_vantage_api_key is None:
        parser.error("ALPHA_VANTAGE_API_KEY environment variable is not set")

    report = run_research(
        arguments.ticker,
        AlphaVantageProvider(alpha_vantage_api_key),
        GroqBusinessAnalyst.from_environment(),
        GroqBearAnalyst.from_environment(),
        GroqFinancialQualityAnalyst.from_environment(),
        GroqResearchSynthesizer.from_environment(),
    )
    print(report)
