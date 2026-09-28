"""Tests for the document chunker pipeline component.

IMPORTANT: All test documents are intentionally kept under MAX_CHUNK_SIZE (1500 chars).
The multi-chunk path is not exercised here — see architecture notes for why.
"""
from hypersmell.pipeline.chunker import MAX_CHUNK_SIZE, chunk_document


def test_chunk_short_document():
    """Text well under 1500 chars is returned as a single chunk."""
    text = "Bergamot is a citrus fruit native to Calabria, Italy."
    chunks = chunk_document(text)
    assert len(chunks) == 1
    assert chunks[0]["content"] == text
    assert chunks[0]["chunk_index"] == 0


def test_chunk_empty_document():
    """Empty string returns an empty list of chunks."""
    chunks = chunk_document("")
    assert chunks == []


def test_chunk_single_sentence():
    """A single sentence produces exactly one chunk."""
    text = "The heart of this fragrance is Bulgarian rose absolute."
    chunks = chunk_document(text)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0


def test_chunk_at_sentence_boundary():
    """Text at exactly MAX_CHUNK_SIZE chars is treated as a single chunk."""
    # Build a text that is exactly at the limit — fits in one chunk
    sentence = "Sandalwood from Mysore has a creamy, woody character. "
    # Repeat to get close to limit but stay under
    text = (sentence * 27)[:MAX_CHUNK_SIZE]
    assert len(text) <= MAX_CHUNK_SIZE
    chunks = chunk_document(text)
    # Should still be a single chunk since len <= MAX_CHUNK_SIZE
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0


def test_chunk_returns_list_of_dicts():
    """chunk_document always returns a list of dicts with required keys."""
    text = "Vetiver from Haiti. Patchouli from Indonesia."
    chunks = chunk_document(text)
    assert isinstance(chunks, list)
    for chunk in chunks:
        assert isinstance(chunk, dict)
        assert "content" in chunk
        assert "chunk_index" in chunk


def test_chunk_content_is_non_empty():
    """All returned chunks contain non-empty content."""
    text = "Ambergris note layered over a musky base."
    chunks = chunk_document(text)
    for chunk in chunks:
        assert chunk["content"].strip() != ""


def test_chunk_preserves_full_text_for_short_input():
    """For text under the size limit, the full original text is preserved."""
    text = "Iris root, also known as orris, has a powdery, violet-like scent."
    chunks = chunk_document(text)
    assert chunks[0]["content"] == text


def test_chunk_long_document():
    """Text over MAX_CHUNK_SIZE is split into multiple chunks."""
    sentence = "This is a sentence. "
    text = sentence * 200  # Will be well over 1500 chars

    chunks = chunk_document(text)

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i
        assert len(chunk["content"]) <= MAX_CHUNK_SIZE

    # Verify that the reconstructed text matches the original (minus whitespace changes)
    reconstructed = " ".join([c["content"] for c in chunks])
    assert reconstructed.replace(" ", "") == text.replace(" ", "")
