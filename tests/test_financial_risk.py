"""Tests for provenance-preserving financial-risk inputs."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from equity_research_agent.analytics.financial_risk import (
    build_financial_risk_context,
)
from equity_research_agent.analytics.metrics import assemble_financial_metrics
from equity_research_agent.models.company import SecurityIdentity
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
from equity_research_agent.models.financials import (
    AnnualFinancials,
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriod,
    IncomeStatement,
    MarketSnapshot,
)
from equity_research_agent.models.metrics import FinancialMetrics
from equity_research_agent.models.provenance import SourceReference


def make_source(source_id: str) -> SourceReference:
    """Create stable provenance for one financial statement."""

    return SourceReference(
        provider="test_provider",
        source_type="annual_statement",
        source_id=source_id,
        url=HttpUrl(f"https://example.com/{source_id}"),
        captured_on=date(2026, 8, 18),
    )


def make_financials(
    year: int,
    *,
    operating_cash_flow: Decimal | None = Decimal("30"),
    gross_profit: Decimal | None = Decimal("60"),
) -> AnnualFinancials:
    """Create a complete annual period with distinct statement sources."""

    period = FiscalPeriod(
        start_date=date(year, 1, 1), end_date=date(year, 12, 31), fiscal_year=year
    )
    return AnnualFinancials(
        period=period,
        income_statement=IncomeStatement(
            period=period,
            reporting_currency="EUR",
            sources=(make_source(f"income-{year}"),),
            revenue=Decimal("100"),
            gross_profit=gross_profit,
            operating_income=Decimal("25"),
            net_income=Decimal("20"),
            depreciation_and_amortization=Decimal("5"),
            reported_eps=Decimal("10"),
        ),
        balance_sheet=BalanceSheet(
            period=period,
            reporting_currency="EUR",
            sources=(make_source(f"balance-{year}"),),
            cash_and_cash_equivalents=Decimal("15"),
            total_debt=Decimal("40"),
            total_shareholder_equity=Decimal("100"),
            shares_outstanding=100,
        ),
        cash_flow_statement=CashFlowStatement(
            period=period,
            reporting_currency="EUR",
            sources=(make_source(f"cashflow-{year}"),),
            operating_cash_flow=operating_cash_flow,
            capital_expenditure=Decimal("10"),
        ),
    )


def make_market_snapshot(currency: str = "EUR") -> MarketSnapshot:
    """Create a sourced market snapshot compatible with the fixture financials."""

    return MarketSnapshot(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency=currency,
        ),
        price=Decimal("100"),
        price_currency=currency,
        price_as_of=date(2026, 8, 18),
        market_cap=Decimal("1000"),
        sources=(make_source("market"),),
    )


def make_metrics(
    financials: tuple[AnnualFinancials, ...],
    market_snapshot: MarketSnapshot | None,
) -> FinancialMetrics:
    """Create every financial-risk metric, including unsupported ROIC."""

    return assemble_financial_metrics(financials, market_snapshot)


def metric_sources(context: FinancialRiskContext, metric: str) -> tuple[str, ...]:
    """Return the source IDs for one named metric."""

    return next(item.source_ids for item in context.metrics if item.metric == metric)


def test_builder_assigns_exact_sources_to_supported_metric_categories() -> None:
    financials = (make_financials(2024), make_financials(2025))
    market_snapshot = make_market_snapshot()

    context = build_financial_risk_context(
        make_metrics(financials, market_snapshot), financials, market_snapshot
    )

    assert metric_sources(context, "revenue_cagr") == ("income-2024", "income-2025")
    assert metric_sources(context, "eps_cagr") == ("income-2024", "income-2025")
    assert metric_sources(context, "share_count_cagr") == (
        "balance-2024",
        "balance-2025",
    )
    assert metric_sources(context, "fcf") == ("cashflow-2025",)
    assert metric_sources(context, "fcf_margin") == ("income-2025", "cashflow-2025")
    assert metric_sources(context, "gross_margin") == ("income-2025",)
    assert metric_sources(context, "operating_margin") == ("income-2025",)
    assert metric_sources(context, "ebitda") == ("income-2025",)
    assert metric_sources(context, "net_debt") == ("balance-2025",)
    assert metric_sources(context, "net_debt_to_ebitda") == (
        "balance-2025",
        "income-2025",
    )
    assert metric_sources(context, "roe") == ("income-2025", "balance-2025")
    assert metric_sources(context, "pe_ratio") == ("income-2025", "market")
    assert metric_sources(context, "fcf_yield") == ("cashflow-2025", "market")
    assert metric_sources(context, "ev_to_ebitda") == (
        "income-2025",
        "balance-2025",
        "market",
    )
    assert "roic" not in {item.metric for item in context.metrics}


def test_builder_omits_missing_metrics_and_market_metrics_without_snapshot() -> None:
    financials = (
        make_financials(
            2025, operating_cash_flow=None, gross_profit=None
        ),
    )
    metrics = make_metrics(financials, None)

    context = build_financial_risk_context(metrics, financials, None)

    names = {item.metric for item in context.metrics}
    assert "fcf" not in names
    assert "gross_margin" not in names
    assert "pe_ratio" not in names
    assert "fcf_yield" not in names
    assert "ev_to_ebitda" not in names


def test_builder_deduplicates_sources_in_stable_encounter_order() -> None:
    financials = (make_financials(2024), make_financials(2025))
    market_snapshot = make_market_snapshot()

    context = build_financial_risk_context(
        make_metrics(financials, market_snapshot), financials, market_snapshot
    )

    assert [source.source_id for source in context.sources] == [
        "income-2024",
        "income-2025",
        "balance-2024",
        "balance-2025",
        "cashflow-2025",
        "market",
    ]


def test_context_rejects_metric_sources_not_in_its_sources() -> None:
    with pytest.raises(ValueError, match="unknown source IDs: missing"):
        FinancialRiskContext(
            metrics=(
                FinancialRiskMetric(
                    metric="fcf",
                    value=Decimal("20"),
                    unit="currency",
                    source_ids=("missing",),
                ),
            ),
            sources=(make_source("cashflow"),),
        )


def test_builder_rejects_metrics_for_a_different_latest_period() -> None:
    financials = (make_financials(2025),)
    market_snapshot = make_market_snapshot()
    metrics = make_metrics(financials, market_snapshot).model_copy(
        update={"latest_period_end": date(2024, 12, 31)}
    )

    with pytest.raises(ValueError, match="latest_period_end"):
        build_financial_risk_context(metrics, financials, market_snapshot)


def test_builder_rejects_history_derived_cagr_mismatch() -> None:
    financials = (make_financials(2024), make_financials(2025))
    market_snapshot = make_market_snapshot()
    metrics = make_metrics(financials, market_snapshot).model_copy(
        update={"revenue_cagr": Decimal("0.1")}
    )

    with pytest.raises(ValueError, match="revenue_cagr"):
        build_financial_risk_context(metrics, financials, market_snapshot)


def test_builder_rejects_reporting_currency_mismatch() -> None:
    financials = (make_financials(2025),)
    market_snapshot = make_market_snapshot()
    metrics = make_metrics(financials, market_snapshot).model_copy(
        update={"reporting_currency": "USD"}
    )

    with pytest.raises(ValueError, match="reporting_currency"):
        build_financial_risk_context(metrics, financials, market_snapshot)


def test_builder_rejects_market_metric_from_incompatible_snapshot() -> None:
    financials = (make_financials(2025),)
    compatible_snapshot = make_market_snapshot()
    metrics = make_metrics(financials, compatible_snapshot)

    with pytest.raises(ValueError, match="pe_ratio"):
        build_financial_risk_context(
            metrics, financials, make_market_snapshot("USD")
        )


def test_context_rejects_conflicting_references_for_one_source_id() -> None:
    source = make_source("same-source")
    conflicting_source = source.model_copy(update={"provider": "other_provider"})

    with pytest.raises(ValueError, match="conflicting source references"):
        FinancialRiskContext(
            metrics=(
                FinancialRiskMetric(
                    metric="fcf",
                    value=Decimal("20"),
                    unit="currency",
                    source_ids=("same-source",),
                ),
            ),
            sources=(source, conflicting_source),
        )
