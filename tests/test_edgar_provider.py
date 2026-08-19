"""Tests for the synchronous SEC EDGAR filing-discovery provider."""

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from equity_research_agent.data.providers import FilingProvider
from equity_research_agent.data.providers.edgar import EdgarNormalizationError
from equity_research_agent.data.providers.edgar_provider import (
    EdgarFilingProvider,
    EdgarProviderError,
)

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "providers"
    / "sec_edgar"
    / "asml"
    / "submissions.json"
)

USER_AGENT = "Equity Research Agent research@example.test"


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
def recorded_requests(monkeypatch: pytest.MonkeyPatch) -> list[Request]:
    """Replace urlopen with the recorded submissions fixture and record requests."""

    requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        requests.append(request)
        return FakeResponse(FIXTURE_PATH.read_bytes())

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.sleep",
        lambda delay: None,
    )
    return requests


def test_provider_conforms_to_filing_provider_protocol() -> None:
    assert isinstance(EdgarFilingProvider(USER_AGENT), FilingProvider)


def test_get_latest_annual_report_fetches_and_normalizes_submissions(
    recorded_requests: list[Request],
) -> None:
    filing = EdgarFilingProvider(USER_AGENT).get_latest_annual_report("937966")

    assert filing.form_type == "20-F"
    assert filing.accession_number == "0000937966-26-000008"
    assert len(recorded_requests) == 1
    assert recorded_requests[0].full_url == (
        "https://data.sec.gov/submissions/CIK0000937966.json"
    )


def test_provider_sends_the_contact_user_agent_edgar_requires(
    recorded_requests: list[Request],
) -> None:
    EdgarFilingProvider(f"  {USER_AGENT}  ").get_latest_annual_report("937966")

    assert recorded_requests[0].get_header("User-agent") == USER_AGENT
    assert recorded_requests[0].get_header("Accept") == "application/json"


@pytest.mark.parametrize("cik", ["937966", "0000937966", " 937966 "])
def test_provider_zero_pads_the_requested_cik(
    recorded_requests: list[Request], cik: str
) -> None:
    EdgarFilingProvider(USER_AGENT).get_latest_annual_report(cik)

    assert recorded_requests[0].full_url.endswith("CIK0000937966.json")


def test_source_records_the_submissions_index_it_read(
    recorded_requests: list[Request],
) -> None:
    filing = EdgarFilingProvider(USER_AGENT).get_latest_annual_report("937966")

    source = filing.sources[0]
    assert source.provider == "sec_edgar"
    assert source.source_type == "submissions_index"
    assert source.source_id == "CIK0000937966-submissions"
    assert str(source.url) == "https://data.sec.gov/submissions/CIK0000937966.json"
    assert source.retrieved_at is not None


def test_provider_does_not_retrieve_the_filing_document(
    recorded_requests: list[Request],
) -> None:
    filing = EdgarFilingProvider(USER_AGENT).get_latest_annual_report("937966")

    assert len(recorded_requests) == 1
    assert str(filing.document_url) not in [
        request.full_url for request in recorded_requests
    ]


def test_provider_waits_for_the_remaining_request_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock_values = iter((0.0, 0.05, 0.15))
    recorded_sleeps: list[float] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(FIXTURE_PATH.read_bytes())

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
    provider.get_latest_annual_report("937966")
    provider.get_latest_annual_report("937966")

    assert recorded_sleeps == [pytest.approx(0.10)]


@pytest.mark.parametrize("user_agent", ["", "   "])
def test_constructor_rejects_a_blank_user_agent(user_agent: str) -> None:
    with pytest.raises(ValueError, match="user_agent"):
        EdgarFilingProvider(user_agent)


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_constructor_rejects_nonpositive_timeout(timeout_seconds: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        EdgarFilingProvider(USER_AGENT, timeout_seconds=timeout_seconds)


@pytest.mark.parametrize("cik", ["", "   ", "ASML", "12345678901", "93-7966"])
def test_provider_rejects_invalid_ciks(cik: str) -> None:
    with pytest.raises(ValueError, match="cik"):
        EdgarFilingProvider(USER_AGENT).get_latest_annual_report(cik)


@pytest.mark.parametrize(
    "network_error",
    [
        HTTPError("https://example.test", 403, "forbidden", Message(), None),
        URLError("connection unavailable"),
    ],
)
def test_http_and_url_errors_are_safely_wrapped(
    monkeypatch: pytest.MonkeyPatch, network_error: Exception
) -> None:
    def failing_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise network_error

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        failing_urlopen,
    )

    with pytest.raises(EdgarProviderError) as error:
        EdgarFilingProvider(USER_AGENT).get_latest_annual_report("937966")

    assert "https://" not in str(error.value)


@pytest.mark.parametrize("body", [b"not json", b"[]"])
def test_invalid_or_nonobject_json_is_rejected_safely(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(body)

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        fake_urlopen,
    )

    with pytest.raises(EdgarProviderError) as error:
        EdgarFilingProvider(USER_AGENT).get_latest_annual_report("937966")

    assert "https://" not in str(error.value)


def test_provider_payload_is_validated_by_the_normalizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(json.dumps({"cik": "937966"}).encode())

    monkeypatch.setattr(
        "equity_research_agent.data.providers.edgar_provider.urlopen",
        fake_urlopen,
    )

    with pytest.raises(EdgarNormalizationError, match="filings"):
        EdgarFilingProvider(USER_AGENT).get_latest_annual_report("937966")
