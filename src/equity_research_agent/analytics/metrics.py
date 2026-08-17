"""Assembly of deterministic metrics from normalized annual financials."""

from collections.abc import Callable, Sequence
from decimal import Decimal, localcontext
from typing import Literal

from equity_research_agent.analytics.capital_efficiency import (
    calculate_roe,
    calculate_roic,
)
from equity_research_agent.analytics.growth import (
    calculate_eps_cagr,
    calculate_revenue_cagr,
    calculate_share_count_cagr,
)
from equity_research_agent.analytics.leverage import (
    calculate_ebitda,
    calculate_net_debt,
    calculate_net_debt_to_ebitda,
)
from equity_research_agent.analytics.profitability import (
    calculate_fcf_margin,
    calculate_free_cash_flow,
    calculate_gross_margin,
    calculate_operating_margin,
)
from equity_research_agent.models.financials import AnnualFinancials, MarketSnapshot
from equity_research_agent.models.metrics import FinancialMetrics, MetricUnavailability

_CALCULATION_PRECISION = 50


def assemble_financial_metrics(
    financials: Sequence[AnnualFinancials],
    market_snapshot: MarketSnapshot | None = None,
    *,
    nopat: Decimal | None = None,
    invested_capital: Decimal | None = None,
) -> FinancialMetrics:
    """Assemble available deterministic metrics without inventing missing inputs."""

    if not financials:
        raise ValueError("at least one annual financial period is required")

    period_end_dates = [item.period.end_date for item in financials]
    if len(set(period_end_dates)) != len(period_end_dates):
        raise ValueError("annual financial periods must have distinct end dates")

    latest = max(financials, key=lambda item: item.period.end_date)
    income = latest.income_statement
    balance_sheet = latest.balance_sheet
    cash_flow = latest.cash_flow_statement

    fcf = _when_all_present(
        (cash_flow.operating_cash_flow, cash_flow.capital_expenditure),
        calculate_free_cash_flow,
    )
    ebitda = _when_all_present(
        (income.operating_income, income.depreciation_and_amortization),
        calculate_ebitda,
    )
    net_debt = _when_all_present(
        (balance_sheet.total_debt, balance_sheet.cash_and_cash_equivalents),
        calculate_net_debt,
    )
    market_metrics = _calculate_market_metrics(
        market_snapshot,
        income.reporting_currency,
        income.net_income,
        fcf,
        net_debt,
        ebitda,
    )

    return FinancialMetrics(
        latest_period_end=latest.period.end_date,
        reporting_currency=income.reporting_currency,
        revenue_cagr=_calculate_series_metric(
            financials,
            lambda item: item.income_statement.revenue,
            calculate_revenue_cagr,
        ),
        eps_cagr=_calculate_series_metric(
            financials,
            lambda item: item.income_statement.reported_eps,
            calculate_eps_cagr,
        ),
        share_count_cagr=_calculate_series_metric(
            financials,
            lambda item: item.balance_sheet.shares_outstanding,
            calculate_share_count_cagr,
        ),
        fcf=fcf,
        fcf_margin=_when_all_present((fcf, income.revenue), calculate_fcf_margin),
        gross_margin=_when_all_present(
            (income.gross_profit, income.revenue), calculate_gross_margin
        ),
        operating_margin=_when_all_present(
            (income.operating_income, income.revenue), calculate_operating_margin
        ),
        ebitda=ebitda,
        net_debt=net_debt,
        net_debt_to_ebitda=_when_positive(
            (net_debt, ebitda), calculate_net_debt_to_ebitda
        ),
        roe=_when_all_present(
            (income.net_income, balance_sheet.total_shareholder_equity), calculate_roe
        ),
        roic=_when_all_present((nopat, invested_capital), calculate_roic),
        pe_ratio=market_metrics.pe_ratio,
        fcf_yield=market_metrics.fcf_yield,
        ev_to_ebitda=market_metrics.ev_to_ebitda,
        market_metric_unavailabilities=market_metrics.unavailabilities,
    )


def _calculate_series_metric(
    financials: Sequence[AnnualFinancials],
    value_for: Callable[[AnnualFinancials], Decimal | int | None],
    calculator: Callable[[Sequence[AnnualFinancials]], Decimal],
) -> Decimal | None:
    """Calculate a CAGR only when every required annual value is available."""

    if len(financials) < 2 or any(value_for(item) is None for item in financials):
        return None
    return calculator(financials)


def _when_all_present(
    values: tuple[Decimal | None, ...],
    calculator: Callable[..., Decimal],
) -> Decimal | None:
    """Run a metric calculation only when its inputs are explicitly available."""

    if any(value is None for value in values):
        return None
    return calculator(*values)


