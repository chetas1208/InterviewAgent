"""Hybrid BM25 + dense retrieval with Reciprocal Rank Fusion."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np
from pydantic import TypeAdapter

from .models import DocumentChunk, RetrievalResult
from .utils import ensure_dir

EMBEDDINGS_FILE = "embeddings.npy"
RETRIEVER_CONFIG_FILE = "retriever_config.json"
CHUNKS_FILE = "chunks.json"


class EmbeddingModel(Protocol):
    """Minimal protocol implemented by sentence-transformers and test fakes."""

    def encode(self, sentences: str | list[str], **kwargs: object) -> np.ndarray:
        """Return dense vector embeddings."""


def tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 with a stable, dependency-light regex."""

    return re.findall(r"[a-zA-Z0-9+#.]+", text.lower())


class _SimpleBM25:
    """Small fallback if rank-bm25 is unavailable."""

    def __init__(self, corpus: list[list[str]]) -> None:
        self.corpus = corpus
        self.doc_freq: dict[str, int] = {}
        for doc in corpus:
            for token in set(doc):
                self.doc_freq[token] = self.doc_freq.get(token, 0) + 1
        self.doc_count = max(len(corpus), 1)

    def get_scores(self, query_tokens: list[str]) -> np.ndarray:
        scores: list[float] = []
        for doc in self.corpus:
            counts = {token: doc.count(token) for token in set(doc)}
            score = 0.0
            for token in query_tokens:
                if token not in counts:
                    continue
                idf = math.log((self.doc_count + 1) / (self.doc_freq.get(token, 0) + 1)) + 1
                score += counts[token] * idf
            scores.append(score)
        return np.array(scores, dtype=float)


def _build_bm25(tokenized_chunks: list[list[str]]) -> object:
    try:
        from rank_bm25 import BM25Okapi

        return BM25Okapi(tokenized_chunks)
    except Exception:
        return _SimpleBM25(tokenized_chunks)


