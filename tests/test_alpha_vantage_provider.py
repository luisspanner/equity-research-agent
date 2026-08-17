"""Tests for the synchronous Alpha Vantage data provider."""

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from equity_research_agent.data.providers import FinancialDataProvider
from equity_research_agent.data.providers.alpha_vantage import (
    AlphaVantageNormalizationError,
)
from equity_research_agent.data.providers.alpha_vantage_provider import (
    AlphaVantageProvider,
    AlphaVantageProviderError,
)

FIXTURE_DIRECTORY = (
    Path(__file__).parent / "fixtures" / "providers" / "alpha_vantage" / "asml"
)

_FIXTURES_BY_FUNCTION = {
    "OVERVIEW": "overview.json",
    "INCOME_STATEMENT": "income_statement.json",
    "BALANCE_SHEET": "balance_sheet.json",
    "CASH_FLOW": "cash_flow.json",
    "EARNINGS": "earnings.json",
    "TIME_SERIES_DAILY": "time_series_daily.json",
}


class FakeResponse:
    """Minimal context-managed HTTP response for provider tests."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def recorded_urlopen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace urlopen with fixture responses and record outgoing request URLs."""

    request_urls: list[str] = []

    def fake_urlopen(url: str, *, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        request_urls.append(url)
        function = parse_qs(urlparse(url).query)["function"][0]
        fixture_name = _FIXTURES_BY_FUNCTION[function]
        return FakeResponse((FIXTURE_DIRECTORY / fixture_name).read_bytes())

    monkeypatch.setattr(
        "equity_research_agent.data.providers.alpha_vantage_provider.urlopen",
        fake_urlopen,
    )
    return request_urls


def _query_parameters(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def _assert_source_has_no_api_key(source_url: str) -> None:
    assert "apikey" not in _query_parameters(source_url)
    assert "test-key" not in source_url


def test_provider_conforms_to_financial_data_provider_protocol() -> None:
    assert isinstance(AlphaVantageProvider("test-key"), FinancialDataProvider)


def test_get_company_profile_fetches_and_normalizes_overview(
    recorded_urlopen: list[str],
) -> None:
    profile = AlphaVantageProvider("test-key").get_company_profile(" ASML ")

    assert profile.name == "ASML Holding NV ADR"
    assert profile.security.listing_currency == "USD"
    assert len(recorded_urlopen) == 1
    assert _query_parameters(recorded_urlopen[0]) == {
        "function": ["OVERVIEW"],
        "symbol": ["ASML"],
        "apikey": ["test-key"],
    }
    assert profile.sources[0].retrieved_at is not None
    _assert_source_has_no_api_key(str(profile.sources[0].url))


def test_get_annual_financials_fetches_all_required_endpoints(
    recorded_urlopen: list[str],
) -> None:
    financials = AlphaVantageProvider("test-key").get_annual_financials("ASML")

    assert len(financials) == 20
    assert financials[0].income_statement.revenue == 32667300000
    assert [
        _query_parameters(url)["function"][0] for url in recorded_urlopen
    ] == ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW", "EARNINGS"]
    assert all(
        _query_parameters(url)["apikey"] == ["test-key"]
        for url in recorded_urlopen
    )
    for statement in (
        financials[0].income_statement,
        financials[0].balance_sheet,
        financials[0].cash_flow_statement,
    ):
        for source in statement.sources:
            _assert_source_has_no_api_key(str(source.url))


def test_get_market_snapshot_fetches_overview_and_daily_data(
    recorded_urlopen: list[str],
) -> None:
    snapshot = AlphaVantageProvider("test-key").get_market_snapshot("ASML")

    assert snapshot.price_currency == "USD"
    assert str(snapshot.price) == "1844.0800"
    assert [
        _query_parameters(url)["function"][0] for url in recorded_urlopen
    ] == ["OVERVIEW", "TIME_SERIES_DAILY"]
    assert _query_parameters(recorded_urlopen[1]) == {
        "function": ["TIME_SERIES_DAILY"],
        "symbol": ["ASML"],
        "outputsize": ["compact"],
        "apikey": ["test-key"],
    }
    for source in snapshot.sources:
        _assert_source_has_no_api_key(str(source.url))


@pytest.mark.parametrize("api_key", ["", "   "])
def test_constructor_rejects_blank_api_key(api_key: str) -> None:
    with pytest.raises(ValueError, match="api_key"):
        AlphaVantageProvider(api_key)


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_constructor_rejects_nonpositive_timeout(timeout_seconds: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        AlphaVantageProvider("test-key", timeout_seconds=timeout_seconds)


@pytest.mark.parametrize("ticker", ["", "  "])
def test_public_methods_reject_blank_tickers(ticker: str) -> None:
    provider = AlphaVantageProvider("test-key")

    with pytest.raises(ValueError, match="ticker"):
        provider.get_company_profile(ticker)
    with pytest.raises(ValueError, match="ticker"):
        provider.get_annual_financials(ticker)
    with pytest.raises(ValueError, match="ticker"):
        provider.get_market_snapshot(ticker)


@pytest.mark.parametrize(
    "network_error",
    [
        HTTPError("https://example.test", 429, "rate limit", Message(), None),
        URLError("connection unavailable"),
    ],
)
def test_http_and_url_errors_are_safely_wrapped(
    monkeypatch: pytest.MonkeyPatch, network_error: Exception
) -> None:
    def failing_urlopen(url: str, *, timeout: float) -> FakeResponse:
        raise network_error

    monkeypatch.setattr(
        "equity_research_agent.data.providers.alpha_vantage_provider.urlopen",
        failing_urlopen,
    )

    with pytest.raises(AlphaVantageProviderError) as error:
        AlphaVantageProvider("test-key").get_company_profile("ASML")

    assert "test-key" not in str(error.value)
    assert "https://" not in str(error.value)


@pytest.mark.parametrize("body", [b"not json", b"[]"])
def test_invalid_or_nonobject_json_is_rejected_safely(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    def fake_urlopen(url: str, *, timeout: float) -> FakeResponse:
        return FakeResponse(body)

    monkeypatch.setattr(
        "equity_research_agent.data.providers.alpha_vantage_provider.urlopen",
        fake_urlopen,
    )

    with pytest.raises(AlphaVantageProviderError) as error:
        AlphaVantageProvider("test-key").get_company_profile("ASML")

    assert "test-key" not in str(error.value)


def test_provider_error_payload_is_validated_by_normalizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(url: str, *, timeout: float) -> FakeResponse:
        return FakeResponse(json.dumps({"Note": "rate limit"}).encode())

    monkeypatch.setattr(
        "equity_research_agent.data.providers.alpha_vantage_provider.urlopen",
        fake_urlopen,
    )

    with pytest.raises(AlphaVantageNormalizationError, match="Note"):
        AlphaVantageProvider("test-key").get_company_profile("ASML")
