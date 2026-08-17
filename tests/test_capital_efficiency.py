"""Tests for deterministic capital-efficiency calculations."""

from collections.abc import Callable
from decimal import Decimal, getcontext, setcontext

import pytest

from equity_research_agent.analytics.capital_efficiency import (
    calculate_roe,
    calculate_roic,
)

ReturnCalculator = Callable[[Decimal, Decimal], Decimal]


@pytest.mark.parametrize(
    ("calculator", "numerator", "denominator", "expected"),
    [
        (calculate_roic, Decimal("15"), Decimal("100"), Decimal("0.15")),
        (calculate_roe, Decimal("12"), Decimal("80"), Decimal("0.15")),
        (calculate_roic, Decimal("-15"), Decimal("100"), Decimal("-0.15")),
        (calculate_roe, Decimal("-12"), Decimal("80"), Decimal("-0.15")),
    ],
)
def test_return_calculations_allow_finite_positive_or_negative_numerators(
    calculator: ReturnCalculator,
    numerator: Decimal,
    denominator: Decimal,
    expected: Decimal,
) -> None:
    assert calculator(numerator, denominator) == expected


@pytest.mark.parametrize("calculator", [calculate_roic, calculate_roe])
@pytest.mark.parametrize(
    "numerator", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
)
def test_return_calculations_reject_nonfinite_numerators(
    calculator: ReturnCalculator, numerator: Decimal
) -> None:
    with pytest.raises(ValueError):
        calculator(numerator, Decimal("100"))


@pytest.mark.parametrize("calculator", [calculate_roic, calculate_roe])
@pytest.mark.parametrize(
    "denominator",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_return_calculations_reject_invalid_denominators(
    calculator: ReturnCalculator, denominator: Decimal
) -> None:
    with pytest.raises(ValueError):
        calculator(Decimal("10"), denominator)


def test_return_calculations_do_not_mutate_global_decimal_context() -> None:
    original_context = getcontext().copy()

    calculate_roic(Decimal("15"), Decimal("100"))
    calculate_roe(Decimal("12"), Decimal("80"))

    current_context = getcontext()
    assert current_context.prec == original_context.prec
    assert current_context.rounding == original_context.rounding
    assert current_context.Emin == original_context.Emin
    assert current_context.Emax == original_context.Emax
    assert current_context.capitals == original_context.capitals
    assert current_context.clamp == original_context.clamp
    assert current_context.flags == original_context.flags
    assert current_context.traps == original_context.traps


@pytest.mark.parametrize("calculator", [calculate_roic, calculate_roe])
def test_return_calculations_use_fixed_local_precision(
    calculator: ReturnCalculator,
) -> None:
    original_context = getcontext().copy()

    try:
        getcontext().prec = 6
        low_precision_result = calculator(Decimal("1"), Decimal("7"))
        assert getcontext().prec == 6

        getcontext().prec = 40
        high_precision_result = calculator(Decimal("1"), Decimal("7"))
        assert getcontext().prec == 40
    finally:
        setcontext(original_context)

    assert low_precision_result == high_precision_result
    assert low_precision_result == Decimal(
        "0.14285714285714285714285714285714285714285714285714"
    )
