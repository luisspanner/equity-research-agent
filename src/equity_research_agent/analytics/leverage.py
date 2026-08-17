"""Deterministic leverage calculations for normalized financial data."""

from decimal import Decimal, localcontext

_CALCULATION_PRECISION = 50


def calculate_ebitda(
    operating_income: Decimal, depreciation_and_amortization: Decimal
) -> Decimal:
    """Calculate the V0 EBITDA proxy from operating income and D&A."""

    _require_finite(operating_income, "operating_income")
    _require_nonnegative_finite(
        depreciation_and_amortization, "depreciation_and_amortization"
    )

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return operating_income + depreciation_and_amortization


def calculate_net_debt(
    total_debt: Decimal, cash_and_cash_equivalents: Decimal
) -> Decimal:
    """Calculate net debt, allowing a negative result for net cash."""

    _require_nonnegative_finite(total_debt, "total_debt")
    _require_nonnegative_finite(cash_and_cash_equivalents, "cash_and_cash_equivalents")

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return total_debt - cash_and_cash_equivalents


def calculate_net_debt_to_ebitda(net_debt: Decimal, ebitda: Decimal) -> Decimal:
    """Calculate net-debt-to-EBITDA when EBITDA is strictly positive."""

    _require_finite(net_debt, "net_debt")
    _require_finite(ebitda, "ebitda")
    if ebitda <= 0:
        raise ValueError("ebitda must be greater than zero")

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return net_debt / ebitda


def _require_nonnegative_finite(value: Decimal, name: str) -> None:
    """Reject negative, NaN, and infinite balance-sheet inputs."""

    _require_finite(value, name)
    if value < 0:
        raise ValueError(f"{name} must not be negative")


def _require_finite(value: Decimal, name: str) -> None:
    """Reject NaN and infinite Decimal values before calculating."""

    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
