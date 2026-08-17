"""Deterministic capital-efficiency calculations.

Callers are responsible for deriving NOPAT, invested capital, and shareholder
equity from compatible accounting data. These functions intentionally do not
infer tax rates, use average balances, or normalize source statements.
"""

from decimal import Decimal, localcontext

_CALCULATION_PRECISION = 50


def calculate_roic(nopat: Decimal, invested_capital: Decimal) -> Decimal:
    """Calculate return on invested capital from caller-supplied inputs."""

    return _calculate_return(nopat, invested_capital, "nopat", "invested_capital")


def calculate_roe(net_income: Decimal, shareholder_equity: Decimal) -> Decimal:
    """Calculate return on equity from caller-supplied inputs."""

    return _calculate_return(
        net_income,
        shareholder_equity,
        "net_income",
        "shareholder_equity",
    )


def _calculate_return(
    numerator: Decimal,
    denominator: Decimal,
    numerator_name: str,
    denominator_name: str,
) -> Decimal:
    """Validate a return ratio before dividing with fixed local precision."""

    _require_finite(numerator, numerator_name)
    _require_finite(denominator, denominator_name)
    if denominator <= 0:
        raise ValueError(f"{denominator_name} must be greater than zero")

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return numerator / denominator


def _require_finite(value: Decimal, name: str) -> None:
    """Reject NaN and infinite Decimal inputs before calculating."""

    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
