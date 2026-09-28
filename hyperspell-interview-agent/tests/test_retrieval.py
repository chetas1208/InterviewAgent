from __future__ import annotations

import numpy as np

from src.ingest import chunk_text
from src.models import DocumentChunk, RetrievalResult
from src.retrieval import HybridRetriever


class FakeEmbeddingModel:
    def encode(self, sentences, **kwargs):
        if isinstance(sentences, str):
            return self._one(sentences)
        return np.array([self._one(sentence) for sentence in sentences], dtype=float)

    def _one(self, text: str) -> np.ndarray:
        lowered = text.lower()
        if any(term in lowered for term in ("customer", "support", "empathy", "issue")):
            return np.array([1.0, 0.0, 0.0])
        if any(term in lowered for term in ("agent", "memory", "context")):
            return np.array([0.0, 1.0, 0.0])
        return np.array([0.0, 0.0, 1.0])


def make_chunk(text: str, idx: int) -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk-{idx}",
        text=text,
        source_file="test.md",
        section_title="Test",
        chunk_index=idx,
        start_char=0,
        end_char=len(text),
    )


def test_chunking_adds_metadata_and_overlap() -> None:
    text = "# Main\n\n" + ("Qdrant retrieval and React product engineering. " * 250)
    chunks = chunk_text(text, "candidate.md", min_chars=500, max_chars=900, overlap_chars=120)

    assert len(chunks) > 1
    assert chunks[0].source_file == "candidate.md"
    assert chunks[0].section_title == "Main"
    assert chunks[1].start_char < chunks[0].end_char


def test_bm25_returns_exact_keyword_matches() -> None:
    chunks = [
        make_chunk("React frontend and Tailwind interface.", 0),
        make_chunk("Qdrant vector database for retrieval.", 1),
    ]
    retriever = HybridRetriever(chunks, build_dense=False)

    results = retriever.retrieve_bm25("How did you use Qdrant?", top_k=2)

    assert results
    assert results[0].chunk.chunk_index == 1


def test_dense_retrieval_returns_semantic_matches() -> None:
    chunks = [
        make_chunk("I debug customer issues by reproducing reports and checking logs.", 0),
        make_chunk("I built a memory layer for AI agent context.", 1),
    ]
    retriever = HybridRetriever(chunks, embedding_model=FakeEmbeddingModel(), build_dense=True)

    results = retriever.retrieve_dense("How do you handle a support issue?", top_k=2)

    assert results
    assert results[0].chunk.chunk_index == 0


def test_rrf_merges_results_deterministically() -> None:
    a = make_chunk("A", 0)
    b = make_chunk("B", 1)
    bm25 = [
        RetrievalResult(chunk=a, score=10, rank=1, method="bm25"),
        RetrievalResult(chunk=b, score=9, rank=2, method="bm25"),
    ]
    dense = [
        RetrievalResult(chunk=b, score=0.9, rank=1, method="dense"),
        RetrievalResult(chunk=a, score=0.8, rank=2, method="dense"),
    ]

    first = HybridRetriever.reciprocal_rank_fusion([bm25, dense])
    second = HybridRetriever.reciprocal_rank_fusion([bm25, dense])

    assert [result.chunk.id for result in first] == [result.chunk.id for result in second]
    assert {result.chunk.id for result in first} == {"chunk-0", "chunk-1"}
