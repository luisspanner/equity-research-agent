"""Tests for normalization of the EDGAR submissions-index contract."""

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import HttpUrl

from equity_research_agent.data.providers.edgar import (
    EdgarNormalizationError,
    normalize_latest_annual_report,
)
from equity_research_agent.models.provenance import SourceReference

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "providers"
    / "sec_edgar"
    / "asml"
    / "submissions.json"
)


def make_source() -> SourceReference:
    """Create provenance for the EDGAR submissions index."""

    return SourceReference(
        provider="sec_edgar",
        source_type="submissions_index",
        source_id="CIK0000937966-submissions",
        url=HttpUrl("https://data.sec.gov/submissions/CIK0000937966.json"),
        retrieved_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
    )


def load_submissions() -> dict[str, Any]:
    """Load a mutable copy of the recorded ASML submissions payload."""

    with FIXTURE_PATH.open() as fixture_file:
        payload: dict[str, Any] = json.load(fixture_file)
    return payload


def recent(submissions: dict[str, Any]) -> dict[str, Any]:
    """Return the mutable recent-filings block of a submissions payload."""

    block: dict[str, Any] = submissions["filings"]["recent"]
    return block


def test_normalizer_selects_the_most_recently_filed_annual_report() -> None:
    filing = normalize_latest_annual_report(load_submissions(), make_source())

    assert filing.form_type == "20-F"
    assert filing.accession_number == "0000937966-26-000008"
    assert filing.filed_on == date(2026, 2, 11)
    assert filing.period_end == date(2025, 12, 31)


def test_normalizer_builds_the_canonical_primary_document_url() -> None:
    filing = normalize_latest_annual_report(load_submissions(), make_source())

    assert str(filing.document_url) == (
        "https://www.sec.gov/Archives/edgar/data/937966/"
        "000093796626000008/asml-20251231.htm"
    )


def test_normalizer_retains_the_supplied_source_reference() -> None:
    source = make_source()

    filing = normalize_latest_annual_report(load_submissions(), source)

    assert filing.sources == (source,)


def test_normalizer_strips_leading_zeros_from_the_reported_cik() -> None:
    submissions = load_submissions()
    submissions["cik"] = "0000937966"

    assert normalize_latest_annual_report(submissions, make_source()).cik == "937966"


def test_normalizer_accepts_an_integer_cik() -> None:
    submissions = load_submissions()
    submissions["cik"] = 937966

    assert normalize_latest_annual_report(submissions, make_source()).cik == "937966"


def test_normalizer_selects_ten_k_filings_for_domestic_issuers() -> None:
    submissions = load_submissions()
    recent(submissions)["form"] = ["6-K", "10-K", "6-K", "6-K", "10-K"]

    filing = normalize_latest_annual_report(submissions, make_source())

    assert filing.form_type == "10-K"
    assert filing.filed_on == date(2026, 2, 11)


def test_normalizer_ignores_amendments_to_annual_reports() -> None:
    submissions = load_submissions()
    recent(submissions)["form"] = ["20-F/A", "6-K", "6-K", "6-K", "20-F"]

    filing = normalize_latest_annual_report(submissions, make_source())

    assert filing.accession_number == "0000937966-25-000003"
    assert filing.filed_on == date(2025, 2, 12)


def test_normalizer_ignores_filing_order_within_the_payload() -> None:
    submissions = load_submissions()
    recent(submissions)["filingDate"] = [
        "2026-04-22",
        "2025-02-12",
        "2026-01-28",
        "2025-07-16",
        "2026-02-11",
    ]
    recent(submissions)["reportDate"] = [
        "2025-12-31",
        "2024-12-31",
        "2025-12-31",
        "2025-06-30",
        "2025-12-31",
    ]

    filing = normalize_latest_annual_report(submissions, make_source())

    assert filing.accession_number == "0000937966-25-000003"
    assert filing.filed_on == date(2026, 2, 11)


def test_normalizer_rejects_payloads_without_an_annual_report() -> None:
    submissions = load_submissions()
    recent(submissions)["form"] = ["6-K", "6-K", "6-K", "6-K", "6-K"]

    with pytest.raises(EdgarNormalizationError, match="no 10-K or 20-F"):
        normalize_latest_annual_report(submissions, make_source())


def test_normalizer_rejects_a_missing_primary_document() -> None:
    submissions = load_submissions()
    recent(submissions)["primaryDocument"][1] = "  "

    with pytest.raises(EdgarNormalizationError, match="primary document"):
        normalize_latest_annual_report(submissions, make_source())


def test_normalizer_rejects_misaligned_parallel_arrays() -> None:
    submissions = load_submissions()
    recent(submissions)["reportDate"] = ["2025-12-31"]

    with pytest.raises(EdgarNormalizationError, match="misaligned"):
        normalize_latest_annual_report(submissions, make_source())


@pytest.mark.parametrize("field", ["accessionNumber", "form", "filingDate"])
def test_normalizer_rejects_missing_required_columns(field: str) -> None:
    submissions = load_submissions()
    del recent(submissions)[field]

    with pytest.raises(EdgarNormalizationError, match=field):
        normalize_latest_annual_report(submissions, make_source())


def test_normalizer_rejects_non_string_column_values() -> None:
    submissions = load_submissions()
    recent(submissions)["form"] = ["6-K", 20, "6-K", "6-K", "20-F"]

    with pytest.raises(EdgarNormalizationError, match="form"):
        normalize_latest_annual_report(submissions, make_source())


@pytest.mark.parametrize("field", ["filingDate", "reportDate"])
def test_normalizer_rejects_non_iso_dates(field: str) -> None:
    submissions = load_submissions()
    recent(submissions)[field][1] = "11 February 2026"

    with pytest.raises(EdgarNormalizationError, match=field):
        normalize_latest_annual_report(submissions, make_source())


@pytest.mark.parametrize("payload", [{}, {"cik": "937966"}, {"cik": "ASML"}])
def test_normalizer_rejects_structurally_invalid_payloads(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(EdgarNormalizationError):
        normalize_latest_annual_report(payload, make_source())


def test_normalizer_rejects_a_non_object_recent_block() -> None:
    submissions = load_submissions()
    submissions["filings"]["recent"] = []

    with pytest.raises(EdgarNormalizationError, match="recent"):
        normalize_latest_annual_report(submissions, make_source())


def test_normalizer_rejects_annual_reports_filed_before_their_period_end() -> None:
    submissions = load_submissions()
    recent(submissions)["reportDate"][1] = "2026-12-31"

    with pytest.raises(EdgarNormalizationError, match="filing contract"):
        normalize_latest_annual_report(submissions, make_source())


def test_normalizer_does_not_mutate_the_supplied_payload() -> None:
    submissions = load_submissions()
    original = deepcopy(submissions)

    normalize_latest_annual_report(submissions, make_source())

    assert submissions == original
