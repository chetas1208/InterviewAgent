"""Local LinkedIn PDF ingestion for retrieval context."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from .utils import normalize_whitespace

LINKEDIN_PDF_CANDIDATES = (
    "LinkedIn_Profile.pdf",
    "linkedin_profile.pdf",
    "linkedin.pdf",
)
OUTPUT_FILE_NAME = "linkedin_context.md"


def find_linkedin_pdf(data_dir: Path) -> Path | None:
    """Return the preferred LinkedIn PDF path if one exists."""

    for filename in LINKEDIN_PDF_CANDIDATES:
        path = data_dir / filename
        if path.exists() and path.is_file():
            return path
    return None


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a LinkedIn PDF page by page."""

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_whitespace(text)
        if text:
            pages.append(f"[LinkedIn PDF page {index}]\n{text}")
    return "\n\n".join(pages).strip()


def normalize_linkedin_text(raw_text: str) -> str:
    """Clean extracted LinkedIn text while preserving section structure."""

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def write_linkedin_context(pdf_path: Path, text: str) -> Path:
    """Write normalized Markdown context for retrieval."""

    output_path = pdf_path.parent / OUTPUT_FILE_NAME
    source_path = f"data/{pdf_path.name}"
    body = "\n\n".join(
        [
            "# LinkedIn Profile Context",
            f"Source PDF: {source_path}",
            "Extracted for local retrieval only.",
            "",
            text,
        ]
    ).strip() + "\n"
    output_path.write_text(body, encoding="utf-8")
    return output_path


def ingest_linkedin_pdf(data_dir: Path = Path("data")) -> Path | None:
    """Extract a local LinkedIn PDF into `data/linkedin_context.md` if present."""

    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / OUTPUT_FILE_NAME
    pdf_path = find_linkedin_pdf(data_dir)
    if pdf_path is None:
        if output_path.exists():
            output_path.unlink()
        print(
            "No LinkedIn PDF found. To include LinkedIn context, export your LinkedIn profile as PDF "
            "and save it to data/LinkedIn_Profile.pdf."
        )
        return None

    raw_text = extract_pdf_text(pdf_path)
    normalized = normalize_linkedin_text(raw_text)
    if not normalized:
        if output_path.exists():
            output_path.unlink()
        print("LinkedIn PDF has no extractable text. Re-export from LinkedIn or provide a text/markdown version.")
        return None

    written_path = write_linkedin_context(pdf_path, normalized)
    print(f"LinkedIn PDF ingestion succeeded: {pdf_path}")
    print(f"Wrote LinkedIn context to {written_path}")
    return written_path


if __name__ == "__main__":
    ingest_linkedin_pdf()
