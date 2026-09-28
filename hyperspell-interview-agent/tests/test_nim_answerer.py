from __future__ import annotations

from src.answerer import NIMGemmaAnswerer, choose_max_tokens, overlong_warning
from src.config import AppSettings
from src.models import DocumentChunk, RetrievalResult


def make_result() -> RetrievalResult:
    chunk = DocumentChunk(
        id="candidate-0",
        text="Chetas built an AI-powered portfolio with React, Node.js, Express, Tailwind CSS, Claude 3, and Qdrant.",
        source_file="candidate_context.md",
        section_title="Project",
        chunk_index=0,
    )
    return RetrievalResult(chunk=chunk, score=1.0, rank=1, method="bm25", reason="Matched Qdrant and portfolio.")


class FakeRetriever:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.chunks = [result.chunk for result in results]

    def retrieve(self, question: str, top_k: int = 8):
        return self.results[:top_k]


class FakeLLM:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.messages = None
        self.max_tokens = None
        self.called = False

    def generate_response(self, messages, max_tokens=None, temperature=None):
        self.called = True
        self.messages = messages
        self.max_tokens = max_tokens
        return {
            "private_reasoning": "I should tie this to retrieval and Hyperspell's memory context work.",
            "final_answer": "I built a dynamic AI-powered portfolio using React, Node.js, Express, Tailwind CSS, Claude 3, and Qdrant.",
            "raw_content": "<think>private</think>I built a dynamic AI-powered portfolio using React, Node.js, Express, Tailwind CSS, Claude 3, and Qdrant.",
        }


def test_nim_answerer_retrieves_chunks_and_builds_prompt_without_api_key() -> None:
    settings = AppSettings(nim_api_key="hidden-secret-key")
    llm = FakeLLM(settings)
    answerer = NIMGemmaAnswerer(FakeRetriever([make_result()]), llm, settings=settings)

    draft = answerer.draft_answer("Why Hyperspell?", top_k=8)

    assert draft.answer_text.startswith("I built a dynamic")
    assert draft.private_model_reasoning.startswith("I should tie this")
    assert draft.used_context_sources == ["candidate_context.md#0 | Project"]
    assert llm.called is True
    rendered_messages = str(llm.messages)
    assert "hidden-secret-key" not in rendered_messages
    assert "candidate_context.md" in rendered_messages


def test_nim_answerer_refuses_with_no_context() -> None:
    settings = AppSettings(nim_base_url="http://0.0.0.0:8000/v1")
    llm = FakeLLM(settings)
    answerer = NIMGemmaAnswerer(FakeRetriever([]), llm, settings=settings)

    draft = answerer.draft_answer("What is your work authorization?", top_k=8)

    assert draft.confidence == "low"
    assert draft.answer_text == "I do not have that information in my current context."
    assert llm.called is False


def test_nim_answerer_does_not_put_private_source_metadata_in_answer() -> None:
    settings = AppSettings(nim_api_key="key")
    llm = FakeLLM(settings)
    answerer = NIMGemmaAnswerer(FakeRetriever([make_result()]), llm, settings=settings)

    draft = answerer.draft_answer("Tell me about yourself.", top_k=8)

    assert "candidate_context.md" not in draft.answer_text
    assert "chunk" not in draft.answer_text.lower()
    assert "Hyperspell's memory context work" not in draft.answer_text


def test_choose_max_tokens_uses_default_and_technical_budget() -> None:
    settings = AppSettings(nim_max_tokens=1200, nim_long_max_tokens=2500, nim_absolute_max_tokens=6000)

    assert choose_max_tokens("Why Hyperspell?", settings) == 1200
    assert choose_max_tokens("Walk me through the architecture tradeoffs.", settings) == 2500
    assert choose_max_tokens("Walk me through the architecture tradeoffs.", settings, long_mode=True) == 6000


def test_nim_answerer_passes_question_based_max_tokens() -> None:
    settings = AppSettings(nim_api_key="key", nim_max_tokens=1200, nim_long_max_tokens=2500, nim_absolute_max_tokens=6000)
    llm = FakeLLM(settings)
    answerer = NIMGemmaAnswerer(FakeRetriever([make_result()]), llm, settings=settings)

    answerer.draft_answer("Give me a technical architecture deep dive.", top_k=8)

    assert llm.max_tokens == 2500
    assert "Never generate more than 2500 tokens" in str(llm.messages)

    answerer.draft_answer("Give me a technical architecture deep dive.", top_k=8, long_mode=True)

    assert llm.max_tokens == 6000
    assert "Long mode is explicitly approved" in str(llm.messages)


def test_overlong_warning_triggers_after_1800_words() -> None:
    warning = overlong_warning("word " * 1801)

    assert warning is not None
    assert "Draft is long" in warning
