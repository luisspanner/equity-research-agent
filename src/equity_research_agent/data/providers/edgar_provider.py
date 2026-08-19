"""Synchronous SEC EDGAR implementation of the filing-discovery contract."""

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import HttpUrl

from equity_research_agent.data.providers.edgar import normalize_latest_annual_report
from equity_research_agent.models.filings import FilingReference
from equity_research_agent.models.provenance import SourceReference


class EdgarProviderError(RuntimeError):
    """Raised when an EDGAR HTTP response cannot be read safely."""


class EdgarFilingProvider:
    """Discover annual-report filing metadata from the EDGAR submissions index.

    Only filing metadata is retrieved. Filing documents are not downloaded, so
    no untrusted document text enters the system through this provider.
    """

    _BASE_URL = "https://data.sec.gov/submissions"
    _MINIMUM_REQUEST_INTERVAL_SECONDS = 0.15

    def __init__(self, user_agent: str, *, timeout_seconds: float = 10.0) -> None:
        """Create a provider with the contact user agent EDGAR requires."""

        if not user_agent.strip():
            raise ValueError("user_agent must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._last_request_started_at: float | None = None

    def get_latest_annual_report(self, cik: str) -> FilingReference:
        """Return metadata for the issuer's most recent 10-K or 20-F."""

        padded_cik = _normalize_cik(cik)
        source_url = f"{self._BASE_URL}/CIK{padded_cik}.json"

        self._wait_until_request_allowed()
        request = Request(
            source_url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read()
            payload = json.loads(response_body.decode("utf-8"))
        except (HTTPError, URLError, UnicodeDecodeError, JSONDecodeError):
            raise EdgarProviderError(
                "could not retrieve a valid EDGAR submissions response"
            ) from None

        if not isinstance(payload, dict):
            raise EdgarProviderError("EDGAR submissions response must be an object")

        source = SourceReference(
            provider="sec_edgar",
            source_type="submissions_index",
            source_id=f"CIK{padded_cik}-submissions",
            url=HttpUrl(source_url),
            retrieved_at=datetime.now(timezone.utc),
        )
        return normalize_latest_annual_report(payload, source)

    def _wait_until_request_allowed(self) -> None:
        """Conservatively respect the EDGAR request-rate limit."""

        now = monotonic()
        if self._last_request_started_at is not None:
            elapsed = now - self._last_request_started_at
            remaining_interval = self._MINIMUM_REQUEST_INTERVAL_SECONDS - elapsed
            if remaining_interval > 0:
                sleep(remaining_interval)
                now = monotonic()
        self._last_request_started_at = now


def _normalize_cik(cik: str) -> str:
    """Return the zero-padded ten-digit CIK the EDGAR submissions API requires."""

    normalized_cik = cik.strip().lstrip("0")
    if not normalized_cik.isdigit() or len(normalized_cik) > 10:
        raise ValueError("cik must be one to ten digits")
    return normalized_cik.zfill(10)
