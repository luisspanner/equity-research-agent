"""Tests for deterministic free-cash-flow and margin calculations."""

from collections.abc import Callable
from decimal import Decimal, getcontext, setcontext

import pytest

from equity_research_agent.analytics.profitability import (
    calculate_fcf_margin,
    calculate_free_cash_flow,
    calculate_gross_margin,
    calculate_operating_margin,
)

MarginCalculator = Callable[[Decimal, Decimal], Decimal]


def test_calculate_free_cash_flow_subtracts_positive_capex() -> None:
    assert calculate_free_cash_flow(Decimal("120"), Decimal("30")) == Decimal("90")


def test_calculate_free_cash_flow_allows_zero_capex() -> None:
    assert calculate_free_cash_flow(Decimal("120"), Decimal("0")) == Decimal("120")


def test_calculate_free_cash_flow_allows_negative_operating_cash_flow() -> None:
    assert calculate_free_cash_flow(Decimal("-10"), Decimal("30")) == Decimal("-40")


@pytest.mark.parametrize(
    "capital_expenditure",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_calculate_free_cash_flow_rejects_invalid_capex(
    capital_expenditure: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_free_cash_flow(Decimal("100"), capital_expenditure)


@pytest.mark.parametrize(
    "operating_cash_flow",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_calculate_free_cash_flow_rejects_nonfinite_operating_cash_flow(
    operating_cash_flow: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_free_cash_flow(operating_cash_flow, Decimal("0"))


@pytest.mark.parametrize(
    ("calculator", "numerator"),
    [
        (calculate_fcf_margin, Decimal("25")),
        (calculate_gross_margin, Decimal("60")),
        (calculate_operating_margin, Decimal("20")),
    ],
)
def test_margin_calculations_return_unrounded_decimal_quotients(
    calculator: MarginCalculator, numerator: Decimal
) -> None:
    result = calculator(numerator, Decimal("100"))

    assert result == numerator / Decimal("100")
    assert isinstance(result, Decimal)


@pytest.mark.parametrize(
    ("calculator", "numerator"),
    [
        (calculate_fcf_margin, Decimal("-25")),
        (calculate_gross_margin, Decimal("-60")),
        (calculate_operating_margin, Decimal("-20")),
    ],
)
def test_margin_calculations_allow_negative_numerators(
    calculator: MarginCalculator, numerator: Decimal
) -> None:
    assert calculator(numerator, Decimal("100")) == numerator / Decimal("100")


@pytest.mark.parametrize(
    "calculator",
    [calculate_fcf_margin, calculate_gross_margin, calculate_operating_margin],
)
@pytest.mark.parametrize(
    "revenue",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_margin_calculations_reject_invalid_revenue(
    calculator: MarginCalculator, revenue: Decimal
) -> None:
    with pytest.raises(ValueError):
        calculator(Decimal("10"), revenue)


@pytest.mark.parametrize(
    "calculator",
    [calculate_fcf_margin, calculate_gross_margin, calculate_operating_margin],
)
@pytest.mark.parametrize(
    "numerator",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_margin_calculations_reject_nonfinite_numerators(
    calculator: MarginCalculator, numerator: Decimal
) -> None:
    with pytest.raises(ValueError):
        calculator(numerator, Decimal("100"))


def test_calculations_do_not_mutate_global_decimal_context() -> None:
    original_context = getcontext().copy()

    calculate_free_cash_flow(Decimal("120"), Decimal("30"))
    calculate_fcf_margin(Decimal("25"), Decimal("100"))
    calculate_gross_margin(Decimal("60"), Decimal("100"))
    calculate_operating_margin(Decimal("20"), Decimal("100"))

    current_context = getcontext()
    assert current_context.prec == original_context.prec
    assert current_context.rounding == original_context.rounding
    assert current_context.Emin == original_context.Emin
    assert current_context.Emax == original_context.Emax
    assert current_context.capitals == original_context.capitals
    assert current_context.clamp == original_context.clamp
    assert current_context.flags == original_context.flags
    assert current_context.traps == original_context.traps


def test_margin_calculation_uses_fixed_local_precision() -> None:
    original_context = getcontext().copy()

    try:
        getcontext().prec = 6
        low_precision_result = calculate_fcf_margin(Decimal("1"), Decimal("7"))
        assert getcontext().prec == 6

        getcontext().prec = 40
        high_precision_result = calculate_fcf_margin(Decimal("1"), Decimal("7"))
        assert getcontext().prec == 40
    finally:
        setcontext(original_context)

    assert low_precision_result == high_precision_result
    assert low_precision_result == Decimal(
        "0.14285714285714285714285714285714285714285714285714"
    )
