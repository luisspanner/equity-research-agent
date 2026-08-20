"""Deterministic selection of one filing's disclosed-risk section.

The form-item mapping is defined by the SEC forms, not inferred from a
particular filer's display caption or HTML structure. The section metadata it
uses still comes only from filing-index structures that the sectioner has
explicitly recognized.
"""

from dataclasses import dataclass
from enum import StrEnum

from equity_research_agent.models.filings import FilingSection, SectionedFiling

_RISK_ITEM_BY_FORM = {
    "10-K": "1A",
    "20-F": "3.D",
}


class RiskFactorsSectionUnavailableReason(StrEnum):
    """Why a filing could not supply one safe disclosed-risk section."""

    EXPECTED_ITEM_NOT_FOUND = "expected_item_not_found"
    MULTIPLE_EXPECTED_ITEM_ANCHORS = "multiple_expected_item_anchors"
    CONFLICTING_EXPECTED_ITEM_TEXT = "conflicting_expected_item_text"


@dataclass(frozen=True)
class RiskFactorsSectionSelection:
    """One selected risk section or an explicit reason it is unavailable.

    Missing or ambiguous filing metadata is an expected evidence limitation,
    not an exception that a future research workflow should turn into a failed
    run. Exactly one of ``section`` and ``unavailable_reason`` is present.
    """

    section: FilingSection | None = None
    unavailable_reason: RiskFactorsSectionUnavailableReason | None = None

    def __post_init__(self) -> None:
        if (self.section is None) == (self.unavailable_reason is None):
            raise ValueError(
                "exactly one of section and unavailable_reason must be provided"
            )

    @property
    def is_available(self) -> bool:
        """Whether a uniquely identified disclosed-risk section is present."""

        return self.section is not None


def select_risk_factors_section(
    sectioned: SectionedFiling,
) -> RiskFactorsSectionSelection:
    """Select one disclosed-risk section or return an explicit limitation.

    A 10-K identifies Risk Factors as Item 1A, while a 20-F identifies it as
    Item 3.D. The sectioner's metadata comes from the filing's own index, so
    this selection does not depend on a filer's display wording. Filers can
    cite the same anchored span through several index rows; those duplicate
    entries are one section here when their text agrees. Distinct anchors are
    not ranked because choosing one would turn an evidence-boundary decision
    into an unsupported heuristic.
    """

    expected_item = _RISK_ITEM_BY_FORM[sectioned.filing.form_type]

    matching_sections = [
        section
        for section in sectioned.sections
        if section.item_identifier == expected_item
    ]
    if not matching_sections:
        return RiskFactorsSectionSelection(
            unavailable_reason=RiskFactorsSectionUnavailableReason.EXPECTED_ITEM_NOT_FOUND
        )

    sections_by_anchor: dict[str, list[FilingSection]] = {}
    for section in matching_sections:
        sections_by_anchor.setdefault(section.anchor_id, []).append(section)

    if len(sections_by_anchor) != 1:
        return RiskFactorsSectionSelection(
            unavailable_reason=(
                RiskFactorsSectionUnavailableReason.MULTIPLE_EXPECTED_ITEM_ANCHORS
            )
        )

    matching_anchor_sections = next(iter(sections_by_anchor.values()))
    selected_section = matching_anchor_sections[0]
    if any(
        section.text != selected_section.text
        for section in matching_anchor_sections[1:]
    ):
        return RiskFactorsSectionSelection(
            unavailable_reason=(
                RiskFactorsSectionUnavailableReason.CONFLICTING_EXPECTED_ITEM_TEXT
            )
        )
    return RiskFactorsSectionSelection(section=selected_section)
