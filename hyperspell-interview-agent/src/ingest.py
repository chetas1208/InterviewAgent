"""Document loading, text extraction, chunking, and artifact persistence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import TypeAdapter

from .models import DocumentChunk
from .utils import ensure_dir, normalize_whitespace

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".html", ".htm"}
CHUNKS_FILE = "chunks.json"


def load_text_file(path: Path) -> str:
    """Load plain text or Markdown content."""

    return path.read_text(encoding="utf-8", errors="replace")


def load_pdf(path: Path) -> str:
    """Extract text from a PDF file using pypdf."""

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def load_docx(path: Path) -> str:
    """Extract paragraph text from a DOCX file."""

    from docx import Document

    document = Document(str(path))
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())


def load_html(path: Path) -> str:
    """Clean HTML and normalize it to Markdown-like text."""

    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return md(str(soup))


def load_document(path: Path) -> str:
    """Load a supported document type into plain text."""

    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return load_text_file(path)
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix == ".docx":
        return load_docx(path)
    if suffix in {".html", ".htm"}:
        return load_html(path)
    raise ValueError(f"Unsupported file type: {path}")


def discover_documents(data_dir: Path) -> list[Path]:
    """Return supported files under `data_dir` in stable order."""

    if not data_dir.exists():
        return []
    return sorted(
        path
        for path in data_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _section_title_at(text: str, start_char: int) -> str | None:
    headings = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", text[: max(start_char, 0) + 1]))
    if not headings:
        first_heading = re.search(r"(?m)^#{1,6}\s+(.+?)\s*$", text)
        return first_heading.group(1).strip() if first_heading else None
    return headings[-1].group(1).strip()


def _best_chunk_end(text: str, start: int, min_chars: int, max_chars: int) -> int:
    hard_end = min(len(text), start + max_chars)
    if hard_end >= len(text):
        return len(text)

    min_end = min(len(text), start + min_chars)
    window = text[min_end:hard_end]

    paragraph_break = window.rfind("\n\n")
    if paragraph_break != -1:
        return min_end + paragraph_break + 2

    sentence_breaks = [window.rfind(marker) for marker in (". ", "? ", "! ")]
    sentence_break = max(sentence_breaks)
    if sentence_break != -1:
        return min_end + sentence_break + 2

    newline = window.rfind("\n")
    if newline != -1:
        return min_end + newline + 1

    return hard_end


def chunk_text(
    text: str,
    source_file: str,
    *,
    min_chars: int = 2500,
    max_chars: int = 4000,
    overlap_chars: int = 700,
) -> list[DocumentChunk]:
    """Split text into explainable overlapping chunks.

    The target size maps roughly to 500-900 tokens. Character-based chunking is
    deterministic and avoids adding tokenizer dependencies just for ingestion.
    """

    cleaned = normalize_whitespace(text)
    if not cleaned:
        return []
    if min_chars <= 0 or max_chars <= min_chars:
        raise ValueError("Expected 0 < min_chars < max_chars.")
    if overlap_chars < 0 or overlap_chars >= min_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than min_chars.")

    chunks: list[DocumentChunk] = []
    start = 0
    chunk_index = 0
    while start < len(cleaned):
        end = _best_chunk_end(cleaned, start, min_chars, max_chars)
        chunk_body = cleaned[start:end].strip()
        if chunk_body:
            digest = hashlib.sha1(f"{source_file}:{chunk_index}:{start}:{chunk_body[:80]}".encode()).hexdigest()[:12]
            chunks.append(
                DocumentChunk(
                    id=f"{Path(source_file).name}-{chunk_index}-{digest}",
                    text=chunk_body,
                    source_file=source_file,
                    section_title=_section_title_at(cleaned, start),
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end,
                )
            )
            chunk_index += 1
        if end >= len(cleaned):
            break
        start = max(0, end - overlap_chars)
    return chunks


def build_chunks_from_directory(data_dir: Path) -> tuple[list[Path], list[DocumentChunk]]:
    """Load supported documents and return all chunks."""

    documents = discover_documents(data_dir)
    chunks: list[DocumentChunk] = []
    for path in documents:
        text = load_document(path)
        source_file = str(path.relative_to(data_dir))
        chunks.extend(chunk_text(text, source_file))
    return documents, chunks


def save_chunks(chunks: list[DocumentChunk], artifacts_dir: Path) -> Path:
    """Persist chunks to `artifacts/chunks.json`."""

    ensure_dir(artifacts_dir)
    path = artifacts_dir / CHUNKS_FILE
    payload = [chunk.model_dump() for chunk in chunks]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_chunks(artifacts_dir: Path) -> list[DocumentChunk]:
    """Load chunk artifacts from disk."""

    path = artifacts_dir / CHUNKS_FILE
    if not path.exists():
        raise FileNotFoundError(f"No chunk artifact found at {path}. Run `python -m src.interview_runner ingest` first.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[DocumentChunk]).validate_python(payload)
