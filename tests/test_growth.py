"""Tests for deterministic annual growth calculations."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from equity_research_agent.analytics.growth import (
    calculate_cagr,
    calculate_eps_cagr,
    calculate_revenue_cagr,
    calculate_share_count_cagr,
)
from equity_research_agent.models.financials import (
    AnnualFinancials,
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriod,
    IncomeStatement,
)
from equity_research_agent.models.provenance import SourceReference


def make_source(year: int) -> SourceReference:
    """Create minimal annual-statement provenance."""

    return SourceReference(
        provider="alpha_vantage",
        source_type="annual_statement",
        source_id=f"ASML-{year}",
        url=HttpUrl(
            "https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol=ASML"
        ),
        captured_on=date(2026, 8, 17),
        period_end=date(year, 12, 31),
    )


def make_financials(
    year: int,
    *,
    revenue: Decimal | None = Decimal("100"),
    reported_eps: Decimal | None = Decimal("10"),
    shares_outstanding: int | None = None,
    currency: str = "EUR",
) -> AnnualFinancials:
    """Create compatible ASML-like annual statements for one fiscal year."""

    period = FiscalPeriod(
        start_date=date(year, 1, 1),
        end_date=date(year, 12, 31),
        fiscal_year=year,
    )
    source = make_source(year)
    return AnnualFinancials(
        period=period,
        income_statement=IncomeStatement(
            period=period,
            reporting_currency=currency,
            sources=(source,),
            revenue=revenue,
            reported_eps=reported_eps,
        ),
        balance_sheet=BalanceSheet(
            period=period,
            reporting_currency=currency,
            sources=(source,),
            shares_outstanding=shares_outstanding,
        ),
        cash_flow_statement=CashFlowStatement(
            period=period,
            reporting_currency=currency,
            sources=(source,),
        ),
    )


@pytest.mark.parametrize(
    ("start_value", "end_value", "years", "expected"),
    [
        (Decimal("100"), Decimal("121"), 2, Decimal("0.1")),
        (Decimal("100"), Decimal("100"), 4, Decimal("0")),
    ],
)
def test_calculate_cagr_returns_expected_growth(
    start_value: Decimal,
    end_value: Decimal,
    years: int,
    expected: Decimal,
) -> None:
    assert calculate_cagr(start_value, end_value, years) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("start_value", "end_value", "years"),
    [
        (Decimal("0"), Decimal("100"), 1),
        (Decimal("-1"), Decimal("100"), 1),
        (Decimal("100"), Decimal("0"), 1),
        (Decimal("100"), Decimal("-1"), 1),
        (Decimal("NaN"), Decimal("100"), 1),
        (Decimal("100"), Decimal("NaN"), 1),
        (Decimal("Infinity"), Decimal("100"), 1),
        (Decimal("100"), Decimal("Infinity"), 1),
        (Decimal("-Infinity"), Decimal("100"), 1),
        (Decimal("100"), Decimal("-Infinity"), 1),
        (Decimal("100"), Decimal("121"), 0),
    ],
)
def test_calculate_cagr_rejects_values_without_a_real_solution(
    start_value: Decimal, end_value: Decimal, years: int
) -> None:
    with pytest.raises(ValueError):
        calculate_cagr(start_value, end_value, years)


def test_revenue_cagr_sorts_newest_first_financials() -> None:
    newest_first = (
        make_financials(2025, revenue=Decimal("144")),
        make_financials(2024, revenue=Decimal("120")),
        make_financials(2023, revenue=Decimal("100")),
    )

    assert calculate_revenue_cagr(newest_first) == pytest.approx(Decimal("0.2"))


def test_eps_cagr_uses_reported_eps_endpoints() -> None:
    financials = (
        make_financials(2023, reported_eps=Decimal("10")),
        make_financials(2024, reported_eps=Decimal("12")),
        make_financials(2025, reported_eps=Decimal("14.4")),
    )

    assert calculate_eps_cagr(financials) == pytest.approx(Decimal("0.2"))


def test_share_count_cagr_uses_balance_sheet_endpoints() -> None:
    financials = (
        make_financials(2023, shares_outstanding=100),
        make_financials(2024, shares_outstanding=110),
        make_financials(2025, shares_outstanding=121),
    )

    assert calculate_share_count_cagr(financials) == pytest.approx(Decimal("0.1"))


def test_share_count_cagr_can_be_negative_for_share_buybacks() -> None:
    financials = (
        make_financials(2023, shares_outstanding=121),
        make_financials(2024, shares_outstanding=110),
        make_financials(2025, shares_outstanding=100),
    )

    expected = Decimal("-0.09090909090909090909090909091")

    assert calculate_share_count_cagr(financials) == pytest.approx(expected)


def test_share_count_cagr_rejects_missing_share_counts() -> None:
    financials = (
        make_financials(2024, shares_outstanding=None),
        make_financials(2025, shares_outstanding=100),
    )

    with pytest.raises(ValueError, match="shares_outstanding"):
        calculate_share_count_cagr(financials)


def test_share_count_cagr_does_not_require_matching_reporting_currencies() -> None:
    financials = (
        make_financials(2024, shares_outstanding=100, currency="EUR"),
        make_financials(2025, shares_outstanding=121, currency="USD"),
    )

    assert calculate_share_count_cagr(financials) == pytest.approx(Decimal("0.21"))
    with pytest.raises(ValueError):
        calculate_revenue_cagr(financials)


@pytest.mark.parametrize(
    "financials",
    [
        (make_financials(2025),),
        (make_financials(2025), make_financials(2025)),
    ],
)
def test_series_cagr_requires_distinct_annual_periods(
    financials: tuple[AnnualFinancials, ...],
) -> None:
    with pytest.raises(ValueError):
        calculate_revenue_cagr(financials)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (make_financials(2024, revenue=None), make_financials(2025)),
        (make_financials(2024), make_financials(2025, revenue=None)),
        (make_financials(2024, reported_eps=None), make_financials(2025)),
    ],
)
def test_series_cagr_rejects_missing_relevant_values(
    first: AnnualFinancials, second: AnnualFinancials
) -> None:
    calculator = (
        calculate_eps_cagr
        if first.income_statement.reported_eps is None
        else calculate_revenue_cagr
    )

    with pytest.raises(ValueError):
        calculator((first, second))


def test_series_cagr_rejects_incompatible_reporting_currencies() -> None:
    financials = (
        make_financials(2024, currency="EUR"),
        make_financials(2025, currency="USD"),
    )

    with pytest.raises(ValueError):
        calculate_revenue_cagr(financials)
