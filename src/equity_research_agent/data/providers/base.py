"""Contracts for providers of normalized financial research data."""

from typing import Protocol, runtime_checkable

from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financials import AnnualFinancials, MarketSnapshot


@runtime_checkable
class FinancialDataProvider(Protocol):
    """Provide normalized, sourced financial research data for one ticker.

    Runtime ``isinstance`` checks confirm required member names only; static type
    checking enforces method signatures and return annotations.
    """

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        """Return a normalized company profile with source provenance."""

    def get_annual_financials(self, ticker: str) -> tuple[AnnualFinancials, ...]:
        """Return normalized, sourced annual financial statements."""

    def get_market_snapshot(self, ticker: str) -> MarketSnapshot:
        """Return a normalized, sourced market snapshot."""
