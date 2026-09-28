"""Tests for the embedder pipeline component.

The SentenceTransformer model is mocked to avoid downloading weights during CI.
Tests verify the embed_chunks interface and output shape, not embedding quality.
"""
from unittest.mock import MagicMock, patch

import numpy as np

import hypersmell.pipeline.embedder as embedder_module
from hypersmell.pipeline.embedder import embed_chunks


def _make_mock_model(dim: int = 384):
    """Build a mock SentenceTransformer that returns fake embeddings."""
    mock = MagicMock()
    mock.encode.side_effect = lambda texts, **kwargs: np.zeros((len(texts), dim))
    return mock


def test_embed_single_chunk():
    """embed_chunks returns a single chunk with a 384-dim embedding vector."""
    chunks = [{"content": "Bergamot top note.", "chunk_index": 0}]
    mock_model = _make_mock_model(dim=384)

    # Reset cached model so our mock is used
    original = embedder_module._model
    embedder_module._model = mock_model
    try:
        result = embed_chunks(chunks)
    finally:
        embedder_module._model = original

    assert len(result) == 1
    assert "embedding" in result[0]
    assert len(result[0]["embedding"]) == 384


def test_embed_multiple_chunks():
    """embed_chunks returns embeddings for every input chunk."""
    chunks = [
        {"content": "Top note: bergamot.", "chunk_index": 0},
        {"content": "Heart note: rose.", "chunk_index": 1},
        {"content": "Base note: sandalwood.", "chunk_index": 2},
    ]
    mock_model = _make_mock_model(dim=384)

    original = embedder_module._model
    embedder_module._model = mock_model
    try:
        result = embed_chunks(chunks)
    finally:
        embedder_module._model = original

    assert len(result) == 3
    for chunk in result:
        assert "embedding" in chunk
        assert len(chunk["embedding"]) == 384


def test_embed_empty_list():
    """embed_chunks returns an empty list when given no chunks."""
    result = embed_chunks([])
    assert result == []


def test_embed_preserves_existing_fields():
    """embed_chunks does not strip other fields from chunk dicts."""
    chunks = [
        {
            "content": "Patchouli base note.",
            "chunk_index": 0,
            "metadata": {"source": "supplier_catalog"},
        }
    ]
    mock_model = _make_mock_model(dim=384)

    original = embedder_module._model
    embedder_module._model = mock_model
    try:
        result = embed_chunks(chunks)
    finally:
        embedder_module._model = original

    assert result[0]["metadata"] == {"source": "supplier_catalog"}
    assert result[0]["chunk_index"] == 0


def test_embed_embedding_is_list_of_floats():
    """Embedding vectors are plain Python lists of floats (JSON-serialisable)."""
    chunks = [{"content": "Oud oil from Cambodia.", "chunk_index": 0}]
    mock_model = _make_mock_model(dim=384)

    original = embedder_module._model
    embedder_module._model = mock_model
    try:
        result = embed_chunks(chunks)
    finally:
        embedder_module._model = original

    embedding = result[0]["embedding"]
    assert isinstance(embedding, list)
    assert all(isinstance(v, float) for v in embedding)


def test_get_model_caches_instance():
    """get_model returns the same object on repeated calls (lazy singleton)."""
    from hypersmell.pipeline.embedder import get_model

    with patch("hypersmell.pipeline.embedder.SentenceTransformer") as MockST:
        MockST.return_value = MagicMock()
        # Reset module-level cache
        original = embedder_module._model
        embedder_module._model = None
        try:
            m1 = get_model()
            m2 = get_model()
            assert m1 is m2
            MockST.assert_called_once()
        finally:
            embedder_module._model = original
