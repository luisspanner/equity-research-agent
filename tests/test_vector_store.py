"""Tests for cosine similarity and the in-memory vector store."""

from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import HttpUrl

from equity_research_agent.embeddings import (
    InMemoryVectorStore,
    cosine_similarity,
)
from equity_research_agent.models.filings import FilingChunk, FilingReference
from equity_research_agent.models.provenance import SourceReference

DOCUMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/937966/"
    "000093796626000008/asml-20251231.htm"
)


def make_filing(**overrides: Any) -> FilingReference:
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


def make_chunk(text: str, chunk_index: int = 0, **overrides: Any) -> FilingChunk:
    fields: dict[str, Any] = {
        "filing": make_filing(),
        "section_label": "Item 1A. Risk Factors",
        "section_anchor_id": "risk_factors",
        "item_identifier": "1A",
        "chunk_index": chunk_index,
        "text": text,
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
    return FilingChunk(**{**fields, **overrides})


def test_cosine_similarity_of_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_of_opposite_vectors_is_negative_one() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_ignores_magnitude() -> None:
    assert cosine_similarity([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1.0)


def test_cosine_similarity_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosine_similarity_rejects_zero_vector() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([0.0, 0.0], [1.0, 0.0])


def test_search_returns_closest_chunks_first() -> None:
    store = InMemoryVectorStore()
    close = make_chunk("close match")
    far = make_chunk("far match")
    store.add([close, far], [[1.0, 0.0], [0.0, 1.0]])

    results = store.search([0.9, 0.1], top_k=2)

    assert [r.chunk for r in results] == [close, far]
    assert results[0].score > results[1].score


def test_search_respects_top_k() -> None:
    store = InMemoryVectorStore()
    store.add(
        [make_chunk("a"), make_chunk("b"), make_chunk("c")],
        [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
    )

    results = store.search([1.0, 0.0], top_k=2)

    assert len(results) == 2


def test_search_returns_fewer_than_top_k_when_store_is_smaller() -> None:
    store = InMemoryVectorStore()
    store.add([make_chunk("a")], [[1.0, 0.0]])

    results = store.search([1.0, 0.0], top_k=5)

    assert len(results) == 1


def test_search_on_empty_store_returns_empty_list() -> None:
    store = InMemoryVectorStore()

    assert store.search([1.0, 0.0], top_k=3) == []


def test_search_rejects_non_positive_top_k() -> None:
    store = InMemoryVectorStore()
    store.add([make_chunk("a")], [[1.0, 0.0]])

    with pytest.raises(ValueError):
        store.search([1.0, 0.0], top_k=0)


def test_add_rejects_mismatched_chunk_and_vector_counts() -> None:
    store = InMemoryVectorStore()

    with pytest.raises(ValueError):
        store.add([make_chunk("a"), make_chunk("b")], [[1.0, 0.0]])


def test_add_rejects_empty_vector() -> None:
    store = InMemoryVectorStore()

    with pytest.raises(ValueError):
        store.add([make_chunk("a")], [[]])


def test_add_rejects_inconsistent_vector_dimension() -> None:
    store = InMemoryVectorStore()
    store.add([make_chunk("a")], [[1.0, 0.0]])

    with pytest.raises(ValueError):
        store.add([make_chunk("b")], [[1.0, 0.0, 0.0]])


def test_search_rejects_query_vector_of_wrong_dimension() -> None:
    store = InMemoryVectorStore()
    store.add([make_chunk("a")], [[1.0, 0.0]])

    with pytest.raises(ValueError):
        store.search([1.0, 0.0, 0.0], top_k=1)
