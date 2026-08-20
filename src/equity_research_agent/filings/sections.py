"""Deterministic sectioning of a retrieved filing along its own linking index.

Both filers examined so far (ASML's Form 20-F, NVIDIA's Form 10-K) mark
sections the same way: a table whose rows link to empty, positioned marker
elements, with a section's real content in the document that follows, up to
whichever cited marker comes next. This module locates that structure
generically rather than special-casing either filer -- see HANDOFF.md for the
measured findings it is built on, and for what remains unverified against a
filer using a different filing agent.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Tag

from equity_research_agent.filings.text import _extract_html_text
from equity_research_agent.models.filings import (
    FilingSection,
    RetrievedFiling,
    SectionedFiling,
)

_ID_ATTRIBUTE = re.compile(r"""<[a-zA-Z][\w:-]*\b[^>]*\sid=(["'])(.+?)\1""")
_FORM_20_F_HEADERS = (
    "Item",
    "Form 20-F caption",
    "Location in this document",
    "Page",
)
_FORM_10_K_HEADERS = ("", "", "Page")
_FORM_20_F_PARENT_ITEM = re.compile(r"^\d+(?:\.[A-Z])?$")
_FORM_20_F_SUBITEM = re.compile(r"^([A-Z])\.\s+(.+)$")
_FORM_10_K_ITEM = re.compile(r"^Item\s+(\d+[A-Z]?)\.?$")


@dataclass(frozen=True)
class _IndexEntry:
    """One filing-index row and any form structure it exposes."""

    label: str
    target: str
    item_identifier: str | None = None
    form_caption: str | None = None
    location_label: str | None = None


class FilingSectioningError(ValueError):
    """Raised when a retrieved filing carries no discoverable sectioning index."""


def extract_filing_sections(retrieved: RetrievedFiling) -> SectionedFiling:
    """Divide a retrieved filing into labelled sections along its own index.

    The index is any table row that links to an in-document anchor: both
    filers examined use a table of that shape for the same underlying
    mechanism, a legally operative cross-reference table for ASML's 20-F and
    a conventional table of contents for NVIDIA's 10-K. A label's section
    runs from its anchor to whichever cited anchor comes next in the
    document, so a target cited by more than one row yields more than one
    section carrying identical text: sections are spans, not a partition.

    Only table-row-based indices are supported, matching both filers
    examined. Rows whose target does not resolve to an element in the
    document, and spans that render no text, are silently skipped rather than
    treated as errors: both are expected on a real filing's running page
    furniture and on any excerpt trimmed for a fixture.
    """

    if retrieved.content_type != "text/html":
        raise FilingSectioningError(
            f"cannot section content type {retrieved.content_type}"
        )

    document = retrieved.untrusted_text
    soup = BeautifulSoup(document, "html.parser")
    entries = _index_entries(soup, retrieved.filing.form_type)
    if not entries:
        raise FilingSectioningError("filing carries no internal sectioning links")

    positions = _marker_positions(document, {entry.target for entry in entries})
    ordered_offsets = sorted(set(positions.values()))

    sections: list[FilingSection] = []
    for entry in entries:
        start = positions.get(entry.target)
        if start is None:
            continue
        end = next(
            (offset for offset in ordered_offsets if offset > start), len(document)
        )
        text = _extract_html_text(document[start:end])
        if not text:
            continue
        sections.append(
            FilingSection(
                label=entry.label,
                anchor_id=entry.target,
                text=text,
                item_identifier=entry.item_identifier,
                form_caption=entry.form_caption,
                location_label=entry.location_label,
            )
        )

    if not sections:
        raise FilingSectioningError("no cited location produced readable text")

    return SectionedFiling(
        filing=retrieved.filing,
        sections=tuple(sections),
        sources=retrieved.sources,
    )


def _index_entries(
    soup: BeautifulSoup, form_type: str
) -> list[_IndexEntry]:
    """Return one entry per distinct target each filing-index row cites.

    A row citing exactly one target is labelled from all of the row's own
    text, page numbers excepted, not only the linked cell's text: ASML links
    only the page-number cell, NVIDIA links every cell, and using just the
    linked text would lose the caption for ASML. A row citing more than one
    target -- not seen in either filer sampled, but not ruled out -- falls
    back to labelling each target from only the cells that link to it, to
    avoid attributing one target's label to another.
    """

    entries: list[_IndexEntry] = []
    for table in soup.find_all("table"):
        if not isinstance(table, Tag):
            continue

        is_form_20_f_index = form_type == "20-F" and _is_form_20_f_index(table)
        is_form_10_k_index = form_type == "10-K" and _is_form_10_k_index(table)
        parent_item: str | None = None

        for row in _table_rows(table):
            metadata: tuple[str | None, str | None, str | None] = (None, None, None)
            if is_form_20_f_index:
                parent_item, metadata = _form_20_f_row_metadata(row, parent_item)
            elif is_form_10_k_index:
                metadata = _form_10_k_row_metadata(row)

            entries.extend(_row_entries(row, metadata))

    return entries


def _table_rows(table: Tag) -> Iterable[Tag]:
    """Yield rows owned by ``table``, excluding rows of nested tables."""

    for row in table.find_all("tr"):
        if isinstance(row, Tag) and row.find_parent("table") is table:
            yield row


def _direct_cell_texts(row: Tag) -> list[str]:
    """Return normalized text from the row's direct table cells only."""

    return [
        " ".join(cell.get_text().split())
        for cell in row.find_all(("td", "th"), recursive=False)
    ]


def _is_form_20_f_index(table: Tag) -> bool:
    """Identify the measured four-column Form 20-F reference-table shape."""

    return any(
        tuple(_direct_cell_texts(row)) == _FORM_20_F_HEADERS
        for row in _table_rows(table)
    )


def _is_form_10_k_index(table: Tag) -> bool:
    """Identify the measured three-column Form 10-K TOC table shape."""

    return any(
        tuple(_direct_cell_texts(row)) == _FORM_10_K_HEADERS
        for row in _table_rows(table)
    )


def _form_20_f_row_metadata(
    row: Tag, parent_item: str | None
) -> tuple[str | None, tuple[str | None, str | None, str | None]]:
    """Track one Form 20-F parent item and enrich a direct sub-item row."""

    cells = _direct_cell_texts(row)
    if len(cells) != 4:
        return parent_item, (None, None, None)

    item, caption, location, _page = cells
    if _FORM_20_F_PARENT_ITEM.fullmatch(item):
        parent_item = item

    if item or parent_item is None:
        return parent_item, (None, None, None)

    match = _FORM_20_F_SUBITEM.fullmatch(caption)
    if match is None:
        return parent_item, (None, None, None)

    letter, stripped_caption = match.groups()
    return parent_item, (f"{parent_item}.{letter}", stripped_caption, location or None)


def _form_10_k_row_metadata(
    row: Tag,
) -> tuple[str | None, str | None, str | None]:
    """Read an Item identifier and caption from a conventional 10-K TOC row."""

    cells = _direct_cell_texts(row)
    if len(cells) < 2:
        return None, None, None

    match = _FORM_10_K_ITEM.fullmatch(cells[0])
    if match is None or not cells[1]:
        return None, None, None

    return match.group(1), cells[1], None


def _row_entries(
    row: Tag, metadata: tuple[str | None, str | None, str | None]
) -> list[_IndexEntry]:
    """Create entries for a row, retaining metadata only for one target."""

    links = [
        link
        for link in row.find_all("a")
        if isinstance(link, Tag) and _internal_target(link) is not None
    ]
    if not links:
        return []

    targets: list[str] = []
    for link in links:
        target = _internal_target(link)
        if target is not None and target not in targets:
            targets.append(target)

    if len(targets) == 1:
        label = _clean_label(cell.get_text() for cell in row.find_all(("td", "th")))
        if label:
            item_identifier, form_caption, location_label = metadata
            return [
                _IndexEntry(
                    label=label,
                    target=targets[0],
                    item_identifier=item_identifier,
                    form_caption=form_caption,
                    location_label=location_label,
                )
            ]
        return []

    entries: list[_IndexEntry] = []
    for target in targets:
        fragments = (
            link.get_text() for link in links if _internal_target(link) == target
        )
        label = _clean_label(fragments)
        if label:
            entries.append(_IndexEntry(label=label, target=target))
    return entries


def _internal_target(link: Tag) -> str | None:
    """Return the anchor id a link targets, or None if it targets elsewhere."""

    href = link.get("href")
    if isinstance(href, str) and href.startswith("#") and len(href) > 1:
        return href[1:]
    return None


def _clean_label(fragments: Iterable[str]) -> str:
    """Join distinct, non-numeric text fragments into one label string.

    Page numbers are the only fragments this drops: no other row shape
    observed in either filer examined places bare digits in a linked or
    captioned cell.
    """

    seen: list[str] = []
    for fragment in fragments:
        text = " ".join(fragment.split())
        if text and text not in seen and not text.isdigit():
            seen.append(text)
    return " ".join(seen)


def _marker_positions(document: str, targets: set[str]) -> dict[str, int]:
    """Return each target's character offset at its own element's opening tag."""

    positions: dict[str, int] = {}
    for match in _ID_ATTRIBUTE.finditer(document):
        ident = match.group(2)
        if ident in targets and ident not in positions:
            positions[ident] = match.start()
    return positions