def _normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HybridRetriever:
    """Hybrid retriever for exact keyword and semantic interview context."""

    def __init__(
        self,
        chunks: list[DocumentChunk],
        *,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cross_encoder_model_name: str | None = None,
        embedding_model: EmbeddingModel | None = None,
        embeddings: np.ndarray | None = None,
        build_dense: bool = True,
    ) -> None:
        self.chunks = chunks
        self.embedding_model_name = embedding_model_name
        self.cross_encoder_model_name = cross_encoder_model_name
        self.embedding_model = embedding_model
        self.cross_encoder = None
        self.tokenized_chunks = [tokenize(chunk.text) for chunk in chunks]
        self.bm25 = _build_bm25(self.tokenized_chunks)
        self.embeddings: np.ndarray | None = None

        if embeddings is not None:
            self.embeddings = _normalize_matrix(np.asarray(embeddings, dtype=float))
        elif build_dense and chunks:
            self.embeddings = self._build_dense_embeddings()

    def _load_embedding_model(self) -> EmbeddingModel | None:
        if self.embedding_model is not None:
            return self.embedding_model
        try:
            from sentence_transformers import SentenceTransformer

            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            return self.embedding_model
        except Exception:
            return None

    def _build_dense_embeddings(self) -> np.ndarray | None:
        model = self._load_embedding_model()
        if model is None:
            return None
        embeddings = model.encode([chunk.text for chunk in self.chunks], convert_to_numpy=True, show_progress_bar=False)
        return _normalize_matrix(np.asarray(embeddings, dtype=float))

    def retrieve_bm25(self, query: str, top_k: int = 8) -> list[RetrievalResult]:
        """Retrieve chunks using exact keyword matching."""

        if not self.chunks:
            return []
        query_tokens = tokenize(query)
        query_token_set = set(query_tokens)
        raw_scores = np.asarray(self.bm25.get_scores(query_tokens), dtype=float)
        overlaps = np.array(
            [len(query_token_set.intersection(tokens)) for tokens in self.tokenized_chunks],
            dtype=float,
        )
        # rank-bm25 can return zero for exact matches in tiny corpora; the tiny
        # boost preserves BM25 ordering while making exact-match ties useful.
        scores = raw_scores + (overlaps * 1e-6)
        order = np.lexsort((np.arange(len(scores)), -overlaps, -scores))[:top_k]
        results: list[RetrievalResult] = []
        for rank, idx in enumerate(order, start=1):
            if scores[idx] <= 0 and overlaps[idx] <= 0:
                continue
            chunk = self.chunks[int(idx)]
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=float(scores[idx]),
                    rank=rank,
                    method="bm25",
                    reason="BM25 matched exact terms such as stack names, tools, companies, or role keywords.",
                )
            )
        return results

    def retrieve_dense(self, query: str, top_k: int = 8) -> list[RetrievalResult]:
        """Retrieve chunks using dense semantic similarity."""

        if not self.chunks:
            return []
        if self.embeddings is None:
            self.embeddings = self._build_dense_embeddings()
        model = self._load_embedding_model()
        if self.embeddings is None or model is None:
            return []

        query_embedding = np.asarray(model.encode(query, convert_to_numpy=True), dtype=float)
        if query_embedding.ndim > 1:
            query_embedding = query_embedding[0]
        norm = np.linalg.norm(query_embedding)
        if norm:
            query_embedding = query_embedding / norm
        scores = self.embeddings @ query_embedding
        order = np.argsort(-scores, kind="mergesort")[:top_k]
        return [
            RetrievalResult(
                chunk=self.chunks[int(idx)],
                score=float(scores[idx]),
                rank=rank,
                method="dense",
                reason="Dense retrieval matched semantic intent beyond exact wording.",
            )
            for rank, idx in enumerate(order, start=1)
        ]

    @staticmethod
    def reciprocal_rank_fusion(results_lists: Iterable[list[RetrievalResult]], k: int = 60) -> list[RetrievalResult]:
        """Merge ranked result lists without comparing incompatible raw scores."""

        fused_scores: dict[str, float] = {}
        best_result: dict[str, RetrievalResult] = {}
        reasons: dict[str, list[str]] = {}

        for results in results_lists:
            for result in results:
                chunk_id = result.chunk.id
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (k + result.rank)
                if chunk_id not in best_result or result.rank < best_result[chunk_id].rank:
                    best_result[chunk_id] = result
                reasons.setdefault(chunk_id, []).append(result.method)

        ordered = sorted(
            fused_scores,
            key=lambda chunk_id: (
                -fused_scores[chunk_id],
                best_result[chunk_id].chunk.source_file,
                best_result[chunk_id].chunk.chunk_index,
                chunk_id,
            ),
        )

        fused: list[RetrievalResult] = []
        for rank, chunk_id in enumerate(ordered, start=1):
            original = best_result[chunk_id]
            methods = sorted(set(reasons[chunk_id]))
            fused.append(
                RetrievalResult(
                    chunk=original.chunk,
                    score=fused_scores[chunk_id],
                    rank=rank,
                    method="rrf",
                    reason=f"Combined rankings from {', '.join(methods)} using Reciprocal Rank Fusion.",
                )
            )
        return fused

    def rerank_with_cross_encoder(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_n: int = 8,
    ) -> list[RetrievalResult]:
        """Optionally rerank candidates with a sentence-transformers CrossEncoder."""

        if not candidates or not self.cross_encoder_model_name:
            return candidates[:top_n]
        try:
            from sentence_transformers import CrossEncoder

            if self.cross_encoder is None:
                self.cross_encoder = CrossEncoder(self.cross_encoder_model_name)
            pairs = [(query, result.chunk.text) for result in candidates]
            scores = self.cross_encoder.predict(pairs)
        except Exception:
            return candidates[:top_n]

        reranked = []
        for result, score in zip(candidates, scores, strict=False):
            reranked.append(
                result.model_copy(
                    update={
                        "score": float(score),
                        "method": "cross_encoder",
                        "reason": "Cross-encoder reranked this chunk for question-specific relevance.",
                    }
                )
            )
        reranked.sort(key=lambda result: (-result.score, result.chunk.source_file, result.chunk.chunk_index))
        return [result.model_copy(update={"rank": rank}) for rank, result in enumerate(reranked[:top_n], start=1)]

    def retrieve(self, query: str, top_k: int = 8) -> list[RetrievalResult]:
        """Retrieve the top context chunks for an interview question."""

        candidate_k = max(20, top_k * 3)
        bm25_results = self.retrieve_bm25(query, candidate_k)
        dense_results = self.retrieve_dense(query, candidate_k)
        fused = self.reciprocal_rank_fusion([bm25_results, dense_results])
        if not fused:
            return []
        return self.rerank_with_cross_encoder(query, fused[:candidate_k], top_n=top_k)

    def save(self, artifacts_dir: Path) -> None:
        """Persist chunks, embeddings, and retriever config."""

        ensure_dir(artifacts_dir)
        (artifacts_dir / CHUNKS_FILE).write_text(
            json.dumps([chunk.model_dump() for chunk in self.chunks], indent=2),
            encoding="utf-8",
        )
        if self.embeddings is not None:
            np.save(artifacts_dir / EMBEDDINGS_FILE, self.embeddings)
        config = {
            "embedding_model_name": self.embedding_model_name,
            "cross_encoder_model_name": self.cross_encoder_model_name,
            "has_embeddings": self.embeddings is not None,
        }
        (artifacts_dir / RETRIEVER_CONFIG_FILE).write_text(json.dumps(config, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, artifacts_dir: Path, *, build_dense: bool = True) -> "HybridRetriever":
        """Load a retriever from local artifacts."""

        chunks_path = artifacts_dir / CHUNKS_FILE
        if not chunks_path.exists():
            raise FileNotFoundError(f"Missing {chunks_path}. Run ingest first.")
        chunks = TypeAdapter(list[DocumentChunk]).validate_json(chunks_path.read_text(encoding="utf-8"))

        config_path = artifacts_dir / RETRIEVER_CONFIG_FILE
        config = {}
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))

        embeddings = None
        embeddings_path = artifacts_dir / EMBEDDINGS_FILE
        if embeddings_path.exists():
            embeddings = np.load(embeddings_path)

        return cls(
            chunks,
            embedding_model_name=config.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2"),
            cross_encoder_model_name=config.get("cross_encoder_model_name"),
            embeddings=embeddings,
            build_dense=build_dense and embeddings is None,
        )
