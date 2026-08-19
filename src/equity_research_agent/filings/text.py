"""Deterministic extraction of readable text from retrieved filing documents."""

from collections.abc import Iterable

from bs4 import BeautifulSoup
from bs4.element import Tag

from equity_research_agent.models.filings import FilingText, RetrievedFiling

_NON_CONTENT_TAGS = ("head", "script", "style", "ix:header", "ix:hidden")

# Marks a block boundary while text is extracted. Newlines cannot serve as the
# marker: filing HTML wraps prose across source lines, and those line breaks are
# formatting rather than structure.
_BLOCK_SEPARATOR = "\x00"

_CELL_TAGS = ("td", "th")

_BLOCK_TAGS = (
    "p",
    "div",
    "tr",
    "li",
    "table",
    "section",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)


class FilingTextExtractionError(ValueError):
    """Raised when a retrieved filing yields no readable text."""


def extract_filing_text(retrieved: RetrievedFiling) -> FilingText:
    """Extract readable text from a retrieved filing, preserving its provenance.

    Extraction is a representation change, not an interpretation: nothing is
    summarized, reordered, or judged. The result keeps the document's sources so
    later sectioning and citation remain traceable to the filing.
    """

    if retrieved.content_type == "text/html":
        text = _extract_html_text(retrieved.untrusted_text)
    elif retrieved.content_type == "text/plain":
        text = _normalize_whitespace(retrieved.untrusted_text)
    else:
        raise FilingTextExtractionError(
            f"cannot extract text from content type {retrieved.content_type}"
        )

    if not text:
        raise FilingTextExtractionError("filing document contains no readable text")

    return FilingText(
        filing=retrieved.filing,
        untrusted_text=text,
        sources=retrieved.sources,
    )


def _extract_html_text(document: str) -> str:
    """Convert filing HTML into text with one line per block-level element.

    Text nodes are joined without an added separator, matching how a browser
    renders inline content: adjacent inline elements with no whitespace between
    them are one word, and filers put the spacing they mean into the text
    itself. Measured against ASML's 2025 Form 20-F, joining with a space instead
    produced about a thousand spurious spaces before punctuation and split
    hundreds of words, while preventing no fusion at all.

    Table cells are the exception. A bare cell boundary carries no source
    whitespace, so cells emit a space and rows end a line.
    """

    soup = BeautifulSoup(document.replace(_BLOCK_SEPARATOR, ""), "html.parser")

    _remove(soup.find_all(_NON_CONTENT_TAGS))
    _remove(soup.find_all(_is_hidden))

    for line_break in soup.find_all("br"):
        line_break.replace_with(_BLOCK_SEPARATOR)
    for cell in soup.find_all(_CELL_TAGS):
        cell.append(" ")
    for block in soup.find_all(_BLOCK_TAGS):
        block.append(_BLOCK_SEPARATOR)

    return _normalize_blocks(soup.get_text(separator=""))


def _remove(tags: Iterable[Tag]) -> None:
    """Delete tags whose contents are metadata or presentation, not filing text."""

    for tag in tags:
        if not tag.decomposed:
            tag.decompose()


def _is_hidden(tag: Tag) -> bool:
    """Report whether a tag is hidden from readers, as inline XBRL values are."""

    style = tag.get("style")
    if not isinstance(style, str):
        return False
    return "display:none" in style.replace(" ", "").lower()


def _normalize_blocks(text: str) -> str:
    """Return one line per marked block, with each block's whitespace collapsed."""

    return _join_nonempty(text.split(_BLOCK_SEPARATOR))


def _normalize_whitespace(text: str) -> str:
    """Collapse whitespace runs into single spaces and drop empty lines."""

    return _join_nonempty(text.splitlines())


def _join_nonempty(segments: Iterable[str]) -> str:
    lines = []
    for segment in segments:
        line = " ".join(segment.replace("\xa0", " ").split())
        if line:
            lines.append(line)
    return "\n".join(lines)
