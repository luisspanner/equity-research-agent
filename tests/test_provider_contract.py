"""Tests for the normalized financial-data provider contract."""

from datetime import date
from decimal import Decimal

from pydantic import HttpUrl

from equity_research_agent.data.providers import FinancialDataProvider
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.financials import (
    AnnualFinancials,
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriod,
    IncomeStatement,
    MarketSnapshot,
)
from equity_research_agent.models.provenance import SourceReference


def make_source() -> SourceReference:
    """Create provenance for normalized Alpha Vantage contract data."""

    return SourceReference(
        provider="alpha_vantage",
        source_type="annual_statement",
        source_id="ASML-2025",
        url=HttpUrl("https://www.alphavantage.co/query?function=OVERVIEW&symbol=ASML"),
        captured_on=date(2026, 8, 17),
        period_end=date(2025, 12, 31),
    )


def make_security() -> SecurityIdentity:
    """Create the ASML ADR identity used by the provider contract."""

    return SecurityIdentity(
        input_symbol="ASML",
        canonical_symbol="ASML",
        exchange="NASDAQ",
        listing_currency="USD",
        reporting_currency="EUR",
        cik="937966",
    )


def make_financials() -> AnnualFinancials:
    """Create compatible normalized annual statements."""

    source = make_source()
    period = FiscalPeriod(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        fiscal_year=2025,
    )
    return AnnualFinancials(
        period=period,
        income_statement=IncomeStatement(
            period=period,
            reporting_currency="EUR",
            sources=(source,),
            revenue=Decimal("32000"),
        ),
        balance_sheet=BalanceSheet(
            period=period,
            reporting_currency="EUR",
            sources=(source,),
        ),
        cash_flow_statement=CashFlowStatement(
            period=period,
            reporting_currency="EUR",
            sources=(source,),
        ),
    )


class FakeFinancialDataProvider:
    """Minimal provider with already-normalized data for contract tests."""

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        return CompanyProfile(
            security=make_security(),
            name=f"{ticker} Holding N.V.",
            description="A semiconductor equipment company.",
            sources=(make_source(),),
        )

    def get_annual_financials(self, ticker: str) -> tuple[AnnualFinancials, ...]:
        del ticker
        return (make_financials(),)

    def get_market_snapshot(self, ticker: str) -> MarketSnapshot:
        del ticker
        return MarketSnapshot(
            security=make_security(),
            price=Decimal("1000"),
            price_currency="USD",
            price_as_of=date(2026, 8, 14),
            sources=(make_source(),),
        )


class IncompleteProvider:
    """A type missing one required provider operation."""

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        del ticker
        raise NotImplementedError

    def get_annual_financials(self, ticker: str) -> tuple[AnnualFinancials, ...]:
        del ticker
        raise NotImplementedError


class RuntimeCheckOnlyProvider:
    """Demonstrate why this object must not be used as a valid provider."""

    def get_company_profile(self) -> None:
        return None

    def get_annual_financials(self) -> None:
        return None

    def get_market_snapshot(self) -> None:
        return None


def test_complete_provider_satisfies_the_runtime_contract() -> None:
    assert isinstance(FakeFinancialDataProvider(), FinancialDataProvider)


def test_provider_missing_a_required_method_fails_the_runtime_contract() -> None:
    assert not isinstance(IncompleteProvider(), FinancialDataProvider)


def test_runtime_protocol_check_does_not_validate_method_signatures() -> None:
    assert isinstance(RuntimeCheckOnlyProvider(), FinancialDataProvider)


def test_provider_methods_return_the_normalized_contract_shapes() -> None:
    provider = FakeFinancialDataProvider()

    profile = provider.get_company_profile("ASML")
    annual_financials = provider.get_annual_financials("ASML")
    snapshot = provider.get_market_snapshot("ASML")

    assert isinstance(profile, CompanyProfile)
    assert isinstance(annual_financials, tuple)
    assert all(isinstance(item, AnnualFinancials) for item in annual_financials)
    assert isinstance(snapshot, MarketSnapshot)
