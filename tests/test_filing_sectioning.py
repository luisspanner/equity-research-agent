"""Tests for dividing a retrieved filing into labelled sections."""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import HttpUrl

from equity_research_agent.filings import FilingSectioningError, extract_filing_sections
from equity_research_agent.models.filings import FilingReference, RetrievedFiling
from equity_research_agent.models.provenance import SourceReference

ASML_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "providers"
    / "sec_edgar"
    / "asml"
    / "reference_table_excerpt.htm"
)
NVDA_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "providers"
    / "sec_edgar"
    / "nvda"
    / "toc_excerpt.htm"
)

DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/937966/"
    "000093796626000008/asml-20251231.htm"
)


def make_filing(**overrides: Any) -> FilingReference:
    """Create the discovered filing the retrieved document belongs to."""

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


def _row(label: str, target: str, page: str = "1") -> str:
    """Build one index row linking a label and a page number to one target."""

    return (
        "<tr><td><a href='#{t}'>{l}</a></td><td><a href='#{t}'>{p}</a></td></tr>"
    ).format(t=target, l=label, p=page)


def sections(document: str, **overrides: Any) -> list[tuple[str, str, str]]:
    """Extract sections and return (label, anchor_id, text) tuples."""

    result = extract_filing_sections(make_retrieved(document, **overrides))
    return [(s.label, s.anchor_id, s.text) for s in result.sections]


def test_sections_run_from_their_anchor_to_the_next_cited_anchor() -> None:
    document = (
        "<table>" + _row("Item 1.", "a") + _row("Item 2.", "b") + "</table>"
        "<div id='a'></div><p>first section</p>"
        "<div id='b'></div><p>second section</p>"
    )

    assert sections(document) == [
        ("Item 1.", "a", "first section"),
        ("Item 2.", "b", "second section"),
    ]


def test_a_target_cited_by_two_rows_yields_two_overlapping_sections() -> None:
    document = (
        "<table>" + _row("Item 1.", "a") + _row("Item 2.", "a") + "</table>"
        "<div id='a'></div><p>shared content</p>"
    )

    result = sections(document)

    assert [label for label, _, _ in result] == ["Item 1.", "Item 2."]
    assert all(anchor == "a" for _, anchor, _ in result)
    assert all(text == "shared content" for _, _, text in result)


def test_label_combines_row_text_even_when_only_the_page_number_is_linked() -> None:
    """ASML links only its page-number cell, so the caption cell carries no
    link of its own; the label must still be built from the whole row."""

    document = (
        "<table><tr><td>D. Risk Factors</td>"
        "<td><a href='#a'>66</a></td></tr></table>"
        "<div id='a'></div><p>content</p>"
    )

    assert sections(document) == [("D. Risk Factors", "a", "content")]


def test_label_drops_only_purely_numeric_fragments() -> None:
    document = (
        "<table>"
        + _row("Item 1A.", "a", page="12")
        + "</table><div id='a'></div><p>content</p>"
    )

    assert sections(document)[0][0] == "Item 1A."


def test_a_row_citing_two_targets_labels_each_from_its_own_cells() -> None:
    document = (
        "<table><tr>"
        "<td><a href='#a'>Item 1.</a></td>"
        "<td><a href='#b'>Item 1 continued</a></td>"
        "</tr></table>"
        "<div id='a'></div><p>first</p>"
        "<div id='b'></div><p>second</p>"
    )

    assert sections(document) == [
        ("Item 1.", "a", "first"),
        ("Item 1 continued", "b", "second"),
    ]


def test_links_outside_a_table_row_are_not_treated_as_an_index() -> None:
    document = (
        "<p>See <a href='#a'>Item 1.</a> for details.</p><div id='a'></div>"
        "<p>content</p>"
    )

    with pytest.raises(FilingSectioningError, match="no internal sectioning links"):
        extract_filing_sections(make_retrieved(document))


def test_a_dangling_target_is_skipped_rather_than_raising() -> None:
    document = (
        "<table>" + _row("Item 1.", "a") + _row("Item 2.", "missing") + "</table>"
        "<div id='a'></div><p>content</p>"
    )

    assert sections(document) == [("Item 1.", "a", "content")]


