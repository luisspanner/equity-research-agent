"""Pure normalization of the Alpha Vantage V0 payload contract."""

import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation

from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.financials import (
    AnnualFinancials,
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriod,
    IncomeStatement,
    MarketSnapshot,
)
from equity_research_agent.models.provenance import SourceReference


class AlphaVantageNormalizationError(ValueError):
    """Raised when an Alpha Vantage response cannot satisfy the V0 contract."""


_PROVIDER_ERROR_KEYS = frozenset({"Information", "Note", "Error", "Error Message"})
_CREDENTIAL_QUERY_PARAMETER = re.compile(
    r"(?i)\b(apikey|api_key|token)=([^&\s]+)"
)
_OVERVIEW_ALLOWLIST = frozenset(
    {
        "Symbol",
        "AssetType",
        "Name",
        "Description",
        "CIK",
        "Exchange",
        "Currency",
        "Country",
        "Sector",
        "Industry",
        "FiscalYearEnd",
        "LatestQuarter",
        "MarketCapitalization",
        "SharesOutstanding",
    }
)
_MISSING_VALUES = frozenset({"", "None"})


def normalize_company_profile(
    overview: Mapping[str, object], source: SourceReference
) -> CompanyProfile:
    """Normalize the V0 overview allowlist into a company profile."""

    _reject_provider_error(overview)
    allowed_overview = {
        field: overview[field] for field in _OVERVIEW_ALLOWLIST if field in overview
    }

    security = SecurityIdentity(
        input_symbol=_required_text(allowed_overview, "Symbol"),
        canonical_symbol=_required_text(allowed_overview, "Symbol"),
        exchange=_required_text(allowed_overview, "Exchange"),
        listing_currency=_required_text(allowed_overview, "Currency"),
        cik=_optional_text(allowed_overview, "CIK"),
    )
    return CompanyProfile(
        security=security,
        name=_required_text(allowed_overview, "Name"),
        description=_required_text(allowed_overview, "Description"),
        country=_optional_text(allowed_overview, "Country"),
        sector=_optional_text(allowed_overview, "Sector"),
        industry=_optional_text(allowed_overview, "Industry"),
        sources=(source,),
    )


