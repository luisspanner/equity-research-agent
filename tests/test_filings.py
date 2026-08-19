"""Tests for the discovered-filing domain model."""

from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import HttpUrl, ValidationError

from equity_research_agent.models.filings import (
    ANNUAL_REPORT_FORM_TYPES,
    FilingReference,
)
from equity_research_agent.models.provenance import SourceReference


def make_source() -> SourceReference:
    """Create provenance for the EDGAR submissions index."""

    return SourceReference(
        provider="sec_edgar",
        source_type="submissions_index",
        source_id="CIK0000937966-submissions",
        url=HttpUrl("https://data.sec.gov/submissions/CIK0000937966.json"),
        retrieved_at=datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
    )


def make_filing(**overrides: Any) -> FilingReference:
    """Create a valid annual-report reference with optional field overrides."""

    fields: dict[str, Any] = {
        "cik": "937966",
        "form_type": "20-F",
        "accession_number": "0000937966-26-000008",
        "period_end": date(2025, 12, 31),
        "filed_on": date(2026, 2, 11),
        "document_url": HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/937966/"
            "000093796626000008/asml-20251231.htm"
        ),
        "sources": (make_source(),),
    }
    return FilingReference(**{**fields, **overrides})


def test_annual_report_form_types_are_derived_from_the_literal() -> None:
    assert ANNUAL_REPORT_FORM_TYPES == ("10-K", "20-F")


def test_filing_reference_retains_metadata_and_provenance() -> None:
    filing = make_filing()

    assert filing.form_type == "20-F"
    assert filing.period_end == date(2025, 12, 31)
    assert filing.sources[0].provider == "sec_edgar"


def test_filing_reference_is_immutable() -> None:
    filing = make_filing()

    with pytest.raises(ValidationError):
        filing.form_type = "10-K"  # type: ignore[misc]


def test_filing_reference_accepts_both_annual_report_form_types() -> None:
    assert make_filing(form_type="10-K").form_type == "10-K"


@pytest.mark.parametrize("form_type", ["20-F/A", "10-K/A", "6-K", "10-Q", ""])
def test_filing_reference_rejects_non_annual_report_forms(form_type: str) -> None:
    with pytest.raises(ValidationError):
        make_filing(form_type=form_type)


@pytest.mark.parametrize(
    "accession_number",
    ["000093796626000008", "0000937966-26-00008", "not-an-accession", ""],
)
def test_filing_reference_rejects_malformed_accession_numbers(
    accession_number: str,
) -> None:
    with pytest.raises(ValidationError):
        make_filing(accession_number=accession_number)


def test_filing_reference_rejects_filings_dated_before_their_period_end() -> None:
    with pytest.raises(ValidationError, match="filed_on"):
        make_filing(filed_on=date(2025, 12, 30))


def test_filing_reference_allows_filing_on_the_period_end_date() -> None:
    assert make_filing(filed_on=date(2025, 12, 31)).filed_on == date(2025, 12, 31)


def test_filing_reference_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        make_filing(sources=())


@pytest.mark.parametrize("cik", ["", "ASML", "00009379661"])
def test_filing_reference_rejects_invalid_ciks(cik: str) -> None:
    with pytest.raises(ValidationError):
        make_filing(cik=cik)


def test_filing_reference_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        make_filing(document_text="the full annual report")
