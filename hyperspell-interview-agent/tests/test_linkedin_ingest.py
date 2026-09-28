from __future__ import annotations

from pathlib import Path

from src.linkedin_pdf_ingest import find_linkedin_pdf
from src.linkedin_pdf_ingest import ingest_linkedin_pdf
from src.linkedin_pdf_ingest import normalize_linkedin_text


def test_find_linkedin_pdf_prefers_capitalized_profile_name(tmp_path: Path) -> None:
    (tmp_path / "linkedin.pdf").write_bytes(b"%PDF-1.4")
    preferred = tmp_path / "LinkedIn_Profile.pdf"
    preferred.write_bytes(b"%PDF-1.4")
    (tmp_path / "linkedin_profile.pdf").write_bytes(b"%PDF-1.4")

    result = find_linkedin_pdf(tmp_path)

    assert result == preferred


def test_missing_linkedin_pdf_skips_gracefully(tmp_path: Path, capsys) -> None:
    stale = tmp_path / "linkedin_context.md"
    stale.write_text("old", encoding="utf-8")

    result = ingest_linkedin_pdf(tmp_path)

    captured = capsys.readouterr()
    assert result is None
    assert not stale.exists()
    assert "No LinkedIn PDF found." in captured.out


def test_normalize_linkedin_text_removes_excessive_whitespace() -> None:
    raw = "Headline   here\n\n\nExperience\t\tsection\n  Skills  list  "

    normalized = normalize_linkedin_text(raw)

    assert normalized == "Headline here\n\nExperience section\nSkills list"


def test_ingest_linkedin_pdf_writes_context_when_text_exists(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "LinkedIn_Profile.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        "src.linkedin_pdf_ingest.extract_pdf_text",
        lambda path: "[LinkedIn PDF page 1]\nHeadline\n\nExperience",
    )

    output = ingest_linkedin_pdf(tmp_path)

    assert output == tmp_path / "linkedin_context.md"
    text = output.read_text(encoding="utf-8")
    assert "# LinkedIn Profile Context" in text
    assert "Source PDF: data/LinkedIn_Profile.pdf" in text
    assert "Experience" in text
