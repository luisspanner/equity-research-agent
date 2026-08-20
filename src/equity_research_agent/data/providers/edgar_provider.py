"""Synchronous SEC EDGAR implementation of the filing-discovery contract."""

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import HttpUrl

from equity_research_agent.data.providers.edgar import (
    ARCHIVES_BASE_URL,
    normalize_cik_from_ticker,
    normalize_latest_annual_report,
)
from equity_research_agent.models.filings import FilingReference, RetrievedFiling
from equity_research_agent.models.provenance import SourceReference

# ASML's 2025 Form 20-F is roughly 24 MB of inline XBRL, so the limit exists to
# bound a runaway response rather than to reject a large annual report.
DEFAULT_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024


class EdgarProviderError(RuntimeError):
    """Raised when an EDGAR HTTP response cannot be read safely."""


class EdgarFilingProvider:
    """Discover and retrieve annual-report filings from SEC EDGAR.

    Retrieved document text is untrusted third-party prose. This provider only
    fetches and decodes it; interpreting, parsing, or exposing it to a model is
    the responsibility of later, explicitly bounded steps.
    """

    _BASE_URL = "https://data.sec.gov/submissions"
    _COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    _MINIMUM_REQUEST_INTERVAL_SECONDS = 0.15
    _ALLOWED_DOCUMENT_CONTENT_TYPES = frozenset({"text/html", "text/plain"})

    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float = 10.0,
        max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    ) -> None:
        """Create a provider with the contact user agent EDGAR requires."""

        if not user_agent.strip():
            raise ValueError("user_agent must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_document_bytes <= 0:
            raise ValueError("max_document_bytes must be positive")

        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._max_document_bytes = max_document_bytes
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

    def resolve_cik(self, ticker: str) -> str:
        """Return the CIK for a listed ticker using SEC's company tickers file.

        Matching is exact and case-insensitive. Unlike a filing, the resolved
        CIK is not itself a citable fact, so this returns a plain string rather
        than a sourced domain object.
        """

        self._wait_until_request_allowed()
        request = Request(
            self._COMPANY_TICKERS_URL,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read()
            payload = json.loads(response_body.decode("utf-8"))
        except (HTTPError, URLError, UnicodeDecodeError, JSONDecodeError):
            raise EdgarProviderError(
                "could not retrieve a valid EDGAR company tickers response"
            ) from None

        return normalize_cik_from_ticker(payload, ticker)

    def get_document(self, filing: FilingReference) -> RetrievedFiling:
        """Return the filing's primary document as sourced, untrusted text."""

        document_url = str(filing.document_url)
        if not document_url.startswith(f"{ARCHIVES_BASE_URL}/"):
            raise EdgarProviderError(
                "filing document URL is outside the EDGAR archives"
            )

        self._wait_until_request_allowed()
        request = Request(
            document_url,
            headers={"User-Agent": self._user_agent, "Accept": "text/html, text/plain"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                declared_content_type = response.headers.get("Content-Type", "")
                body: bytes = response.read(self._max_document_bytes + 1)
        except (HTTPError, URLError):
            raise EdgarProviderError(
                "could not retrieve the EDGAR filing document"
            ) from None

        if len(body) > self._max_document_bytes:
            raise EdgarProviderError(
                "filing document exceeds the maximum retrievable size"
            )
        if not body:
            raise EdgarProviderError("filing document is empty")

        content_type, charset = _parse_content_type(declared_content_type)
        if content_type not in self._ALLOWED_DOCUMENT_CONTENT_TYPES:
            raise EdgarProviderError("filing document is not a supported text type")

        try:
            document_text = body.decode(charset)
        except (UnicodeDecodeError, LookupError):
            raise EdgarProviderError(
                "filing document could not be decoded as text"
            ) from None

        source = SourceReference(
            provider="sec_edgar",
            source_type="annual_report_document",
            source_id=filing.accession_number,
            url=filing.document_url,
            retrieved_at=datetime.now(timezone.utc),
            period_end=filing.period_end,
        )
        return RetrievedFiling(
            filing=filing,
            content_type=content_type,
            byte_size=len(body),
            untrusted_text=document_text,
            sources=(source,),
        )

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


def _parse_content_type(header_value: str) -> tuple[str, str]:
    """Split a Content-Type header into its media type and character set.

    A missing or unparseable header yields an empty media type, which no
    allowlist accepts, so an undeclared document is rejected rather than
    optimistically decoded.
    """

    parameters = [parameter.strip() for parameter in header_value.split(";")]
    media_type = parameters[0].lower()
    charset = "utf-8"
    for parameter in parameters[1:]:
        name, separator, value = parameter.partition("=")
        if separator and name.strip().lower() == "charset":
            charset = value.strip().strip('"').lower() or charset
    return media_type, charset


def _normalize_cik(cik: str) -> str:
    """Return the zero-padded ten-digit CIK the EDGAR submissions API requires."""

    normalized_cik = cik.strip().lstrip("0")
    if not normalized_cik.isdigit() or len(normalized_cik) > 10:
        raise ValueError("cik must be one to ten digits")
    return normalized_cik.zfill(10)
