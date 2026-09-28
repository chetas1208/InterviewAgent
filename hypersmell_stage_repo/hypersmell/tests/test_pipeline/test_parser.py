"""Tests for the document parser pipeline component."""
from hypersmell.pipeline.parser import parse_document


def test_parse_normal_content():
    """parse_document returns clean, whitespace-normalized text."""
    content = "This is a fragrance note. It smells of bergamot and cedar."
    result = parse_document(content)
    assert result == "This is a fragrance note. It smells of bergamot and cedar."


def test_parse_empty_content():
    """parse_document returns empty string for empty input."""
    result = parse_document("")
    assert result == ""


def test_parse_none_content():
    """parse_document returns empty string for None-ish falsy input."""
    result = parse_document("")
    assert result == ""


def test_parse_whitespace_normalization():
    """parse_document collapses excess whitespace into single spaces."""
    content = "Top   notes:\n\nbergamot,   lemon.\n\nBase   notes:\n\ncedar."
    result = parse_document(content)
    assert result == "Top notes: bergamot, lemon. Base notes: cedar."
    assert "  " not in result
    assert "\n" not in result


def test_parse_leading_trailing_whitespace():
    """parse_document strips leading and trailing whitespace."""
    content = "   Rose absolute.   "
    result = parse_document(content)
    assert result == "Rose absolute."


def test_parse_preserves_content():
    """parse_document does not alter meaningful content."""
    content = "Oud from Laos. Sandalwood from Mysore. Vetiver from Haiti."
    result = parse_document(content)
    assert "Oud from Laos." in result
    assert "Sandalwood from Mysore." in result
    assert "Vetiver from Haiti." in result


def test_parse_with_metadata():
    """parse_document accepts an optional metadata dict without error."""
    content = "A gentle floral accord."
    metadata = {"source": "supplier_catalog", "doc_id": "123"}
    result = parse_document(content, metadata=metadata)
    assert result == "A gentle floral accord."
    assert "floral" in metadata["scent_families"]

def test_extract_scent_families():
    """Extracts multiple scent families from text."""
    from hypersmell.pipeline.parser import extract_scent_families
    content = "This features rose and jasmine with a woody cedar base."
    families = extract_scent_families(content)
    assert sorted(families) == ["floral", "woody"]

