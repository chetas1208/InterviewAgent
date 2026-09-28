from __future__ import annotations

import pytest

from src.answerer import Answerer
from src.config import AppSettings
from src.models import DocumentChunk, RetrievalResult
from src.superme_client import SuperMeClientWrapper


def make_result(text: str) -> RetrievalResult:
    chunk = DocumentChunk(
        id="candidate-0",
        text=text,
        source_file="candidate_context.md",
        section_title="Missing Facts",
        chunk_index=0,
    )
    return RetrievalResult(chunk=chunk, score=1.0, rank=1, method="bm25")


def test_answerer_refuses_to_invent_when_context_missing() -> None:
    answerer = Answerer(AppSettings())

    draft = answerer.draft("What is your work authorization?", [])

    assert draft.confidence == "low"
    assert "do not have enough local context" in draft.answer_text.lower()
    assert draft.missing_info_questions


def test_answerer_treats_missing_fact_mentions_as_missing() -> None:
    answerer = Answerer(AppSettings())
    context = [make_result("Missing facts to confirm before claiming: Work authorization.")]

    draft = answerer.draft("What is your work authorization?", context)

    assert draft.confidence == "low"
    assert any("work authorization" in item.lower() for item in draft.missing_info_questions)


def test_superme_client_does_not_run_without_api_key() -> None:
    settings = AppSettings(superme_api_key=None)
    client = SuperMeClientWrapper(settings)

    with pytest.raises(RuntimeError, match="SUPERME_API_KEY"):
        client.start_interview("role-id")


def test_config_has_no_linkedin_token_fields() -> None:
    settings = AppSettings()

    assert "linkedin_access_token" not in AppSettings.model_fields
    assert not hasattr(settings, "linkedin_access_token")
