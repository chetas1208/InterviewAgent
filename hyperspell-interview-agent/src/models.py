"""Typed data models for ingestion, retrieval, answers, and interview state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = Literal["high", "medium", "low"]


class DocumentChunk(BaseModel):
    """A searchable piece of a source document."""

    id: str
    text: str
    source_file: str
    section_title: str | None = None
    chunk_index: int
    start_char: int = 0
    end_char: int = 0

    @property
    def display_name(self) -> str:
        """Return a compact source label for terminal display."""

        section = f" | {self.section_title}" if self.section_title else ""
        return f"{self.source_file}#{self.chunk_index}{section}"


class RetrievalResult(BaseModel):
    """A ranked retrieval result with an explainable score."""

    chunk: DocumentChunk
    score: float
    rank: int
    method: str
    reason: str = ""


class InterviewEvent(BaseModel):
    """Normalized view of an interview status response."""

    interview_id: str | None = None
    status: str = "unknown"
    stage_number: int | None = None
    stage_name: str | None = None
    question: str | None = None
    awaiting_input: bool = False
    manual_intervention: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class DraftAnswer(BaseModel):
    """Answer draft and private explanation shown only to the candidate."""

    question: str
    answer_text: str
    confidence: Confidence
    private_model_reasoning: str = ""
    used_context_sources: list[str] = Field(default_factory=list)
    missing_info_questions: list[str] = Field(default_factory=list)
    private_reasoning_summary: str = ""
    claimed_facts: list[str] = Field(default_factory=list)
    needs_confirmation: list[str] = Field(default_factory=list)

    @property
    def used_sources(self) -> list[str]:
        """Compatibility alias for callers that use the shorter field name."""

        return self.used_context_sources


class CandidateProfile(BaseModel):
    """Basic candidate identity used for prompts and defaults."""

    name: str = "Chetas Nikunjbhai Parekh"
    target_company: str = "Hyperspell"
    target_role: str = "Product Engineer"
    role_id: str = "43A0pbylxajHuP7wQ8m3"
    location: str = "San Francisco"
    positioning: str = "Early-career full-stack AI builder and M.S. Computer Science student."
