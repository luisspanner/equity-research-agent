"""Preparation of provenance-preserving deterministic financial-risk inputs."""

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Literal

from equity_research_agent.analytics.metrics import assemble_financial_metrics
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
from equity_research_agent.models.financials import AnnualFinancials, MarketSnapshot
from equity_research_agent.models.metrics import FinancialMetrics
from equity_research_agent.models.provenance import SourceReference


def build_financial_risk_context(
    metrics: FinancialMetrics,
    financials: Sequence[AnnualFinancials],
    market_snapshot: MarketSnapshot | None,
) -> FinancialRiskContext:
    """Expose only deterministic metrics whose statement provenance is exact."""

    if not financials:
        raise ValueError("at least one annual financial period is required")

    latest = max(financials, key=lambda item: item.period.end_date)
    if metrics.latest_period_end != latest.period.end_date:
        raise ValueError(
            "metrics latest_period_end must match the latest annual period"
        )
    if metrics.reporting_currency != latest.income_statement.reporting_currency:
        raise ValueError(
            "metrics reporting_currency must match the latest income statement"
        )

    expected = assemble_financial_metrics(financials, market_snapshot)

    result: list[FinancialRiskMetric] = []
    income_sources = latest.income_statement.sources
    balance_sources = latest.balance_sheet.sources
    cash_flow_sources = latest.cash_flow_statement.sources

    _append_metric(
        result,
        "revenue_cagr",
        metrics.revenue_cagr,
        expected.revenue_cagr,
        "percentage",
        _statement_sources(financials, "income_statement"),
    )
    _append_metric(
        result,
        "eps_cagr",
        metrics.eps_cagr,
        expected.eps_cagr,
        "percentage",
        _statement_sources(financials, "income_statement"),
    )
    _append_metric(
        result,
        "share_count_cagr",
        metrics.share_count_cagr,
        expected.share_count_cagr,
        "percentage",
        _statement_sources(financials, "balance_sheet"),
    )
    _append_metric(
        result, "fcf", metrics.fcf, expected.fcf, "currency", cash_flow_sources
    )
    _append_metric(
        result,
        "fcf_margin",
        metrics.fcf_margin,
        expected.fcf_margin,
        "percentage",
        income_sources + cash_flow_sources,
    )
    _append_metric(
        result,
        "gross_margin",
        metrics.gross_margin,
        expected.gross_margin,
        "percentage",
        income_sources,
    )
    _append_metric(
        result,
        "operating_margin",
        metrics.operating_margin,
        expected.operating_margin,
        "percentage",
        income_sources,
    )
    _append_metric(
        result, "ebitda", metrics.ebitda, expected.ebitda, "currency", income_sources
    )
    _append_metric(
        result,
        "net_debt",
        metrics.net_debt,
        expected.net_debt,
        "currency",
        balance_sources,
    )
    _append_metric(
        result,
        "net_debt_to_ebitda",
        metrics.net_debt_to_ebitda,
        expected.net_debt_to_ebitda,
        "multiple",
        balance_sources + income_sources,
    )
    _append_metric(
        result,
        "roe",
        metrics.roe,
        expected.roe,
        "percentage",
        income_sources + balance_sources,
    )

    if market_snapshot is not None:
        market_sources = market_snapshot.sources
        _append_metric(
            result,
            "pe_ratio",
            metrics.pe_ratio,
            expected.pe_ratio,
            "multiple",
            income_sources + market_sources,
        )
        _append_metric(
            result,
            "fcf_yield",
            metrics.fcf_yield,
            expected.fcf_yield,
            "percentage",
            cash_flow_sources + market_sources,
        )
        _append_metric(
            result,
            "ev_to_ebitda",
            metrics.ev_to_ebitda,
            expected.ev_to_ebitda,
            "multiple",
            income_sources + balance_sources + market_sources,
        )

    if not result:
        raise ValueError("no source-traceable financial metrics are available")

    sources = _deduplicate_sources(
        source for metric in result for source in _sources_for_ids(
            metric.source_ids,
            financials,
            market_snapshot,
        )
    )
    return FinancialRiskContext(metrics=tuple(result), sources=sources)


def _append_metric(
    result: list[FinancialRiskMetric],
    metric: str,
    value: Decimal | None,
    expected_value: Decimal | None,
    unit: Literal["currency", "percentage", "multiple"],
    sources: tuple[SourceReference, ...],
) -> None:
    """Append a metric only when it has a deterministic value and sources."""

    if value is None:
        return
    if value != expected_value:
        raise ValueError(f"{metric} does not match the supplied financial inputs")
    result.append(
        FinancialRiskMetric(
            metric=metric,
            value=value,
            unit=unit,
            source_ids=tuple(
                source.source_id for source in _deduplicate_sources(sources)
            ),
        )
    )


def _statement_sources(
    financials: Sequence[AnnualFinancials],
    statement_name: Literal["income_statement", "balance_sheet"],
) -> tuple[SourceReference, ...]:
    """Collect one statement type's sources across all supplied annual periods."""

    return tuple(
        source
        for financial in financials
        for source in getattr(financial, statement_name).sources
    )


def _sources_for_ids(
    source_ids: tuple[str, ...],
    financials: Sequence[AnnualFinancials],
    market_snapshot: MarketSnapshot | None,
) -> tuple[SourceReference, ...]:
    """Resolve metric source IDs against supplied statement and market sources."""

    available_sources = tuple(
        source
        for financial in financials
        for statement_sources in (
            financial.income_statement.sources,
            financial.balance_sheet.sources,
            financial.cash_flow_statement.sources,
        )
        for source in statement_sources
    ) + (() if market_snapshot is None else market_snapshot.sources)
    return tuple(
        source
        for source_id in source_ids
        for source in available_sources
        if source.source_id == source_id
    )


def _deduplicate_sources(
    sources: Iterable[SourceReference],
) -> tuple[SourceReference, ...]:
    """Deduplicate source references by ID while preserving encounter order."""

    result: list[SourceReference] = []
    sources_by_id: dict[str, SourceReference] = {}
    for source in sources:
        existing_source = sources_by_id.get(source.source_id)
        if existing_source is not None and existing_source != source:
            raise ValueError(
                f"source ID {source.source_id} refers to conflicting source references"
            )
        if existing_source is None:
            result.append(source)
            sources_by_id[source.source_id] = source
    return tuple(result)
