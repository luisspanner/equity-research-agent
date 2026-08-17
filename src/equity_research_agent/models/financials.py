"""Normalized annual financial-statement and market-data domain models."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from equity_research_agent.models.common import (
    CurrencyCode,
    DomainModel,
    NonEmptyString,
)
from equity_research_agent.models.company import SecurityIdentity
from equity_research_agent.models.provenance import SourceReference


class FiscalPeriod(DomainModel):
    """One completed annual reporting period."""

    period_type: Literal["annual"] = "annual"
    start_date: date
    end_date: date
    fiscal_year: int
    accounting_standard: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "FiscalPeriod":
        """Reject reporting periods that end before they start."""

        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")

        if self.fiscal_year not in {self.start_date.year, self.end_date.year}:
            raise ValueError("fiscal_year must match the start or end year")

        return self


class FinancialStatement(DomainModel):
    """Fields shared by normalized annual financial statements."""

    period: FiscalPeriod
    reporting_currency: CurrencyCode
    sources: tuple[SourceReference, ...] = Field(min_length=1)


class IncomeStatement(FinancialStatement):
    """Normalized annual income-statement values."""

    revenue: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_income: Decimal | None = None
    income_before_tax: Decimal | None = None
    income_tax_expense: Decimal | None = None
    net_income: Decimal | None = None
    depreciation_and_amortization: Decimal | None = None
    reported_eps: Decimal | None = None


class BalanceSheet(FinancialStatement):
    """Normalized annual balance-sheet values."""

    cash_and_cash_equivalents: Decimal | None = None
    total_debt: Decimal | None = None
    total_shareholder_equity: Decimal | None = None
    shares_outstanding: int | None = Field(default=None, gt=0)


class CashFlowStatement(FinancialStatement):
    """Normalized annual cash-flow values with CapEx as a positive outflow."""

    operating_cash_flow: Decimal | None = None
    capital_expenditure: Decimal | None = Field(default=None, ge=0)


class AnnualFinancials(DomainModel):
    """Three compatible annual statements for one fiscal period."""

    period: FiscalPeriod
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow_statement: CashFlowStatement

    @model_validator(mode="after")
    def validate_statement_compatibility(self) -> "AnnualFinancials":
        """Prevent calculations from combining incompatible statements."""

        statements = (
            self.income_statement,
            self.balance_sheet,
            self.cash_flow_statement,
        )
        if any(statement.period != self.period for statement in statements):
            raise ValueError("all statements must match the annual financial period")

        reporting_currencies = {
            statement.reporting_currency for statement in statements
        }
        if len(reporting_currencies) != 1:
            raise ValueError("all statements must use the same reporting currency")

        return self


class MarketSnapshot(DomainModel):
    """A sourced end-of-day price and optional market capitalization."""

    security: SecurityIdentity
    price: Decimal = Field(gt=0)
    price_currency: CurrencyCode
    price_as_of: date
    market_cap: Decimal | None = Field(default=None, gt=0)
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_listing_currency(self) -> "MarketSnapshot":
        """Keep the market price in the security's listing currency."""

        if self.price_currency != self.security.listing_currency:
            raise ValueError("price_currency must match the security listing currency")

        return self
