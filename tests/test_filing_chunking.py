"""Tests for splitting a sectioned filing into retrievable chunks."""

from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import HttpUrl

from equity_research_agent.filings import chunk_filing_sections
from equity_research_agent.models.filings import (
    FilingReference,
    FilingSection,
    SectionedFiling,
)
from equity_research_agent.models.provenance import SourceReference

DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/937966/"
    "000093796626000008/asml-20251231.htm"
)


def make_filing(**overrides: Any) -> FilingReference:
    """Create the filing a sectioned document belongs to."""

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
                retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            ),
        ),
    }
    return FilingReference(**{**fields, **overrides})


def make_sectioned(*sections: FilingSection) -> SectionedFiling:
    """Wrap sections in a ``SectionedFiling`` for the filing under test."""

    return SectionedFiling(
        filing=make_filing(),
        sections=sections,
        sources=(
            SourceReference(
                provider="sec_edgar",
                source_type="annual_report_document",
                source_id="0000937966-26-000008",
                url=HttpUrl(DOCUMENT_URL),
                retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
                period_end=date(2025, 12, 31),
            ),
        ),
    )


def make_section(text: str, **overrides: Any) -> FilingSection:
    fields: dict[str, Any] = {
        "label": "Item 1A. Risk Factors",
        "anchor_id": "risk_factors",
        "text": text,
        "item_identifier": "1A",
    }
    return FilingSection(**{**fields, **overrides})


def test_short_section_produces_a_single_chunk() -> None:
    sectioned = make_sectioned(make_section("We face several risks."))

    chunks = chunk_filing_sections(sectioned, chunk_size=1500, overlap=200)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.text == "We face several risks."
    assert chunk.chunk_index == 0
    assert chunk.filing == sectioned.filing
    assert chunk.section_label == "Item 1A. Risk Factors"
    assert chunk.section_anchor_id == "risk_factors"
    assert chunk.item_identifier == "1A"
    assert chunk.sources == sectioned.sources


def test_long_section_produces_multiple_overlapping_chunks() -> None:
    words = [f"risk{n}" for n in range(400)]
    text = " ".join(words)
    sectioned = make_sectioned(make_section(text))

    chunks = chunk_filing_sections(sectioned, chunk_size=100, overlap=20)

    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert len(chunk.text) <= 100 or " " not in chunk.text

    # Consecutive chunks share trailing/leading context.
    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    assert first_words[-1] in second_words[: len(first_words)]


def test_chunks_never_split_a_word() -> None:
    text = "supercalifragilisticexpialidocious " * 5
    sectioned = make_sectioned(make_section(text.strip()))

    chunks = chunk_filing_sections(sectioned, chunk_size=10, overlap=2)

    for chunk in chunks:
        assert all(
            word == "supercalifragilisticexpialidocious"
            for word in chunk.text.split()
        )


def test_multiple_sections_chunk_independently_with_own_provenance() -> None:
    sectioned = make_sectioned(
        make_section(
            "Risk one.",
            label="Item 1A. Risk Factors",
            anchor_id="risk_factors",
            item_identifier="1A",
        ),
        make_section(
            "Business overview.",
            label="Item 1. Business",
            anchor_id="business",
            item_identifier="1",
        ),
    )

    chunks = chunk_filing_sections(sectioned, chunk_size=1500, overlap=200)

    assert len(chunks) == 2
    assert chunks[0].section_anchor_id == "risk_factors"
    assert chunks[1].section_anchor_id == "business"
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 0


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (-1, 0), (100, -1), (100, 100), (100, 150)],
)
def test_invalid_chunk_parameters_raise(chunk_size: int, overlap: int) -> None:
    sectioned = make_sectioned(make_section("Some risk text."))

    with pytest.raises(ValueError):
        chunk_filing_sections(sectioned, chunk_size=chunk_size, overlap=overlap)
