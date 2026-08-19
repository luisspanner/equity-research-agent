"""Tests for retrieving an EDGAR filing's primary document as untrusted text."""

from datetime import date, datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from pydantic import HttpUrl

from equity_research_agent.data.providers.edgar_provider import (
    EdgarFilingProvider,
    EdgarProviderError,
)
from equity_research_agent.models.filings import FilingReference
from equity_research_agent.models.provenance import SourceReference

DOCUMENT_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "providers"
    / "sec_edgar"
    / "asml"
    / "annual_report.htm"
)

USER_AGENT = "Equity Research Agent research@example.test"

DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/937966/"
    "000093796626000008/asml-20251231.htm"
)


class FakeResponse:
    """Minimal context-managed HTTP response carrying declared headers."""

    def __init__(self, body: bytes, content_type: str | None) -> None:
        self._body = body
        self.headers = Message()
        if content_type is not None:
            self.headers["Content-Type"] = content_type

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        return None

    def read(self, size: int | None = None) -> bytes:
        return self._body if size is None else self._body[:size]


def make_filing(**overrides: Any) -> FilingReference:
    """Create the discovered filing whose document the provider retrieves."""

    fields: dict[str, Any] = {
        "cik": "937966",
        "form_type": "20-F",
        "accession_number": "0000937966-26-000008",
        "period_end": date(2025, 12, 31),
        "filed_on": date(2026, 2, 11),
        "document_url": HttpUrl(DOCUMENT_URL),
        "sources": (
            SourceReference(
                provider="sec_edgar",
                source_type="submissions_index",
                source_id="CIK0000937966-submissions",
                url=HttpUrl("https://data.sec.gov/submissions/CIK0000937966.json"),
                retrieved_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
            ),
        ),
    }
    return FilingReference(**{**fields, **overrides})


def respond_with(
    monkeypatch: pytest.MonkeyPatch, body: bytes, content_type: str | None
) -> None:
    """Serve one fixed document response to every request."""

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(body, content_type)

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.sleep",
        lambda delay: None,
    )


@pytest.fixture
def recorded_requests(monkeypatch: pytest.MonkeyPatch) -> list[Request]:
    """Replace urlopen with the recorded filing document and record requests."""

    requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        requests.append(request)
        return FakeResponse(
            DOCUMENT_FIXTURE_PATH.read_bytes(), "text/html; charset=UTF-8"
        )

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.sleep",
        lambda delay: None,
    )
    return requests


def test_get_document_retrieves_the_filings_primary_document(
    recorded_requests: list[Request],
) -> None:
    retrieved = EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    assert retrieved.filing == make_filing()
    assert retrieved.content_type == "text/html"
    assert "Risk Factors" in retrieved.untrusted_text
    assert len(recorded_requests) == 1
    assert recorded_requests[0].full_url == DOCUMENT_URL


def test_get_document_sends_the_contact_user_agent(
    recorded_requests: list[Request],
) -> None:
    EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    assert recorded_requests[0].get_header("User-agent") == USER_AGENT


def test_get_document_records_the_retrieved_payload_size(
    recorded_requests: list[Request],
) -> None:
    retrieved = EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    assert retrieved.byte_size == len(DOCUMENT_FIXTURE_PATH.read_bytes())
    assert retrieved.byte_size > len(retrieved.untrusted_text)


def test_get_document_decodes_the_declared_character_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond_with(
        monkeypatch,
        "Net sales were €32.7 billion.".encode("iso-8859-15"),
        "text/html; charset=ISO-8859-15",
    )

    retrieved = EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    assert "€32.7 billion" in retrieved.untrusted_text


def test_get_document_source_cites_the_filing_by_accession_number(
    recorded_requests: list[Request],
) -> None:
    retrieved = EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    source = retrieved.sources[0]
    assert source.provider == "sec_edgar"
    assert source.source_type == "annual_report_document"
    assert source.source_id == "0000937966-26-000008"
    assert str(source.url) == DOCUMENT_URL
    assert source.period_end == date(2025, 12, 31)
    assert source.retrieved_at is not None


def test_get_document_rejects_documents_larger_than_the_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond_with(monkeypatch, b"x" * 2048, "text/html")

    provider = EdgarFilingProvider(USER_AGENT, max_document_bytes=1024)

    with pytest.raises(EdgarProviderError, match="maximum retrievable size"):
        provider.get_document(make_filing())


