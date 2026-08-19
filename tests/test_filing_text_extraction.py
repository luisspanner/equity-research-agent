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

FIXTURE_DIRECTORY = (
    Path(__file__).parent / "fixtures" / "providers" / "sec_edgar" / "asml"
)
FIXTURE_PATH = FIXTURE_DIRECTORY / "inline_xbrl_excerpt.htm"
REAL_FILING_PATH = FIXTURE_DIRECTORY / "asml_20f_excerpt.htm"

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
            "Total net sales for 2025 were €32,667.3 million.",
            "Gross profit margin was 51.3%.",
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


def test_extraction_keeps_the_spacing_the_document_itself_carries() -> None:
    text = extract("<p>a <b>substantial</b> <i>portion</i> of sales</p>")

    assert text == "a substantial portion of sales"


def test_extraction_does_not_insert_spaces_between_adjacent_inline_tags() -> None:
    """Browsers render adjacent inline elements as one word, and so must we."""

    text = extract("<p>Our <span>Yield</span><span>Star</span> systems</p>")

    assert text == "Our YieldStar systems"


def test_extraction_does_not_separate_values_from_their_punctuation() -> None:
    text = extract(
        "<p>Net sales were &#8364;<ix:nonFraction>32,667.3</ix:nonFraction> "
        "million on December 31<ix:nonNumeric>, 2025</ix:nonNumeric>.</p>"
    )

    assert text == "Net sales were €32,667.3 million on December 31, 2025."


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


def real_filing_text() -> str:
    """Extract text from the recorded excerpt of ASML's 2025 Form 20-F."""

    return extract(REAL_FILING_PATH.read_text())


def test_real_filing_cover_page_reads_as_prose() -> None:
    text = real_filing_text()

    assert "for the fiscal year ended December 31, 2025" in text
    assert "ASML HOLDING NV" in text
    assert "(Exact Name of Registrant as Specified in Its Charter)" in text


def test_real_filing_values_keep_their_punctuation() -> None:
    text = real_filing_text()

    assert "Total net sales rose by €4.4 billion, or" in text
    assert " ," not in text
    assert "€ " not in text


def test_real_filing_drops_inline_xbrl_header_facts() -> None:
    text = real_filing_text()

    assert "0000937966" not in text
    assert "EntityCentralIndexKey" not in text


def test_real_filing_drops_the_document_title() -> None:
    text = real_filing_text()

    assert "asml-20251231" not in text


def test_real_filing_keeps_tagged_financial_values() -> None:
    text = real_filing_text()

    assert "Year ended December 31 (€, in millions)" in text
    for value in ("148.2", "96.3", "88.7"):
        assert value in text


def test_real_filing_columns_without_source_whitespace_fuse() -> None:
    """Document a known limit rather than pretend it does not exist.

    This filer lays out cover-page columns with absolute positioning and no
    whitespace between the inline elements, so extraction cannot tell the
    columns apart. Adding a separator would instead insert about a thousand
    spurious spaces elsewhere in the same document, which is the worse trade.
    """

    assert "Trading SymbolName of each exchange" in real_filing_text()


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
