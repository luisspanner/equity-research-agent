"""Tests for deterministic financial-metric assembly."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import HttpUrl

from equity_research_agent.analytics.metrics import assemble_financial_metrics
from equity_research_agent.data.providers.alpha_vantage import (
    normalize_annual_financials,
    normalize_company_profile,
    normalize_market_snapshot,
)
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

FIXTURE_DIRECTORY = (
    Path(__file__).parent / "fixtures" / "providers" / "alpha_vantage" / "asml"
)


def make_source(year: int) -> SourceReference:
    """Create provenance for normalized annual fixture data."""

    return SourceReference(
        provider="test_provider",
        source_type="annual_statement",
        source_id=f"TEST-{year}",
        url=HttpUrl("https://example.com/financials"),
        captured_on=date(2026, 8, 17),
        period_end=date(year, 12, 31),
    )


def make_financials(
    year: int,
    *,
    revenue: Decimal | None = Decimal("100"),
    eps: Decimal | None = Decimal("10"),
    shares: int | None = 100,
    currency: str = "EUR",
    operating_cash_flow: Decimal | None = Decimal("30"),
    capital_expenditure: Decimal | None = Decimal("10"),
    gross_profit: Decimal | None = Decimal("60"),
    operating_income: Decimal | None = Decimal("25"),
    depreciation_and_amortization: Decimal | None = Decimal("5"),
    total_debt: Decimal | None = Decimal("40"),
    cash_and_cash_equivalents: Decimal | None = Decimal("15"),
    net_income: Decimal | None = Decimal("20"),
    total_shareholder_equity: Decimal | None = Decimal("100"),
) -> AnnualFinancials:
    """Create one complete, compatible annual reporting period."""

    period = FiscalPeriod(
        start_date=date(year, 1, 1), end_date=date(year, 12, 31), fiscal_year=year
    )
    source = make_source(year)
    return AnnualFinancials(
        period=period,
        income_statement=IncomeStatement(
            period=period,
            reporting_currency=currency,
            sources=(source,),
            revenue=revenue,
            gross_profit=gross_profit,
            operating_income=operating_income,
            net_income=net_income,
            depreciation_and_amortization=depreciation_and_amortization,
            reported_eps=eps,
        ),
        balance_sheet=BalanceSheet(
            period=period,
            reporting_currency=currency,
            sources=(source,),
            cash_and_cash_equivalents=cash_and_cash_equivalents,
            total_debt=total_debt,
            total_shareholder_equity=total_shareholder_equity,
            shares_outstanding=shares,
        ),
        cash_flow_statement=CashFlowStatement(
            period=period,
            reporting_currency=currency,
            sources=(source,),
            operating_cash_flow=operating_cash_flow,
            capital_expenditure=capital_expenditure,
        ),
    )


def make_market_snapshot(
    currency: str = "USD", market_cap: Decimal | None = None
) -> MarketSnapshot:
    """Create a sourced end-of-day market snapshot."""

    return MarketSnapshot(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency=currency,
        ),
        price=Decimal("100"),
        price_currency=currency,
        price_as_of=date(2026, 8, 14),
        market_cap=market_cap,
        sources=(make_source(2025),),
    )


def test_assembler_calculates_available_latest_period_metrics() -> None:
    metrics = assemble_financial_metrics(
        (
            make_financials(
                2024, revenue=Decimal("100"), eps=Decimal("10"), shares=100
            ),
            make_financials(
                2025, revenue=Decimal("121"), eps=Decimal("12.1"), shares=110
            ),
        ),
        make_market_snapshot("EUR", Decimal("1000")),
        nopat=Decimal("15"),
        invested_capital=Decimal("75"),
    )

    assert metrics.latest_period_end == date(2025, 12, 31)
    assert metrics.reporting_currency == "EUR"
    assert metrics.revenue_cagr == pytest.approx(Decimal("0.21"))
    assert metrics.eps_cagr == pytest.approx(Decimal("0.21"))
    assert metrics.share_count_cagr == pytest.approx(Decimal("0.1"))
    assert metrics.fcf == Decimal("20")
    assert metrics.fcf_margin == pytest.approx(Decimal("20") / Decimal("121"))
    assert metrics.gross_margin == pytest.approx(Decimal("60") / Decimal("121"))
    assert metrics.operating_margin == pytest.approx(Decimal("25") / Decimal("121"))
    assert metrics.ebitda == Decimal("30")
    assert metrics.net_debt == Decimal("25")
    assert metrics.net_debt_to_ebitda == pytest.approx(Decimal("25") / Decimal("30"))
    assert metrics.roe == Decimal("0.2")
    assert metrics.roic == Decimal("0.2")
    assert metrics.pe_ratio == Decimal("50")
    assert metrics.fcf_yield == Decimal("0.02")
    assert metrics.ev_to_ebitda == pytest.approx(Decimal("1025") / Decimal("30"))
    assert metrics.market_metric_unavailabilities == ()


def test_assembler_uses_latest_period_even_when_input_is_unsorted() -> None:
    metrics = assemble_financial_metrics(
        (make_financials(2025), make_financials(2024))
    )

    assert metrics.latest_period_end == date(2025, 12, 31)


def test_assembler_preserves_missing_inputs_as_none() -> None:
    metrics = assemble_financial_metrics(
        (
            make_financials(2024),
            make_financials(
                2025,
                revenue=None,
                eps=None,
                shares=None,
                operating_cash_flow=None,
                gross_profit=None,
                operating_income=None,
                total_debt=None,
                net_income=None,
            ),
        )
    )

    assert metrics.revenue_cagr is None
    assert metrics.eps_cagr is None
    assert metrics.share_count_cagr is None
    assert metrics.fcf is None
    assert metrics.fcf_margin is None
    assert metrics.gross_margin is None
    assert metrics.operating_margin is None
    assert metrics.ebitda is None
    assert metrics.net_debt is None
    assert metrics.net_debt_to_ebitda is None
    assert metrics.roe is None
    assert metrics.roic is None


def test_assembler_records_currency_incompatibility_for_all_market_metrics() -> None:
    metrics = assemble_financial_metrics(
        (make_financials(2025),), make_market_snapshot("USD")
    )

    assert [item.metric for item in metrics.market_metric_unavailabilities] == [
        "pe_ratio",
        "fcf_yield",
        "ev_to_ebitda",
    ]
    assert all(
        "does not match" in item.reason
        for item in metrics.market_metric_unavailabilities
    )


def test_assembler_records_missing_market_snapshot_for_all_market_metrics() -> None:
    metrics = assemble_financial_metrics((make_financials(2025),))

    assert len(metrics.market_metric_unavailabilities) == 3
    assert all(
        "no market snapshot" in item.reason
        for item in metrics.market_metric_unavailabilities
    )


def test_assembler_marks_nonpositive_income_and_ebitda_unavailable() -> None:
    metrics = assemble_financial_metrics(
        (
            make_financials(
                2025,
                net_income=Decimal("0"),
                operating_income=Decimal("-5"),
            ),
        ),
        make_market_snapshot("EUR", Decimal("1000")),
    )

    assert metrics.pe_ratio is None
    assert metrics.ev_to_ebitda is None
    assert [item.metric for item in metrics.market_metric_unavailabilities] == [
        "pe_ratio",
        "ev_to_ebitda",
    ]


def load_fixture(name: str) -> dict[str, object]:
    """Load a checked-in raw Alpha Vantage fixture."""

    with (FIXTURE_DIRECTORY / name).open() as fixture_file:
        payload: object = json.load(fixture_file)
    assert isinstance(payload, dict)
    return payload


def make_alpha_vantage_source(endpoint: str) -> SourceReference:
    """Create credential-free provenance for an Alpha Vantage fixture."""

    return SourceReference(
        provider="alpha_vantage",
        source_type=endpoint,
        source_id=f"ASML-{endpoint}",
        url=f"https://www.alphavantage.co/query?function={endpoint}&symbol=ASML",
        captured_on=date(2026, 8, 17),
    )


def test_asml_fixture_marks_market_metrics_currency_incompatible() -> None:
    sources = {
        endpoint: make_alpha_vantage_source(endpoint)
        for endpoint in ("income_statement", "balance_sheet", "cash_flow", "earnings")
    }
    profile = normalize_company_profile(
        load_fixture("overview.json"), make_alpha_vantage_source("overview")
    )
    financials = normalize_annual_financials(
        load_fixture("income_statement.json"),
        load_fixture("balance_sheet.json"),
        load_fixture("cash_flow.json"),
        load_fixture("earnings.json"),
        sources,
    )
    market_snapshot = normalize_market_snapshot(
        load_fixture("overview.json"),
        load_fixture("time_series_daily.json"),
        profile.security,
        make_alpha_vantage_source("overview"),
        make_alpha_vantage_source("time_series_daily"),
    )

    metrics = assemble_financial_metrics(financials, market_snapshot)

    assert metrics.reporting_currency == "EUR"
    assert market_snapshot.price_currency == "USD"
    assert metrics.pe_ratio is None
    assert metrics.fcf_yield is None
    assert metrics.ev_to_ebitda is None
    assert [item.metric for item in metrics.market_metric_unavailabilities] == [
        "pe_ratio",
        "fcf_yield",
        "ev_to_ebitda",
    ]


def test_assembler_rejects_empty_or_duplicate_period_series() -> None:
    with pytest.raises(ValueError, match="at least one"):
        assemble_financial_metrics(())

    with pytest.raises(ValueError, match="distinct"):
        assemble_financial_metrics((make_financials(2025), make_financials(2025)))


def test_metrics_json_serializes_decimal_values_as_strings() -> None:
    metrics = assemble_financial_metrics((make_financials(2025),))

    assert '"fcf":"20"' in metrics.model_dump_json()
