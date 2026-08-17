"""Synchronous Alpha Vantage implementation of the financial-data contract."""

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import HttpUrl

from equity_research_agent.data.providers.alpha_vantage import (
    normalize_annual_financials,
    normalize_company_profile,
    normalize_market_snapshot,
)
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financials import AnnualFinancials, MarketSnapshot
from equity_research_agent.models.provenance import SourceReference


class AlphaVantageProviderError(RuntimeError):
    """Raised when an Alpha Vantage HTTP response cannot be read safely."""


class AlphaVantageProvider:
    """Retrieve V0 research data from Alpha Vantage and normalize it."""

    _BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, *, timeout_seconds: float = 10.0) -> None:
        """Create a provider with an explicit API key and request timeout."""

        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def get_company_profile(self, ticker: str) -> CompanyProfile:
        """Return a normalized company profile for ``ticker``."""

        normalized_ticker = _normalize_ticker(ticker)
        overview, source = self._fetch("OVERVIEW", normalized_ticker)
        return normalize_company_profile(overview, source)

    def get_annual_financials(self, ticker: str) -> tuple[AnnualFinancials, ...]:
        """Return all compatible normalized annual financial statements."""

        normalized_ticker = _normalize_ticker(ticker)
        income_payload, income_source = self._fetch(
            "INCOME_STATEMENT", normalized_ticker
        )
        balance_payload, balance_source = self._fetch(
            "BALANCE_SHEET", normalized_ticker
        )
        cash_flow_payload, cash_flow_source = self._fetch(
            "CASH_FLOW", normalized_ticker
        )
        earnings_payload, earnings_source = self._fetch("EARNINGS", normalized_ticker)

        return normalize_annual_financials(
            income_payload,
            balance_payload,
            cash_flow_payload,
            earnings_payload,
            {
                "income_statement": income_source,
                "balance_sheet": balance_source,
                "cash_flow": cash_flow_source,
                "earnings": earnings_source,
            },
        )

    def get_market_snapshot(self, ticker: str) -> MarketSnapshot:
        """Return the latest normalized market snapshot for ``ticker``."""

        normalized_ticker = _normalize_ticker(ticker)
        overview, overview_source = self._fetch("OVERVIEW", normalized_ticker)
        profile = normalize_company_profile(overview, overview_source)
        daily_payload, daily_source = self._fetch(
            "TIME_SERIES_DAILY", normalized_ticker, outputsize="compact"
        )
        return normalize_market_snapshot(
            overview,
            daily_payload,
            profile.security,
            overview_source,
            daily_source,
        )

    def _fetch(
        self, function: str, ticker: str, **parameters: str
    ) -> tuple[Mapping[str, object], SourceReference]:
        request_parameters = {"function": function, "symbol": ticker, **parameters}
        request_query = urlencode({**request_parameters, "apikey": self._api_key})
        source_query = urlencode(request_parameters)

        try:
            with urlopen(
                f"{self._BASE_URL}?{request_query}", timeout=self._timeout_seconds
            ) as response:
                response_body = response.read()
            payload = json.loads(response_body.decode("utf-8"))
        except (HTTPError, URLError, UnicodeDecodeError, JSONDecodeError):
            raise AlphaVantageProviderError(
                "could not retrieve a valid Alpha Vantage response"
            ) from None

        if not isinstance(payload, dict):
            raise AlphaVantageProviderError("Alpha Vantage response must be an object")

        endpoint = function.lower()
        source = SourceReference(
            provider="alpha_vantage",
            source_type=endpoint,
            source_id=f"{ticker}-{endpoint}",
            url=HttpUrl(f"{self._BASE_URL}?{source_query}"),
            retrieved_at=datetime.now(timezone.utc),
        )
        return payload, source


def _normalize_ticker(ticker: str) -> str:
    """Return a nonblank ticker suitable for an Alpha Vantage request."""

    normalized_ticker = ticker.strip()
    if not normalized_ticker:
        raise ValueError("ticker must not be blank")
    return normalized_ticker