def test_a_marker_not_cited_by_the_index_does_not_bound_a_section() -> None:
    """An id that is not one of the index's own targets is real structure the
    filer's rendering places there, not a boundary -- matches the NVIDIA
    fixture's unreferenced marker inside its kept Item 1A. content."""

    document = (
        "<table>" + _row("Item 1.", "a") + "</table>"
        "<div id='a'></div><p>first</p>"
        "<div id='unrelated'></div><p>still part of the same section</p>"
    )

    assert sections(document) == [
        ("Item 1.", "a", "first\nstill part of the same section")
    ]


def test_a_section_with_no_content_before_the_next_anchor_is_skipped() -> None:
    document = (
        "<table>" + _row("Item 1.", "a") + _row("Item 2.", "b") + "</table>"
        "<div id='a'></div>"
        "<div id='b'></div><p>content</p>"
    )

    assert sections(document) == [("Item 2.", "b", "content")]


def test_raises_when_every_cited_target_is_dangling_or_empty() -> None:
    document = "<table>" + _row("Item 1.", "missing") + "</table>"

    with pytest.raises(FilingSectioningError, match="no cited location"):
        extract_filing_sections(make_retrieved(document))


def test_sectioning_rejects_unsupported_content_types() -> None:
    document = "<table>" + _row("Item 1.", "a") + "</table><div id='a'></div><p>x</p>"

    with pytest.raises(FilingSectioningError, match="application/pdf"):
        extract_filing_sections(
            make_retrieved(document, content_type="application/pdf")
        )


def test_sectioning_adds_no_source_and_keeps_the_filings_provenance() -> None:
    document = "<table>" + _row("Item 1.", "a") + "</table><div id='a'></div><p>x</p>"
    retrieved = make_retrieved(document)

    result = extract_filing_sections(retrieved)

    assert result.filing == retrieved.filing
    assert result.sources == retrieved.sources


def real_asml_sections() -> list[tuple[str, str, str]]:
    """Section the recorded excerpt of ASML's reference table and content."""

    return sections(ASML_FIXTURE.read_text())


def test_real_asml_filing_has_two_targets_cited_by_more_than_one_row() -> None:
    result = real_asml_sections()

    assert len(result) == 6

    by_anchor: dict[str, set[str]] = {}
    for label, anchor, _ in result:
        by_anchor.setdefault(anchor, set()).add(label)

    risk_factors = "i1edf02a2dc3144cf83a1843d2038ab4e_214"
    at_a_glance = "i1edf02a2dc3144cf83a1843d2038ab4e_22"
    assert len(by_anchor[risk_factors]) == 3
    assert len(by_anchor[at_a_glance]) == 2


def test_real_asml_overlapping_sections_carry_identical_text() -> None:
    result = real_asml_sections()

    risk_factors_texts = {
        text
        for _, anchor, text in result
        if anchor == "i1edf02a2dc3144cf83a1843d2038ab4e_214"
    }

    assert len(risk_factors_texts) == 1
    assert "The risk factors outlined in this section" in next(iter(risk_factors_texts))


def test_real_asml_label_is_built_from_the_row_since_only_the_page_links() -> None:
    result = real_asml_sections()

    labels = {label for label, _, _ in result}
    assert "D. Risk Factors Risk – Risk factors" in labels
    assert "B. Business Overview At a glance" in labels


def real_nvda_sections() -> list[tuple[str, str, str]]:
    """Section the recorded excerpt of NVIDIA's table of contents and content."""

    return sections(NVDA_FIXTURE.read_text())


def test_real_nvda_filing_yields_two_non_overlapping_sections() -> None:
    result = real_nvda_sections()

    assert [label for label, _, _ in result] == [
        "Item 1. Business",
        "Item 1A. Risk Factors",
    ]
    assert result[0][1] != result[1][1]


def test_real_nvda_first_section_is_exactly_bounded_by_the_next_anchor() -> None:
    """Item 1.'s content must stop before Item 1A.'s heading, and must not be
    truncated early by the unreferenced marker inside it."""

    text = real_nvda_sections()[0][2]

    assert text.startswith("Item 1. Business\nOur Company")
    assert "Blackwell architecture" in text
    assert "Item 1A" not in text


def test_real_nvda_second_section_starts_at_its_own_heading() -> None:
    text = real_nvda_sections()[1][2]

    assert text.startswith("Item 1A. Risk Factors\n")
    assert "Risks Related to Our Industry and Markets" in text
