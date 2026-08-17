"""Tests for normalized financial-statement and market-data domain models."""

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from equity_research_agent.models.company import SecurityIdentity
from equity_research_agent.models.financials import (
    AnnualFinancials,
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriod,
    IncomeStatement,
    MarketSnapshot,
)
from equity_research_agent.models.provenance import SourceReference


def make_source(**overrides: object) -> SourceReference:
    """Create annual-statement provenance for the ASML provider contract."""

    values: dict[str, object] = {
        "provider": "alpha_vantage",
        "source_type": "annual_statement",
        "source_id": "ASML-income-2025",
        "url": "https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol=ASML",
        "captured_on": date(2026, 8, 17),
        "period_end": date(2025, 12, 31),
    }
    values.update(overrides)
    return SourceReference(**values)


def make_security(**overrides: object) -> SecurityIdentity:
    """Create the US-listed ASML ADR identity."""

    values: dict[str, object] = {
        "input_symbol": "ASML",
        "canonical_symbol": "ASML",
        "exchange": "NASDAQ",
        "listing_currency": "USD",
        "reporting_currency": "EUR",
        "cik": "937966",
    }
    values.update(overrides)
    return SecurityIdentity(**values)


def make_period(**overrides: object) -> FiscalPeriod:
    """Create the latest completed ASML annual period."""

    values: dict[str, object] = {
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 12, 31),
        "fiscal_year": 2025,
        "accounting_standard": "IFRS",
    }
    values.update(overrides)
    return FiscalPeriod(**values)


def make_income_statement(**overrides: object) -> IncomeStatement:
    """Create a normalized EUR income statement with realistic field types."""

    values: dict[str, object] = {
        "period": make_period(),
        "reporting_currency": "EUR",
        "sources": (make_source(),),
        "revenue": Decimal("32000.00"),
        "gross_profit": Decimal("16500.00"),
        "operating_income": Decimal("10500.00"),
        "income_before_tax": Decimal("10600.00"),
        "income_tax_expense": Decimal("1600.00"),
        "net_income": Decimal("9000.00"),
        "depreciation_and_amortization": Decimal("1200.00"),
        "reported_eps": Decimal("23.50"),
    }
    values.update(overrides)
    return IncomeStatement(**values)


def make_balance_sheet(**overrides: object) -> BalanceSheet:
    """Create a normalized EUR balance sheet."""

    values: dict[str, object] = {
        "period": make_period(),
        "reporting_currency": "EUR",
        "sources": (make_source(source_id="ASML-balance-2025"),),
        "cash_and_cash_equivalents": Decimal("5000.00"),
        "total_debt": Decimal("4000.00"),
        "total_shareholder_equity": Decimal("15000.00"),
        "shares_outstanding": 384_100_000,
    }
    values.update(overrides)
    return BalanceSheet(**values)


def make_cash_flow_statement(**overrides: object) -> CashFlowStatement:
    """Create a normalized EUR cash-flow statement."""

    values: dict[str, object] = {
        "period": make_period(),
        "reporting_currency": "EUR",
        "sources": (make_source(source_id="ASML-cash-flow-2025"),),
        "operating_cash_flow": Decimal("9500.00"),
        "capital_expenditure": Decimal("2500.00"),
    }
    values.update(overrides)
    return CashFlowStatement(**values)


def make_annual_financials(**overrides: object) -> AnnualFinancials:
    """Create three compatible EUR statements for one fiscal year."""

    values: dict[str, object] = {
        "period": make_period(),
        "income_statement": make_income_statement(),
        "balance_sheet": make_balance_sheet(),
        "cash_flow_statement": make_cash_flow_statement(),
    }
    values.update(overrides)
    return AnnualFinancials(**values)


def test_annual_financials_accepts_compatible_eur_statements() -> None:
    financials = make_annual_financials()

    assert financials.period.fiscal_year == 2025
    assert financials.income_statement.revenue == Decimal("32000.00")
    assert financials.cash_flow_statement.capital_expenditure == Decimal("2500.00")


def test_fiscal_period_is_annual_only_and_has_a_valid_date_range() -> None:
    with pytest.raises(ValidationError):
        make_period(period_type="quarterly")

    with pytest.raises(ValidationError):
        make_period(start_date=date(2026, 1, 1), end_date=date(2025, 12, 31))

    with pytest.raises(ValidationError):
        make_period(fiscal_year=1999)


def test_fiscal_period_accepts_cross_year_period_with_end_year_label() -> None:
    period = make_period(
        start_date=date(2024, 7, 1),
        end_date=date(2025, 6, 30),
        fiscal_year=2025,
    )

    assert period.fiscal_year == period.end_date.year


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "income_statement": make_income_statement(
                period=make_period(
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 12, 31),
                    fiscal_year=2024,
                )
            )
        },
        {"balance_sheet": make_balance_sheet(reporting_currency="USD")},
    ],
)
def test_annual_financials_rejects_incompatible_statement_data(
    overrides: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        make_annual_financials(**overrides)


def test_missing_financial_values_remain_explicitly_missing() -> None:
    statement = make_income_statement(
        gross_profit=None,
        depreciation_and_amortization=None,
    )

    assert statement.gross_profit is None
    assert statement.depreciation_and_amortization is None


@pytest.mark.parametrize("shares_outstanding", [0, -1])
def test_balance_sheet_rejects_nonpositive_shares_outstanding(
    shares_outstanding: int,
) -> None:
    with pytest.raises(ValidationError):
        make_balance_sheet(shares_outstanding=shares_outstanding)


@pytest.mark.parametrize(
    "capital_expenditure",
    [Decimal("-1"), Decimal("-0.01")],
)
def test_cash_flow_statement_rejects_negative_capital_expenditure(
    capital_expenditure: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        make_cash_flow_statement(capital_expenditure=capital_expenditure)


def test_market_snapshot_keeps_usd_adr_market_data_separate_from_eur_reporting(
) -> None:
    snapshot = MarketSnapshot(
        security=make_security(),
        price=Decimal("1844.0800"),
        price_currency="USD",
        price_as_of=date(2026, 8, 14),
        market_cap=Decimal("708311122000"),
        sources=(
            make_source(
                source_type="daily_price",
                source_id="ASML-price-2026-08-14",
                url="https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=ASML",
            ),
        ),
    )

    assert snapshot.price_currency == "USD"
    assert snapshot.security.reporting_currency == "EUR"
    assert snapshot.price_as_of == date(2026, 8, 14)


@pytest.mark.parametrize(
    "overrides",
    [
        {"price": Decimal("0")},
        {"market_cap": Decimal("0")},
        {"market_cap": Decimal("-1")},
        {"price_currency": "EUR"},
    ],
)
def test_market_snapshot_rejects_nonpositive_or_currency_incompatible_values(
    overrides: dict[str, object]
) -> None:
    values: dict[str, object] = {
        "security": make_security(),
        "price": Decimal("1844.0800"),
        "price_currency": "USD",
        "price_as_of": date(2026, 8, 14),
        "market_cap": Decimal("708311122000"),
        "sources": (make_source(),),
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        MarketSnapshot(**values)


def test_financial_models_serialize_decimal_values_and_provenance() -> None:
    financials = make_annual_financials()

    serialized = json.loads(financials.model_dump_json())

    assert serialized["income_statement"]["revenue"] == "32000.00"
    assert serialized["cash_flow_statement"]["capital_expenditure"] == "2500.00"
    assert serialized["income_statement"]["sources"][0]["period_end"] == "2025-12-31"