def _when_positive(
    values: tuple[Decimal | None, ...],
    calculator: Callable[..., Decimal],
) -> Decimal | None:
    """Run a ratio only when all inputs exist and its denominator is positive."""

    if any(value is None for value in values):
        return None
    denominator = values[-1]
    assert denominator is not None
    if denominator <= 0:
        return None
    return calculator(*values)


class _MarketMetrics:
    """Internal result of evaluating market-metric input availability."""

    def __init__(
        self,
        *,
        pe_ratio: Decimal | None,
        fcf_yield: Decimal | None,
        ev_to_ebitda: Decimal | None,
        unavailabilities: tuple[MetricUnavailability, ...],
    ) -> None:
        self.pe_ratio = pe_ratio
        self.fcf_yield = fcf_yield
        self.ev_to_ebitda = ev_to_ebitda
        self.unavailabilities = unavailabilities


def _calculate_market_metrics(
    market_snapshot: MarketSnapshot | None,
    reporting_currency: str,
    net_income: Decimal | None,
    fcf: Decimal | None,
    net_debt: Decimal | None,
    ebitda: Decimal | None,
) -> _MarketMetrics:
    """Calculate market metrics only from currency-compatible market capitalisation."""

    if market_snapshot is None:
        return _unavailable_market_metrics("no market snapshot is available")

    if market_snapshot.price_currency != reporting_currency:
        return _unavailable_market_metrics(
            "market price currency "
            f"{market_snapshot.price_currency} does not match financial reporting "
            f"currency {reporting_currency}"
        )

    if market_snapshot.market_cap is None:
        return _unavailable_market_metrics("market capitalization is unavailable")

    market_cap = market_snapshot.market_cap
    unavailabilities: list[MetricUnavailability] = []

    pe_ratio = _calculate_pe_ratio(market_cap, net_income, unavailabilities)
    fcf_yield = _calculate_fcf_yield(market_cap, fcf, unavailabilities)
    ev_to_ebitda = _calculate_ev_to_ebitda(
        market_cap, net_debt, ebitda, unavailabilities
    )
    return _MarketMetrics(
        pe_ratio=pe_ratio,
        fcf_yield=fcf_yield,
        ev_to_ebitda=ev_to_ebitda,
        unavailabilities=tuple(unavailabilities),
    )


def _calculate_pe_ratio(
    market_cap: Decimal,
    net_income: Decimal | None,
    unavailabilities: list[MetricUnavailability],
) -> Decimal | None:
    """Calculate P/E only for a positive latest-period net income."""

    if net_income is None:
        _add_unavailability(unavailabilities, "pe_ratio", "net income is unavailable")
        return None
    if net_income <= 0:
        _add_unavailability(unavailabilities, "pe_ratio", "net income must be positive")
        return None
    return _divide(market_cap, net_income)


def _calculate_fcf_yield(
    market_cap: Decimal,
    fcf: Decimal | None,
    unavailabilities: list[MetricUnavailability],
) -> Decimal | None:
    """Calculate FCF yield when latest free cash flow is available."""

    if fcf is None:
        _add_unavailability(
            unavailabilities, "fcf_yield", "free cash flow is unavailable"
        )
        return None
    return _divide(fcf, market_cap)


def _calculate_ev_to_ebitda(
    market_cap: Decimal,
    net_debt: Decimal | None,
    ebitda: Decimal | None,
    unavailabilities: list[MetricUnavailability],
) -> Decimal | None:
    """Calculate EV/EBITDA only when EBITDA is positive and all inputs exist."""

    if net_debt is None:
        _add_unavailability(
            unavailabilities, "ev_to_ebitda", "net debt is unavailable"
        )
        return None
    if ebitda is None:
        _add_unavailability(unavailabilities, "ev_to_ebitda", "EBITDA is unavailable")
        return None
    if ebitda <= 0:
        _add_unavailability(unavailabilities, "ev_to_ebitda", "EBITDA must be positive")
        return None
    return _divide(market_cap + net_debt, ebitda)


def _unavailable_market_metrics(reason: str) -> _MarketMetrics:
    """Mark all market metrics unavailable for a shared prerequisite failure."""

    market_metrics: tuple[
        Literal["pe_ratio", "fcf_yield", "ev_to_ebitda"], ...
    ] = ("pe_ratio", "fcf_yield", "ev_to_ebitda")
    return _MarketMetrics(
        pe_ratio=None,
        fcf_yield=None,
        ev_to_ebitda=None,
        unavailabilities=tuple(
            MetricUnavailability(metric=metric, reason=reason)
            for metric in market_metrics
        ),
    )


def _add_unavailability(
    unavailabilities: list[MetricUnavailability],
    metric: Literal["pe_ratio", "fcf_yield", "ev_to_ebitda"],
    reason: str,
) -> None:
    """Append a typed explanation for one unavailable market metric."""

    unavailabilities.append(MetricUnavailability(metric=metric, reason=reason))


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Divide with local precision after callers have validated denominators."""

    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        return numerator / denominator