def test_get_document_accepts_a_document_at_exactly_the_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond_with(monkeypatch, b"x" * 1024, "text/html")

    provider = EdgarFilingProvider(USER_AGENT, max_document_bytes=1024)

    assert provider.get_document(make_filing()).byte_size == 1024


@pytest.mark.parametrize(
    "content_type",
    [None, "", "application/pdf", "application/json", "image/png"],
)
def test_get_document_rejects_unsupported_content_types(
    monkeypatch: pytest.MonkeyPatch, content_type: str | None
) -> None:
    respond_with(monkeypatch, b"<html></html>", content_type)

    with pytest.raises(EdgarProviderError, match="supported text type"):
        EdgarFilingProvider(USER_AGENT).get_document(make_filing())


def test_get_document_accepts_plain_text_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond_with(monkeypatch, b"Item 3.D. Risk Factors", "text/plain")

    retrieved = EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    assert retrieved.content_type == "text/plain"


@pytest.mark.parametrize(
    "content_type",
    ["text/html; charset=utf-8", "text/html; charset=not-a-charset"],
)
def test_get_document_rejects_text_it_cannot_decode(
    monkeypatch: pytest.MonkeyPatch, content_type: str
) -> None:
    respond_with(monkeypatch, b"\xff\xfe invalid", content_type)

    with pytest.raises(EdgarProviderError, match="decoded as text"):
        EdgarFilingProvider(USER_AGENT).get_document(make_filing())


def test_get_document_rejects_empty_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond_with(monkeypatch, b"", "text/html")

    with pytest.raises(EdgarProviderError, match="empty"):
        EdgarFilingProvider(USER_AGENT).get_document(make_filing())


@pytest.mark.parametrize(
    "document_url",
    [
        "https://example.test/Archives/edgar/data/937966/000/asml.htm",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
        "https://www.sec.gov.example.test/Archives/edgar/data/937966/000/asml.htm",
        "https://www.sec.gov/Archives/edgar/dataX/937966/000/asml.htm",
    ],
)
def test_get_document_refuses_urls_outside_the_edgar_archives(
    monkeypatch: pytest.MonkeyPatch, document_url: str
) -> None:
    respond_with(monkeypatch, b"<html></html>", "text/html")

    filing = make_filing(document_url=HttpUrl(document_url))

    with pytest.raises(EdgarProviderError, match="outside the EDGAR archives"):
        EdgarFilingProvider(USER_AGENT).get_document(filing)


def test_get_document_refuses_urls_that_escape_the_filing_archive_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative segments resolve during URL parsing, so the guard still applies."""

    respond_with(monkeypatch, b"<html></html>", "text/html")

    filing = make_filing(
        document_url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/937966/000/../../../evil.htm"
        )
    )

    assert str(filing.document_url) == "https://www.sec.gov/Archives/edgar/evil.htm"
    with pytest.raises(EdgarProviderError, match="outside the EDGAR archives"):
        EdgarFilingProvider(USER_AGENT).get_document(filing)


def test_get_document_waits_for_the_remaining_request_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock_values = iter((0.0, 0.05, 0.15))
    recorded_sleeps: list[float] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(DOCUMENT_FIXTURE_PATH.read_bytes(), "text/html")

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.monotonic",
        lambda: next(clock_values),
    )
    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.sleep",
        recorded_sleeps.append,
    )

    provider = EdgarFilingProvider(USER_AGENT)
    provider.get_document(make_filing())
    provider.get_document(make_filing())

    assert recorded_sleeps == [pytest.approx(0.10)]


@pytest.mark.parametrize(
    "network_error",
    [
        HTTPError("https://example.test", 404, "not found", Message(), None),
        URLError("connection unavailable"),
    ],
)
def test_get_document_wraps_network_errors_safely(
    monkeypatch: pytest.MonkeyPatch, network_error: Exception
) -> None:
    def failing_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise network_error

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        failing_urlopen,
    )

    with pytest.raises(EdgarProviderError) as error:
        EdgarFilingProvider(USER_AGENT).get_document(make_filing())

    assert "https://" not in str(error.value)


@pytest.mark.parametrize("max_document_bytes", [0, -1])
def test_constructor_rejects_nonpositive_document_limits(
    max_document_bytes: int,
) -> None:
    with pytest.raises(ValueError, match="max_document_bytes"):
        EdgarFilingProvider(USER_AGENT, max_document_bytes=max_document_bytes)