def normalize_annual_financials(
    income_payload: Mapping[str, object],
    balance_payload: Mapping[str, object],
    cash_flow_payload: Mapping[str, object],
    earnings_payload: Mapping[str, object],
    sources_by_endpoint: Mapping[str, SourceReference],
) -> tuple[AnnualFinancials, ...]:
    """Join compatible annual Alpha Vantage statements by fiscal period end."""

    income_records = _records_by_period(income_payload, "annualReports")
    balance_records = _records_by_period(balance_payload, "annualReports")
    cash_flow_records = _records_by_period(cash_flow_payload, "annualReports")
    earnings_records = _records_by_period(earnings_payload, "annualEarnings")

    required_sources = {
        "income_statement": _required_source(sources_by_endpoint, "income_statement"),
        "balance_sheet": _required_source(sources_by_endpoint, "balance_sheet"),
        "cash_flow": _required_source(sources_by_endpoint, "cash_flow"),
        "earnings": _required_source(sources_by_endpoint, "earnings"),
    }
    common_periods = (
        income_records.keys()
        & balance_records.keys()
        & cash_flow_records.keys()
        & earnings_records.keys()
    )
    if not common_periods:
        raise AlphaVantageNormalizationError(
            "annual statements and earnings have no shared fiscalDateEnding"
        )

    financials: list[AnnualFinancials] = []
    for period_end in sorted(common_periods, reverse=True):
        if period_end.month != 12 or period_end.day != 31:
            raise AlphaVantageNormalizationError(
                "V0 only supports fiscal periods ending on December 31"
            )

        income_record = income_records[period_end]
        balance_record = balance_records[period_end]
        cash_flow_record = cash_flow_records[period_end]
        reporting_currency = _shared_reporting_currency(
            income_record, balance_record, cash_flow_record, period_end
        )
        period = FiscalPeriod(
            start_date=date(period_end.year, 1, 1),
            end_date=period_end,
            fiscal_year=period_end.year,
        )
        financials.append(
            AnnualFinancials(
                period=period,
                income_statement=IncomeStatement(
                    period=period,
                    reporting_currency=reporting_currency,
                    sources=(
                        required_sources["income_statement"],
                        required_sources["earnings"],
                    ),
                    revenue=_decimal_value(income_record, "totalRevenue"),
                    gross_profit=_decimal_value(income_record, "grossProfit"),
                    operating_income=_decimal_value(
                        income_record, "operatingIncome"
                    ),
                    income_before_tax=_decimal_value(
                        income_record, "incomeBeforeTax"
                    ),
                    income_tax_expense=_decimal_value(
                        income_record, "incomeTaxExpense"
                    ),
                    net_income=_decimal_value(income_record, "netIncome"),
                    depreciation_and_amortization=_decimal_value(
                        income_record, "depreciationAndAmortization"
                    ),
                    reported_eps=_decimal_value(
                        earnings_records[period_end], "reportedEPS"
                    ),
                ),
                balance_sheet=BalanceSheet(
                    period=period,
                    reporting_currency=reporting_currency,
                    sources=(required_sources["balance_sheet"],),
                    cash_and_cash_equivalents=_decimal_value(
                        balance_record, "cashAndCashEquivalentsAtCarryingValue"
                    ),
                    total_debt=_decimal_value(
                        balance_record, "shortLongTermDebtTotal"
                    ),
                    total_shareholder_equity=_decimal_value(
                        balance_record, "totalShareholderEquity"
                    ),
                    shares_outstanding=_integer_value(
                        balance_record, "commonStockSharesOutstanding"
                    ),
                ),
                cash_flow_statement=CashFlowStatement(
                    period=period,
                    reporting_currency=reporting_currency,
                    sources=(required_sources["cash_flow"],),
                    operating_cash_flow=_decimal_value(
                        cash_flow_record, "operatingCashflow"
                    ),
                    capital_expenditure=_decimal_value(
                        cash_flow_record, "capitalExpenditures"
                    ),
                ),
            )
        )

    return tuple(financials)


def normalize_market_snapshot(
    overview: Mapping[str, object],
    daily_payload: Mapping[str, object],
    security: SecurityIdentity,
    overview_source: SourceReference,
    daily_source: SourceReference,
) -> MarketSnapshot:
    """Normalize the latest daily close and overview market capitalization."""

    _reject_provider_error(overview)
    _reject_provider_error(daily_payload)

    overview_symbol = _required_text(overview, "Symbol")
    if overview_symbol != security.canonical_symbol:
        raise AlphaVantageNormalizationError(
            "overview payload symbol does not match the requested security"
        )

    metadata = _required_mapping(daily_payload, "Meta Data")
    daily_symbol = _required_text(metadata, "2. Symbol")
    if daily_symbol != security.canonical_symbol:
        raise AlphaVantageNormalizationError(
            "daily payload symbol does not match the requested security"
        )

    price_as_of = _date_value(metadata, "3. Last Refreshed")
    daily_series = _required_mapping(daily_payload, "Time Series (Daily)")
    observation = daily_series.get(price_as_of.isoformat())
    if not isinstance(observation, Mapping):
        raise AlphaVantageNormalizationError(
            "daily payload has no observation for its last-refreshed date"
        )

    market_cap = _decimal_value(overview, "MarketCapitalization")
    return MarketSnapshot(
        security=security,
        price=_decimal_value_required(observation, "4. close"),
        price_currency=security.listing_currency,
        price_as_of=price_as_of,
        market_cap=market_cap,
        sources=(overview_source, daily_source),
    )


