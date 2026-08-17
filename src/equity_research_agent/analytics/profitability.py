"""Deterministic cash-flow and margin calculations."""

from decimal import Decimal, localcontext

_CALCULATION_PRECISION = 50


def calculate_free_cash_flow(
    operating_cash_flow: Decimal, capital_expenditure: Decimal
) -> Decimal:
    """Calculate free cash flow when CapEx is recorded as a positive outflow."""

    _require_finite(operating_cash_flow, "operating_cash_flow")
    _require_finite(capital_expenditure, "capital_expenditure")
    if capital_expenditure < 0:
        raise ValueError("capital_expenditure must not be negative")

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return operating_cash_flow - capital_expenditure


def calculate_fcf_margin(free_cash_flow: Decimal, revenue: Decimal) -> Decimal:
    """Calculate free-cash-flow margin without rounding the result."""

    return _calculate_margin(free_cash_flow, revenue, "free_cash_flow")


def calculate_gross_margin(gross_profit: Decimal, revenue: Decimal) -> Decimal:
    """Calculate gross margin without rounding the result."""

    return _calculate_margin(gross_profit, revenue, "gross_profit")


def calculate_operating_margin(operating_income: Decimal, revenue: Decimal) -> Decimal:
    """Calculate operating margin without rounding the result."""

    return _calculate_margin(operating_income, revenue, "operating_income")


def _calculate_margin(
    numerator: Decimal, revenue: Decimal, numerator_name: str
) -> Decimal:
    """Validate inputs shared by the margin calculations."""

    _require_finite(numerator, numerator_name)
    _require_finite(revenue, "revenue")
    if revenue <= 0:
        raise ValueError("revenue must be greater than zero")

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return numerator / revenue


def _require_finite(value: Decimal, name: str) -> None:
    """Reject NaN and infinite Decimal values before calculating."""

    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
