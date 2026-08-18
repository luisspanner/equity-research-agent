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
from equity_research_agent.analytics.metrics import assemble_financial_metrics
from equity_research_agent.data.providers import (
    AlphaVantageProvider,
    FinancialDataProvider,
)
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.synthesis import ResearchSynthesis
from equity_research_agent.reports import render_research_report


class BusinessAnalyst(Protocol):
    """Produce a structured business analysis for a company profile."""

    def analyze(self, profile: CompanyProfile) -> BusinessAnalysis:
        """Analyze the company's business model and qualitative position."""


class BearAnalyst(Protocol):
    """Produce a structured downside analysis from business context."""

    def analyze(
        self, profile: CompanyProfile, business_analysis: BusinessAnalysis
    ) -> BearAnalysis:
        """Analyze the company's plausible downside risks."""


class ResearchSynthesizer(Protocol):
    """Produce a structured synthesis from completed qualitative analyses."""

    def analyze(
        self,
        profile: CompanyProfile,
        business_analysis: BusinessAnalysis,
        bear_analysis: BearAnalysis,
    ) -> ResearchSynthesis:
        """Synthesize business and bear analyses into a research summary."""


def run_research(
    ticker: str,
    provider: FinancialDataProvider,
    business_analyst: BusinessAnalyst,
    bear_analyst: BearAnalyst,
    synthesizer: ResearchSynthesizer,
) -> str:
    """Run the V0 workflow and return its sourced Markdown research report."""

    profile = provider.get_company_profile(ticker)
    financials = provider.get_annual_financials(ticker)
    market_snapshot = provider.get_market_snapshot(ticker)
    metrics = assemble_financial_metrics(financials, market_snapshot)
    business_analysis = business_analyst.analyze(profile)
    bear_analysis = bear_analyst.analyze(profile, business_analysis)
    synthesis = synthesizer.analyze(profile, business_analysis, bear_analysis)
    return render_research_report(
        profile, metrics, business_analysis, bear_analysis, synthesis
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
        GroqResearchSynthesizer.from_environment(),
    )
    print(report)