def _reject_provider_error(payload: Mapping[str, object]) -> None:
    if error_keys := _PROVIDER_ERROR_KEYS.intersection(payload):
        details = "; ".join(
            f"{key}: {_safe_provider_message(payload[key])}"
            for key in sorted(error_keys)
        )
        raise AlphaVantageNormalizationError(
            f"Alpha Vantage response contains: {details}"
        )


def _safe_provider_message(value: object) -> str:
    """Retain provider diagnostics without exposing credential-like query values."""

    if not isinstance(value, str):
        return "non-text provider message"
    return _CREDENTIAL_QUERY_PARAMETER.sub(r"\1=<redacted>", value)


def _records_by_period(
    payload: Mapping[str, object], array_field: str
) -> dict[date, Mapping[str, object]]:
    _reject_provider_error(payload)
    raw_records = payload.get(array_field)
    if not isinstance(raw_records, list):
        raise AlphaVantageNormalizationError(
            f"payload field {array_field} must be a list"
        )

    records: dict[date, Mapping[str, object]] = {}
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise AlphaVantageNormalizationError(
                f"payload field {array_field} contains a non-object record"
            )
        period_end = _date_value(raw_record, "fiscalDateEnding")
        if period_end in records:
            raise AlphaVantageNormalizationError(
                f"payload field {array_field} has duplicate fiscalDateEnding"
            )
        records[period_end] = raw_record
    return records


def _shared_reporting_currency(
    income_record: Mapping[str, object],
    balance_record: Mapping[str, object],
    cash_flow_record: Mapping[str, object],
    period_end: date,
) -> str:
    currencies = {
        _required_text(income_record, "reportedCurrency"),
        _required_text(balance_record, "reportedCurrency"),
        _required_text(cash_flow_record, "reportedCurrency"),
    }
    if len(currencies) != 1:
        raise AlphaVantageNormalizationError(
            f"annual statements use incompatible reported currencies for {period_end}"
        )
    return currencies.pop()


def _required_source(
    sources_by_endpoint: Mapping[str, SourceReference], endpoint: str
) -> SourceReference:
    try:
        return sources_by_endpoint[endpoint]
    except KeyError as error:
        raise AlphaVantageNormalizationError(
            f"missing source reference for {endpoint}"
        ) from error


def _required_mapping(
    payload: Mapping[str, object], field: str
) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise AlphaVantageNormalizationError(f"payload field {field} must be an object")
    return value


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = _optional_text(payload, field)
    if value is None:
        raise AlphaVantageNormalizationError(f"payload field {field} is required")
    return value


def _optional_text(payload: Mapping[str, object], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AlphaVantageNormalizationError(f"payload field {field} must be a string")
    normalized = value.strip()
    return None if normalized in _MISSING_VALUES else normalized


def _date_value(payload: Mapping[str, object], field: str) -> date:
    value = _required_text(payload, field)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise AlphaVantageNormalizationError(
            f"payload field {field} must be an ISO date"
        ) from error


def _decimal_value(payload: Mapping[str, object], field: str) -> Decimal | None:
    value = _optional_text(payload, field)
    if value is None:
        return None
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as error:
        raise AlphaVantageNormalizationError(
            f"payload field {field} must be a valid decimal"
        ) from error
    if not decimal_value.is_finite():
        raise AlphaVantageNormalizationError(
            f"payload field {field} must be finite"
        )
    return decimal_value


def _decimal_value_required(payload: Mapping[str, object], field: str) -> Decimal:
    value = _decimal_value(payload, field)
    if value is None:
        raise AlphaVantageNormalizationError(f"payload field {field} is required")
    return value


def _integer_value(payload: Mapping[str, object], field: str) -> int | None:
    value = _decimal_value(payload, field)
    if value is None:
        return None
    if value != value.to_integral_value():
        raise AlphaVantageNormalizationError(
            f"payload field {field} must be an integer"
        )
    return int(value)
