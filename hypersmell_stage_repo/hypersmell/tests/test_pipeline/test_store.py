"""Tests for the chunk store pipeline component.

The Chunk model uses pgvector's Vector(384) column which is not supported by
SQLite. These tests mock the database session so they pass in any environment.
Against a real Postgres instance with pgvector, the session mock can be removed.
"""
import uuid
from unittest.mock import MagicMock

from hypersmell.pipeline.store import store_chunks


def _make_chunks(n: int = 2) -> list[dict]:
    """Build fake embedded chunk dicts."""
    return [
        {
            "content": f"Chunk content {i}.",
            "chunk_index": i,
            "embedding": [0.0] * 384,
            "metadata": {"position": i},
        }
        for i in range(n)
    ]


def test_store_chunks():
    """store_chunks calls session.add for each chunk and commits once."""
    session = MagicMock()
    resource_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    chunks = _make_chunks(3)

    result = store_chunks(
        session=session,
        chunks=chunks,
        resource_id=resource_id,
        workspace_id=workspace_id,
        source="supplier_catalog",
    )

    assert session.add.call_count == 3
    session.commit.assert_called_once()
    assert len(result) == 3


def test_store_empty_chunks():
    """store_chunks with an empty list commits nothing and returns empty list."""
    session = MagicMock()
    resource_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    result = store_chunks(
        session=session,
        chunks=[],
        resource_id=resource_id,
        workspace_id=workspace_id,
        source="supplier_catalog",
    )

    session.add.assert_not_called()
    session.commit.assert_called_once()
    assert result == []


def test_store_preserves_metadata():
    """store_chunks creates Chunk objects with the correct metadata."""
    from hypersmell.models import Chunk

    session = MagicMock()
    resource_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    chunks = [
        {
            "content": "Labdanum from Crete.",
            "chunk_index": 0,
            "embedding": [0.5] * 384,
            "metadata": {"supplier": "Givaudan", "grade": "premium"},
        }
    ]

    added_chunks = []
    session.add.side_effect = lambda obj: added_chunks.append(obj)

    store_chunks(
        session=session,
        chunks=chunks,
        resource_id=resource_id,
        workspace_id=workspace_id,
        source="supplier_catalog",
    )

    assert len(added_chunks) == 1
    chunk = added_chunks[0]
    assert isinstance(chunk, Chunk)
    assert chunk.content == "Labdanum from Crete."
    assert chunk.doc_metadata == {"supplier": "Givaudan", "grade": "premium"}
    assert chunk.resource_id == resource_id
    assert chunk.workspace_id == workspace_id
    assert chunk.source == "supplier_catalog"
    assert chunk.chunk_index == 0


def test_store_chunk_index_preserved():
    """store_chunks preserves the chunk_index from each input dict."""

    session = MagicMock()
    added_chunks = []
    session.add.side_effect = lambda obj: added_chunks.append(obj)

    chunks = _make_chunks(4)
    store_chunks(
        session=session,
        chunks=chunks,
        resource_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        source="tasting_notes",
    )

    indices = [c.chunk_index for c in added_chunks]
    assert indices == [0, 1, 2, 3]


def test_store_source_field():
    """store_chunks passes the source string through to each Chunk."""

    session = MagicMock()
    added_chunks = []
    session.add.side_effect = lambda obj: added_chunks.append(obj)

    store_chunks(
        session=session,
        chunks=_make_chunks(1),
        resource_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        source="tasting_notes",
    )

    assert added_chunks[0].source == "tasting_notes"
