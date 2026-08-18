"""Tests for the pure Alpha Vantage V0 JSON normalizer."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from equity_research_agent.data.providers.alpha_vantage import (
    AlphaVantageNormalizationError,
    normalize_annual_financials,
    normalize_company_profile,
    normalize_market_snapshot,
)
from equity_research_agent.models.company import SecurityIdentity
from equity_research_agent.models.financials import AnnualFinancials
from equity_research_agent.models.provenance import SourceReference

FIXTURE_DIRECTORY = (
    Path(__file__).parent / "fixtures" / "providers" / "alpha_vantage" / "asml"
)


def load_fixture(name: str) -> dict[str, object]:
    """Load an untouched raw Alpha Vantage fixture."""

    with (FIXTURE_DIRECTORY / name).open() as fixture_file:
        payload: object = json.load(fixture_file)
    assert isinstance(payload, dict)
    return payload


def make_source(endpoint: str) -> SourceReference:
    """Create non-sensitive fixture provenance for one Alpha Vantage endpoint."""

    query_shapes = {
        "overview": "function=OVERVIEW&symbol=ASML",
        "income_statement": "function=INCOME_STATEMENT&symbol=ASML",
        "balance_sheet": "function=BALANCE_SHEET&symbol=ASML",
        "cash_flow": "function=CASH_FLOW&symbol=ASML",
        "earnings": "function=EARNINGS&symbol=ASML",
        "time_series_daily": (
            "function=TIME_SERIES_DAILY&symbol=ASML&outputsize=compact"
        ),
    }
    return SourceReference(
        provider="alpha_vantage",
        source_type=endpoint,
        source_id=f"ASML-{endpoint}",
        url=f"https://www.alphavantage.co/query?{query_shapes[endpoint]}",
        captured_on=date(2026, 8, 17),
    )


def financial_sources() -> dict[str, SourceReference]:
    """Create provenance for each payload used in annual normalization."""

    return {
        "income_statement": make_source("income_statement"),
        "balance_sheet": make_source("balance_sheet"),
        "cash_flow": make_source("cash_flow"),
        "earnings": make_source("earnings"),
    }


def normalize_asml_annual_financials() -> tuple[AnnualFinancials, ...]:
    """Normalize the four captured annual ASML payloads."""

    return normalize_annual_financials(
        load_fixture("income_statement.json"),
        load_fixture("balance_sheet.json"),
        load_fixture("cash_flow.json"),
        load_fixture("earnings.json"),
        financial_sources(),
    )


def test_normalize_company_profile_preserves_us_adr_identity() -> None:
    profile = normalize_company_profile(
        load_fixture("overview.json"), make_source("overview")
    )

    assert profile.name == "ASML Holding NV ADR"
    assert profile.security == SecurityIdentity(
        input_symbol="ASML",
        canonical_symbol="ASML",
        exchange="NASDAQ",
        listing_currency="USD",
        cik="937966",
    )
    assert profile.security.reporting_currency is None
    assert profile.sources[0].captured_on == date(2026, 8, 17)


def test_normalize_annual_financials_joins_common_periods_and_values() -> None:
    financials = normalize_asml_annual_financials()

    assert [item.period.end_date for item in financials[:5]] == [
        date(2025, 12, 31),
        date(2024, 12, 31),
        date(2023, 12, 31),
        date(2022, 12, 31),
        date(2021, 12, 31),
    ]
    assert len(financials) == 20
    latest = financials[0]
    assert latest.income_statement.revenue == Decimal("32667300000")
    assert latest.income_statement.reported_eps == Decimal("24.73")
    assert latest.balance_sheet.cash_and_cash_equivalents == Decimal("12910503000")
    assert latest.balance_sheet.shares_outstanding == 388_900_000
    assert latest.cash_flow_statement.capital_expenditure == Decimal("1511494250")
    assert len(latest.income_statement.sources) == 2


def test_annual_normalization_excludes_anomalous_earnings_date_by_intersection(
) -> None:
    financials = normalize_asml_annual_financials()

    assert all(item.period.end_date != date(2026, 6, 30) for item in financials)


def test_annual_normalization_preserves_missing_sentinel_as_none() -> None:
    income_payload = load_fixture("income_statement.json")
    reports = income_payload["annualReports"]
    assert isinstance(reports, list)
    latest_report = reports[0]
    assert isinstance(latest_report, dict)
    latest_report["grossProfit"] = "None"

    financials = normalize_annual_financials(
        income_payload,
        load_fixture("balance_sheet.json"),
        load_fixture("cash_flow.json"),
        load_fixture("earnings.json"),
        financial_sources(),
    )

    assert financials[0].income_statement.gross_profit is None


def test_annual_normalization_is_independent_of_report_array_order() -> None:
    income_payload = load_fixture("income_statement.json")
    reports = income_payload["annualReports"]
    assert isinstance(reports, list)
    reports.reverse()

    financials = normalize_annual_financials(
        income_payload,
        load_fixture("balance_sheet.json"),
        load_fixture("cash_flow.json"),
        load_fixture("earnings.json"),
        financial_sources(),
    )

    assert financials[0].period.end_date == date(2025, 12, 31)


def test_annual_normalization_rejects_incompatible_reporting_currencies() -> None:
    balance_payload = load_fixture("balance_sheet.json")
    reports = balance_payload["annualReports"]
    assert isinstance(reports, list)
    latest_report = reports[0]
    assert isinstance(latest_report, dict)
    latest_report["reportedCurrency"] = "USD"

    with pytest.raises(AlphaVantageNormalizationError, match="incompatible"):
        normalize_annual_financials(
            load_fixture("income_statement.json"),
            balance_payload,
            load_fixture("cash_flow.json"),
            load_fixture("earnings.json"),
            financial_sources(),
        )


def test_annual_normalization_rejects_non_december_shared_period() -> None:
    income_payload = {"annualReports": [{"fiscalDateEnding": "2025-06-30"}]}
    balance_payload = {"annualReports": [{"fiscalDateEnding": "2025-06-30"}]}
    cash_flow_payload = {"annualReports": [{"fiscalDateEnding": "2025-06-30"}]}
    earnings_payload = {"annualEarnings": [{"fiscalDateEnding": "2025-06-30"}]}

    with pytest.raises(AlphaVantageNormalizationError, match="December 31"):
        normalize_annual_financials(
            income_payload,
            balance_payload,
            cash_flow_payload,
            earnings_payload,
            financial_sources(),
        )


@pytest.mark.parametrize("error_key", ["Information", "Note", "Error", "Error Message"])
def test_normalizer_rejects_alpha_vantage_error_bodies(error_key: str) -> None:
    with pytest.raises(AlphaVantageNormalizationError, match=error_key):
        normalize_company_profile(
            {error_key: "provider response"}, make_source("overview")
        )


def test_normalizer_preserves_alpha_vantage_provider_message() -> None:
    with pytest.raises(AlphaVantageNormalizationError, match="rate limit exceeded"):
        normalize_company_profile(
            {"Information": "rate limit exceeded"}, make_source("overview")
        )


def test_normalizer_redacts_credential_like_values_from_provider_message() -> None:
    with pytest.raises(AlphaVantageNormalizationError) as error:
        normalize_company_profile(
            {"Information": "Request failed for apikey=secret-value"},
            make_source("overview"),
        )

    assert "secret-value" not in str(error.value)
    assert "apikey=<redacted>" in str(error.value)


def test_annual_normalization_rejects_malformed_numerical_data() -> None:
    income_payload = load_fixture("income_statement.json")
    reports = income_payload["annualReports"]
    assert isinstance(reports, list)
    latest_report = reports[0]
    assert isinstance(latest_report, dict)
    latest_report["totalRevenue"] = "not-a-number"

    with pytest.raises(AlphaVantageNormalizationError, match="totalRevenue"):
        normalize_annual_financials(
            income_payload,
            load_fixture("balance_sheet.json"),
            load_fixture("cash_flow.json"),
            load_fixture("earnings.json"),
            financial_sources(),
        )


def test_normalize_market_snapshot_uses_daily_close_and_overview_market_cap() -> None:
    profile = normalize_company_profile(
        load_fixture("overview.json"), make_source("overview")
    )
    snapshot = normalize_market_snapshot(
        load_fixture("overview.json"),
        load_fixture("time_series_daily.json"),
        profile.security,
        make_source("overview"),
        make_source("time_series_daily"),
    )

    assert snapshot.price == Decimal("1844.0800")
    assert snapshot.price_currency == "USD"
    assert snapshot.price_as_of == date(2026, 8, 14)
    assert snapshot.market_cap == Decimal("708311122000")
    assert len(snapshot.sources) == 2


def test_market_normalization_rejects_symbol_mismatch() -> None:
    daily_payload = load_fixture("time_series_daily.json")
    metadata = daily_payload["Meta Data"]
    assert isinstance(metadata, dict)
    metadata["2. Symbol"] = "ASML.AMS"

    security = SecurityIdentity(
        input_symbol="ASML",
        canonical_symbol="ASML",
        exchange="NASDAQ",
        listing_currency="USD",
    )
    with pytest.raises(AlphaVantageNormalizationError, match="does not match"):
        normalize_market_snapshot(
            load_fixture("overview.json"),
            daily_payload,
            security,
            make_source("overview"),
            make_source("time_series_daily"),
        )


def test_market_normalization_rejects_overview_symbol_mismatch() -> None:
    overview = load_fixture("overview.json")
    overview["Symbol"] = "OTHER"
    security = SecurityIdentity(
        input_symbol="ASML",
        canonical_symbol="ASML",
        exchange="NASDAQ",
        listing_currency="USD",
    )

    with pytest.raises(AlphaVantageNormalizationError, match="overview payload symbol"):
        normalize_market_snapshot(
            overview,
            load_fixture("time_series_daily.json"),
            security,
            make_source("overview"),
            make_source("time_series_daily"),
        )
