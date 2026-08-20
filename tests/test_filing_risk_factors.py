"""Tests for selecting a filing's uniquely identified Risk Factors section."""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import HttpUrl

from equity_research_agent.filings import (
    RiskFactorsSectionUnavailableReason,
    extract_filing_sections,
    select_risk_factors_section,
)
from equity_research_agent.models.filings import (
    FilingReference,
    FilingSection,
    RetrievedFiling,
    SectionedFiling,
)
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
DOCUMENT_URL = HttpUrl(
    "https://www.sec.gov/Archives/edgar/data/937966/"
    "000093796626000008/asml-20251231.htm"
)
_RISKS_CAPTION_10_K = """
<html><body>
<div id="business"></div><p>Business discussion.</p>
<div id="risks"></div><p>Disclosed risks.</p>
<table>
  <tr><th></th><th></th><th>Page</th></tr>
  <tr>
    <td><a href="#business">Item 1.</a></td>
    <td><a href="#business">Business</a></td>
    <td><a href="#business">1</a></td>
  </tr>
  <tr>
    <td><a href="#risks">Item 1A.</a></td>
    <td><a href="#risks">Risks</a></td>
    <td><a href="#risks">2</a></td>
  </tr>
</table>
</body></html>
"""


def _filing(form_type: Literal["10-K", "20-F"] = "20-F") -> FilingReference:
    return FilingReference(
        cik="937966",
        form_type=form_type,
        accession_number="0000937966-26-000008",
        period_end=date(2025, 12, 31),
        filed_on=date(2026, 2, 11),
        document_url=DOCUMENT_URL,
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


def _source() -> SourceReference:
    return SourceReference(
        provider="sec_edgar",
        source_type="annual_report_document",
        source_id="0000937966-26-000008",
        url=DOCUMENT_URL,
        retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        period_end=date(2025, 12, 31),
    )


def _sectioned(
    *sections: FilingSection, form_type: Literal["10-K", "20-F"] = "20-F"
) -> SectionedFiling:
    return SectionedFiling(
        filing=_filing(form_type), sections=sections, sources=(_source(),)
    )


def _sections_from_fixture(
    path: Path, form_type: Literal["10-K", "20-F"] = "20-F"
) -> SectionedFiling:
    document = path.read_text()
    return extract_filing_sections(
        RetrievedFiling(
            filing=_filing(form_type),
            content_type="text/html",
            byte_size=len(document.encode()),
            untrusted_text=document,
            sources=(_source(),),
        )
    )


def test_selects_an_expected_item_without_reading_its_display_caption() -> None:
    """This synthetic caption tests the selector boundary, not SEC compliance."""

    expected = FilingSection(
        label="Risks",
        anchor_id="risk",
        text="disclosed risks",
        item_identifier="1A",
    )

    selected = select_risk_factors_section(
        _sectioned(
            FilingSection(label="Business", anchor_id="business", text="overview"),
            expected,
            form_type="10-K",
        )
    )

    assert selected.section == expected
    assert selected.unavailable_reason is None


def test_routes_a_10k_risks_caption_through_item_1a_metadata() -> None:
    sectioned = extract_filing_sections(
        RetrievedFiling(
            filing=_filing("10-K"),
            content_type="text/html",
            byte_size=len(_RISKS_CAPTION_10_K.encode()),
            untrusted_text=_RISKS_CAPTION_10_K,
            sources=(_source(),),
        )
    )

    selected = select_risk_factors_section(sectioned)

    assert selected.section is not None
    assert selected.section.label == "Item 1A. Risks"
    assert selected.section.item_identifier == "1A"
    assert selected.section.anchor_id == "risks"
    assert selected.section.text.startswith("Disclosed risks.")


def test_duplicate_expected_items_for_one_anchor_select_the_first_section() -> None:
    first = FilingSection(
        label="D. Risk Factors Risk – Risk factors",
        anchor_id="risk",
        text="disclosed risks",
        item_identifier="3.D",
    )

    selected = select_risk_factors_section(
        _sectioned(
            first,
            FilingSection(
                label="Risk – Risk factors",
                anchor_id="risk",
                text="disclosed risks",
                item_identifier="3.D",
            ),
        )
    )

    assert selected.section == first
    assert selected.unavailable_reason is None


def test_returns_missing_item_reason_without_title_fallback() -> None:
    sectioned = _sectioned(
        FilingSection(
            label="Risk Factors",
            anchor_id="risk",
            text="disclosed risks",
            item_identifier="1B",
        ),
        form_type="10-K",
    )

    selection = select_risk_factors_section(sectioned)

    assert selection.section is None
    assert (
        selection.unavailable_reason
        is RiskFactorsSectionUnavailableReason.EXPECTED_ITEM_NOT_FOUND
    )


def test_returns_ambiguous_anchor_reason() -> None:
    sectioned = _sectioned(
        FilingSection(
            label="Risks", anchor_id="first", text="first", item_identifier="1A"
        ),
        FilingSection(
            label="Risk summary",
            anchor_id="second",
            text="two",
            item_identifier="1A",
        ),
        form_type="10-K",
    )

    selection = select_risk_factors_section(sectioned)

    assert selection.section is None
    assert (
        selection.unavailable_reason
        is RiskFactorsSectionUnavailableReason.MULTIPLE_EXPECTED_ITEM_ANCHORS
    )


def test_returns_conflicting_text_reason() -> None:
    sectioned = _sectioned(
        FilingSection(
            label="Risk Factors", anchor_id="risk", text="first", item_identifier="3.D"
        ),
        FilingSection(
            label="Risk Factors", anchor_id="risk", text="second", item_identifier="3.D"
        ),
    )

    selection = select_risk_factors_section(sectioned)

    assert selection.section is None
    assert (
        selection.unavailable_reason
        is RiskFactorsSectionUnavailableReason.CONFLICTING_EXPECTED_ITEM_TEXT
    )


def test_selects_asmls_item_3d_risk_factor_anchor() -> None:
    selected = select_risk_factors_section(_sections_from_fixture(ASML_FIXTURE))

    assert selected.section is not None
    assert selected.section.anchor_id == "i1edf02a2dc3144cf83a1843d2038ab4e_214"
    assert selected.section.label == "D. Risk Factors Risk – Risk factors"
    assert selected.section.item_identifier == "3.D"
    assert "The risk factors outlined in this section" in selected.section.text


def test_selects_nvidias_risk_factors_section() -> None:
    selected = select_risk_factors_section(
        _sections_from_fixture(NVDA_FIXTURE, form_type="10-K")
    )

    assert selected.section is not None
    assert selected.section.label == "Item 1A. Risk Factors"
    assert selected.section.item_identifier == "1A"
    assert selected.section.text.startswith("Item 1A. Risk Factors\n")
