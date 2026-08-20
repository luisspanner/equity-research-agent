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

from bs4 import BeautifulSoup
from bs4.element import Tag

from equity_research_agent.filings.text import _extract_html_text
from equity_research_agent.models.filings import (
    FilingSection,
    RetrievedFiling,
    SectionedFiling,
)

_ID_ATTRIBUTE = re.compile(r"""<[a-zA-Z][\w:-]*\b[^>]*\sid=(["'])(.+?)\1""")


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
    entries = _index_entries(soup)
    if not entries:
        raise FilingSectioningError("filing carries no internal sectioning links")

    positions = _marker_positions(document, {target for _, target in entries})
    ordered_offsets = sorted(set(positions.values()))

    sections: list[FilingSection] = []
    for label, target in entries:
        start = positions.get(target)
        if start is None:
            continue
        end = next(
            (offset for offset in ordered_offsets if offset > start), len(document)
        )
        text = _extract_html_text(document[start:end])
        if not text:
            continue
        sections.append(FilingSection(label=label, anchor_id=target, text=text))

    if not sections:
        raise FilingSectioningError("no cited location produced readable text")

    return SectionedFiling(
        filing=retrieved.filing,
        sections=tuple(sections),
        sources=retrieved.sources,
    )


def _index_entries(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Return one (label, anchor id) pair per distinct target each row cites.

    A row citing exactly one target is labelled from all of the row's own
    text, page numbers excepted, not only the linked cell's text: ASML links
    only the page-number cell, NVIDIA links every cell, and using just the
    linked text would lose the caption for ASML. A row citing more than one
    target -- not seen in either filer sampled, but not ruled out -- falls
    back to labelling each target from only the cells that link to it, to
    avoid attributing one target's label to another.
    """

    entries: list[tuple[str, str]] = []
    for row in soup.find_all("tr"):
        if not isinstance(row, Tag):
            continue
        links = [
            link
            for link in row.find_all("a")
            if isinstance(link, Tag) and _internal_target(link) is not None
        ]
        if not links:
            continue

        targets: list[str] = []
        for link in links:
            target = _internal_target(link)
            if target is not None and target not in targets:
                targets.append(target)

        if len(targets) == 1:
            label = _clean_label(cell.get_text() for cell in row.find_all(("td", "th")))
            if label:
                entries.append((label, targets[0]))
            continue

        for target in targets:
            fragments = (
                link.get_text() for link in links if _internal_target(link) == target
            )
            label = _clean_label(fragments)
            if label:
                entries.append((label, target))

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
