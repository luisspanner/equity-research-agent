"""Deterministic growth-rate calculations for normalized annual financials."""

from collections.abc import Callable, Sequence
from decimal import Decimal, localcontext

from equity_research_agent.models.financials import AnnualFinancials

_CALCULATION_PRECISION = 50


def calculate_cagr(start_value: Decimal, end_value: Decimal, years: int) -> Decimal:
    """Calculate compound annual growth using high-precision decimal arithmetic.

    The local precision keeps fractional exponents stable without changing the
    process-wide Decimal context used by unrelated code.
    """

    if not start_value.is_finite() or start_value <= 0:
        raise ValueError("start_value must be greater than zero")
    if not end_value.is_finite() or end_value <= 0:
        raise ValueError("end_value must be greater than zero")
    if years <= 0:
        raise ValueError("years must be greater than zero")

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return (end_value / start_value) ** (Decimal(1) / Decimal(years)) - Decimal(1)


def calculate_revenue_cagr(financials: Sequence[AnnualFinancials]) -> Decimal:
    """Calculate revenue CAGR across a compatible annual financial series."""

    return _calculate_statement_cagr(
        financials,
        lambda item: item.income_statement.revenue,
        "revenue",
    )


def calculate_eps_cagr(financials: Sequence[AnnualFinancials]) -> Decimal:
    """Calculate reported EPS CAGR across a compatible annual financial series."""

    return _calculate_statement_cagr(
        financials,
        lambda item: item.income_statement.reported_eps,
        "reported_eps",
    )


def calculate_share_count_cagr(financials: Sequence[AnnualFinancials]) -> Decimal:
    """Calculate share-count CAGR across annual financials.

    Share counts are unitless, so financial-statement reporting currencies do
    not affect their comparability.
    """

    return _calculate_statement_cagr(
        financials,
        lambda item: item.balance_sheet.shares_outstanding,
        "shares_outstanding",
        require_one_reporting_currency=False,
    )


def _calculate_statement_cagr(
    financials: Sequence[AnnualFinancials],
    value_for: Callable[[AnnualFinancials], Decimal | int | None],
    metric_name: str,
    *,
    require_one_reporting_currency: bool = True,
) -> Decimal:
    """Validate an annual series and calculate its endpoint CAGR."""

    if len(financials) < 2:
        raise ValueError("at least two annual financial periods are required")

    period_end_dates = [item.period.end_date for item in financials]
    if len(set(period_end_dates)) != len(period_end_dates):
        raise ValueError("annual financial periods must have distinct end dates")

    if require_one_reporting_currency:
        reporting_currencies = {
            item.income_statement.reporting_currency for item in financials
        }
        if len(reporting_currencies) != 1:
            raise ValueError(
                "annual financial periods must use one reporting currency"
            )

    sorted_financials = sorted(financials, key=lambda item: item.period.end_date)
    values = [value_for(item) for item in sorted_financials]
    if any(value is None for value in values):
        raise ValueError(f"{metric_name} is required for every annual period")

    earliest = sorted_financials[0]
    latest = sorted_financials[-1]
    years = latest.period.end_date.year - earliest.period.end_date.year
    if years <= 0:
        raise ValueError(
            "annual financial periods must span at least one calendar year"
        )

    start_value = values[0]
    end_value = values[-1]
    assert start_value is not None
    assert end_value is not None
    return calculate_cagr(Decimal(start_value), Decimal(end_value), years)
