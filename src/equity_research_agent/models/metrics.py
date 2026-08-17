"""Structured outputs of deterministic financial analysis."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from equity_research_agent.models.common import (
    CurrencyCode,
    DomainModel,
    NonEmptyString,
)


class MetricUnavailability(DomainModel):
    """A market metric deliberately withheld with its explicit reason."""

    metric: Literal["pe_ratio", "fcf_yield", "ev_to_ebitda"]
    reason: NonEmptyString


class FinancialMetrics(DomainModel):
    """Deterministic metrics for the latest annual reporting period."""

    latest_period_end: date
    reporting_currency: CurrencyCode
    revenue_cagr: Decimal | None = None
    eps_cagr: Decimal | None = None
    share_count_cagr: Decimal | None = None
    fcf: Decimal | None = None
    fcf_margin: Decimal | None = None
    gross_margin: Decimal | None = None
    operating_margin: Decimal | None = None
    ebitda: Decimal | None = None
    net_debt: Decimal | None = None
    net_debt_to_ebitda: Decimal | None = None
    roe: Decimal | None = None
    roic: Decimal | None = None
    pe_ratio: Decimal | None = None
    fcf_yield: Decimal | None = None
    ev_to_ebitda: Decimal | None = None
    market_metric_unavailabilities: tuple[MetricUnavailability, ...] = Field(
        default=()
    )
