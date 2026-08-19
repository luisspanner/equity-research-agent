"""Contracts for providers of normalized financial research data."""

from typing import Protocol, runtime_checkable

from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.filings import FilingReference
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


@runtime_checkable
class FilingProvider(Protocol):
    """Discover primary-source annual-report filings for one issuer.

    This is deliberately separate from ``FinancialDataProvider``: filings are
    documents identified by an issuer CIK, not normalized statement data keyed
    by a listed ticker.
    """

    def get_latest_annual_report(self, cik: str) -> FilingReference:
        """Return sourced metadata for the issuer's most recent annual report."""
