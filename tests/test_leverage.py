"""Tests for deterministic leverage calculations."""

from decimal import Decimal, getcontext, setcontext

import pytest

from equity_research_agent.analytics.leverage import (
    calculate_ebitda,
    calculate_net_debt,
    calculate_net_debt_to_ebitda,
)


def test_calculate_ebitda_adds_operating_income_and_depreciation() -> None:
    assert calculate_ebitda(Decimal("100"), Decimal("20")) == Decimal("120")


def test_calculate_ebitda_allows_negative_operating_income() -> None:
    assert calculate_ebitda(Decimal("-25"), Decimal("20")) == Decimal("-5")


@pytest.mark.parametrize(
    "operating_income", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
)
def test_calculate_ebitda_rejects_nonfinite_operating_income(
    operating_income: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_ebitda(operating_income, Decimal("20"))


@pytest.mark.parametrize(
    "depreciation_and_amortization",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_calculate_ebitda_rejects_invalid_depreciation_and_amortization(
    depreciation_and_amortization: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_ebitda(Decimal("100"), depreciation_and_amortization)


def test_calculate_net_debt_subtracts_cash_from_debt() -> None:
    assert calculate_net_debt(Decimal("120"), Decimal("30")) == Decimal("90")


def test_calculate_net_debt_allows_a_negative_net_cash_result() -> None:
    assert calculate_net_debt(Decimal("30"), Decimal("120")) == Decimal("-90")


@pytest.mark.parametrize(
    "total_debt",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_calculate_net_debt_rejects_invalid_total_debt(total_debt: Decimal) -> None:
    with pytest.raises(ValueError):
        calculate_net_debt(total_debt, Decimal("30"))


@pytest.mark.parametrize(
    "cash_and_cash_equivalents",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_calculate_net_debt_rejects_invalid_cash(
    cash_and_cash_equivalents: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_net_debt(Decimal("120"), cash_and_cash_equivalents)


def test_calculate_net_debt_to_ebitda_returns_unrounded_ratio() -> None:
    assert calculate_net_debt_to_ebitda(Decimal("90"), Decimal("120")) == Decimal(
        "0.75"
    )


def test_calculate_net_debt_to_ebitda_allows_negative_net_debt() -> None:
    assert calculate_net_debt_to_ebitda(Decimal("-90"), Decimal("120")) == Decimal(
        "-0.75"
    )


@pytest.mark.parametrize(
    "net_debt", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
)
def test_calculate_net_debt_to_ebitda_rejects_nonfinite_net_debt(
    net_debt: Decimal,
) -> None:
    with pytest.raises(ValueError):
        calculate_net_debt_to_ebitda(net_debt, Decimal("120"))


@pytest.mark.parametrize(
    "ebitda",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_calculate_net_debt_to_ebitda_rejects_invalid_ebitda(ebitda: Decimal) -> None:
    with pytest.raises(ValueError):
        calculate_net_debt_to_ebitda(Decimal("90"), ebitda)


def test_calculations_do_not_mutate_global_decimal_context() -> None:
    original_context = getcontext().copy()

    calculate_ebitda(Decimal("100"), Decimal("20"))
    calculate_net_debt(Decimal("120"), Decimal("30"))
    calculate_net_debt_to_ebitda(Decimal("90"), Decimal("120"))

    current_context = getcontext()
    assert current_context.prec == original_context.prec
    assert current_context.rounding == original_context.rounding
    assert current_context.Emin == original_context.Emin
    assert current_context.Emax == original_context.Emax
    assert current_context.capitals == original_context.capitals
    assert current_context.clamp == original_context.clamp
    assert current_context.flags == original_context.flags
    assert current_context.traps == original_context.traps


def test_net_debt_to_ebitda_uses_fixed_local_precision() -> None:
    original_context = getcontext().copy()

    try:
        getcontext().prec = 6
        low_precision_result = calculate_net_debt_to_ebitda(
            Decimal("1"), Decimal("7")
        )
        assert getcontext().prec == 6

        getcontext().prec = 40
        high_precision_result = calculate_net_debt_to_ebitda(
            Decimal("1"), Decimal("7")
        )
        assert getcontext().prec == 40
    finally:
        setcontext(original_context)

    assert low_precision_result == high_precision_result
    assert low_precision_result == Decimal(
        "0.14285714285714285714285714285714285714285714285714"
    )
