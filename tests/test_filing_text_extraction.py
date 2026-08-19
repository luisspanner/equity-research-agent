"""Tests for extracting readable text from retrieved filing documents."""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import HttpUrl

from equity_research_agent.filings import (
    FilingTextExtractionError,
    extract_filing_text,
)
from equity_research_agent.models.filings import FilingReference, RetrievedFiling
from equity_research_agent.models.provenance import SourceReference

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "providers"
    / "sec_edgar"
    / "asml"
    / "inline_xbrl_excerpt.htm"
)

DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/937966/"
    "000093796626000008/asml-20251231.htm"
)


def make_filing() -> FilingReference:
    """Create the discovered filing the retrieved document belongs to."""

    return FilingReference(
        cik="937966",
        form_type="20-F",
        accession_number="0000937966-26-000008",
        period_end=date(2025, 12, 31),
        filed_on=date(2026, 2, 11),
        document_url=HttpUrl(DOCUMENT_URL),
        sources=(
            SourceReference(
                provider="sec_edgar",
                source_type="submissions_index",
                source_id="CIK0000937966-submissions",
                url=HttpUrl("https://data.sec.gov/submissions/CIK0000937966.json"),
                retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            ),
        ),
    )


def make_retrieved(untrusted_text: str, **overrides: Any) -> RetrievedFiling:
    """Create a retrieved filing carrying the supplied document text."""

    fields: dict[str, Any] = {
        "filing": make_filing(),
        "content_type": "text/html",
        "byte_size": max(len(untrusted_text.encode()), 1),
        "untrusted_text": untrusted_text,
        "sources": (
            SourceReference(
                provider="sec_edgar",
                source_type="annual_report_document",
                source_id="0000937966-26-000008",
                url=HttpUrl(DOCUMENT_URL),
                retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
                period_end=date(2025, 12, 31),
            ),
        ),
    }
    return RetrievedFiling(**{**fields, **overrides})


def extract(document: str, **overrides: Any) -> str:
    """Extract text from one document and return it."""

    return extract_filing_text(make_retrieved(document, **overrides)).untrusted_text


def test_extracts_readable_text_from_a_recorded_inline_xbrl_document() -> None:
    retrieved = make_retrieved(FIXTURE_PATH.read_text())

    assert extract_filing_text(retrieved).untrusted_text == "\n".join(
        [
            "Item 3.D. Risk Factors",
            "We derive a substantial portion of our net sales from a small number"
            " of customers, and the loss of one of them would materially affect"
            " our results of operations.",
            "Total net sales for 2025 were € 32,667.3 million.",
            "Gross profit margin was 51.3 %.",
            "Year Net sales Gross profit",
            "2025 32,667.3 16,758.3",
            "2024 28,263.0 14,266.0",
            "Our operations depend on a limited number of suppliers of critical"
            " components.",
        ]
    )


def test_extraction_preserves_the_documents_provenance() -> None:
    retrieved = make_retrieved(FIXTURE_PATH.read_text())

    extracted = extract_filing_text(retrieved)

    assert extracted.filing == retrieved.filing
    assert extracted.sources == retrieved.sources


def test_extraction_drops_scripts_styles_and_document_metadata() -> None:
    text = extract(FIXTURE_PATH.read_text())

    assert "toggleSection" not in text
    assert "font-family" not in text
    assert "Form 20-F" not in text


def test_extraction_drops_inline_xbrl_metadata_and_hidden_elements() -> None:
    text = extract(FIXTURE_PATH.read_text())

    assert "ASML HOLDING NV" not in text
    assert "EntityRegistrantName" not in text
    assert "Draft note" not in text


def test_extraction_keeps_reported_values_that_inline_xbrl_wraps() -> None:
    text = extract(FIXTURE_PATH.read_text())

    assert "32,667.3" in text
    assert "51.3" in text


def test_extraction_does_not_fuse_words_across_inline_tags() -> None:
    text = extract("<p>a <b>substantial</b><i>portion</i> of sales</p>")

    assert text == "a substantial portion of sales"


def test_extraction_joins_prose_wrapped_across_source_lines() -> None:
    text = extract("<p>a small\nnumber of\n   customers</p>")

    assert text == "a small number of customers"


def test_extraction_puts_each_block_element_on_its_own_line() -> None:
    text = extract("<p>first paragraph</p><p>second paragraph</p>")

    assert text == "first paragraph\nsecond paragraph"


def test_extraction_keeps_one_table_row_per_line() -> None:
    text = extract(
        "<table><tr><td>2025</td><td>32,667.3</td></tr>"
        "<tr><td>2024</td><td>28,263.0</td></tr></table>"
    )

    assert text == "2025 32,667.3\n2024 28,263.0"


def test_extraction_treats_line_breaks_as_block_boundaries() -> None:
    text = extract("<p>net sales<br/>gross profit</p>")

    assert text == "net sales\ngross profit"


def test_extraction_replaces_non_breaking_spaces() -> None:
    text = extract("<p>Item&nbsp;3.D.&nbsp;Risk Factors</p>")

    assert text == "Item 3.D. Risk Factors"
    assert "\xa0" not in text


def test_extraction_ignores_block_separators_present_in_the_document() -> None:
    text = extract("<p>net\x00sales</p>")

    assert text == "netsales"


def test_extraction_normalizes_plain_text_without_parsing_it_as_html() -> None:
    text = extract(
        "Item 3.D.   Risk Factors\n\n\nSuppliers &amp; customers\n",
        content_type="text/plain",
    )

    assert text == "Item 3.D. Risk Factors\nSuppliers &amp; customers"


def test_extraction_rejects_unsupported_content_types() -> None:
    with pytest.raises(FilingTextExtractionError, match="application/pdf"):
        extract("<p>text</p>", content_type="application/pdf")


@pytest.mark.parametrize(
    "document",
    [
        "<html><head><title>20-F</title></head><body></body></html>",
        "<p>   </p>",
        "<script>var noise = 1;</script>",
        "   ",
    ],
)
def test_extraction_rejects_documents_without_readable_text(document: str) -> None:
    with pytest.raises(FilingTextExtractionError, match="no readable text"):
        extract(document)
