"""Deterministic splitting of a sectioned filing into retrievable chunks.

Chunking runs within one already-identified ``FilingSection`` rather than
across the whole document, since sectioning already supplies the structural
boundaries (Item 1A, Item 7, ...) that retrieval should respect. Each
section's text is split into overlapping, word-boundary-aligned windows so
retrieval can return a precise passage instead of an entire section.
"""

from equity_research_agent.models.filings import FilingChunk, SectionedFiling


def chunk_filing_sections(
    sectioned: SectionedFiling,
    *,
    chunk_size: int = 1500,
    overlap: int = 200,
) -> tuple[FilingChunk, ...]:
    """Split every section of ``sectioned`` into overlapping text windows.

    ``chunk_size`` and ``overlap`` are character counts. A window never
    splits a word: it accumulates whole words up to ``chunk_size``, then the
    next window starts far enough back to repeat roughly ``overlap``
    characters of trailing context. A single word longer than ``chunk_size``
    still becomes its own, oversized chunk rather than being split, since
    breaking a word would make it unembeddable as meaningful text.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must not be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[FilingChunk] = []
    for section in sectioned.sections:
        windows = _split_into_windows(section.text, chunk_size, overlap)
        for chunk_index, window in enumerate(windows):
            chunks.append(
                FilingChunk(
                    filing=sectioned.filing,
                    section_label=section.label,
                    section_anchor_id=section.anchor_id,
                    item_identifier=section.item_identifier,
                    chunk_index=chunk_index,
                    text=window,
                    sources=sectioned.sources,
                )
            )

    return tuple(chunks)


def _split_into_windows(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split ``text`` into overlapping, word-boundary-aligned windows."""

    words = text.split()
    if not words:
        return []

    windows: list[str] = []
    start = 0
    word_count = len(words)

    while start < word_count:
        end = _window_end(words, start, chunk_size)
        windows.append(" ".join(words[start:end]))
        if end >= word_count:
            break
        start = _next_start(words, start, end, overlap)

    return windows


def _window_end(words: list[str], start: int, chunk_size: int) -> int:
    """Return the exclusive end index of the word window starting at ``start``."""

    length = len(words[start])
    end = start + 1
    while end < len(words):
        added_length = length + 1 + len(words[end])
        if added_length > chunk_size:
            break
        length = added_length
        end += 1
    return end


def _next_start(words: list[str], start: int, end: int, overlap: int) -> int:
    """Return the next window's start index, stepping back for overlap.

    Falls back to ``end`` (no overlap) when the current window is too short
    to supply ``overlap`` characters of trailing context without stepping
    back past ``start``, which would otherwise stall progress.
    """

    overlap_length = 0
    back = end
    while back > start and overlap_length < overlap:
        back -= 1
        overlap_length += len(words[back]) + 1

    return back if back > start else end
