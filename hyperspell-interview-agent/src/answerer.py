"""Truthful, grounded answer drafting for interview questions."""

from __future__ import annotations

import re

from .config import AppSettings
from .llm_nim import NIMGemmaClient
from .models import DraftAnswer, RetrievalResult
from .prompts import (
    CUSTOMER_DEBUGGING_FRAMEWORK,
    EXPERIENCE_GAP_RESPONSE,
    HYPERSPELL_ROLE_CONTEXT,
    PRODUCT_ENGINEERING_FRAMEWORK,
    SYSTEM_CANDIDATE_IDENTITY,
    TRUTHFULNESS_GUARDRAILS,
)

SENSITIVE_UNKNOWN_TOPICS = {
    "work authorization": ["work authorization", "visa", "sponsorship", "authorized"],
    "graduation date": ["graduation", "graduate", "degree completion"],
    "gpa": ["gpa"],
    "employment dates": ["employment date", "start date", "end date", "worked at"],
    "full-time experience": ["years of experience", "3+ years", "three years", "full-time"],
    "production metrics": ["users", "revenue", "production", "scale", "traffic"],
}

AFFIRMATIVE_FACT_PATTERNS = {
    "work authorization": [
        "authorized to work",
        "do not require sponsorship",
        "does not require sponsorship",
        "require sponsorship",
        "requires sponsorship",
    ],
    "graduation date": ["expected graduation", "graduating in", "graduation date:"],
    "gpa": ["gpa:"],
    "employment dates": ["worked from", "employment dates:", "started in"],
    "production metrics": ["active users", "production users", "monthly users", "revenue"],
}

LONG_ANSWER_KEYWORDS = (
    "architecture",
    "system design",
    "design doc",
    "implementation plan",
    "debugging plan",
    "tradeoffs",
    "deep dive",
)


def choose_max_tokens(question: str, settings: AppSettings, *, long_mode: bool = False) -> int:
    """Choose a safe answer budget from question intent."""

    if long_mode:
        return settings.nim_absolute_max_tokens

    q = question.lower()
    requested = settings.nim_long_max_tokens if any(keyword in q for keyword in LONG_ANSWER_KEYWORDS) else settings.nim_max_tokens
    return min(requested, 2500, settings.nim_absolute_max_tokens)


def answer_length_instruction(question: str) -> str:
    """Return the word-count instruction for the answer prompt."""

    q = question.lower()
    if any(keyword in q for keyword in LONG_ANSWER_KEYWORDS):
        return "Target length: 700-1200 words for technical architecture, debugging, or tradeoff-heavy answers."
    return "Target length: 300-700 words."


def overlong_warning(answer: str, threshold_words: int = 1800) -> str | None:
    """Return a manual-review warning for very long drafts."""

    approx_words = len(answer.split())
    if approx_words <= threshold_words:
        return None
    return f"Draft is long: ~{approx_words} words. Do not send this blindly. Review and compress first."


class Answerer:
    """Draft answers from retrieved context without inventing facts."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def draft(self, question: str, context: list[RetrievalResult]) -> DraftAnswer:
        """Create a grounded answer and private explanation for the candidate."""

        missing = self._missing_info_questions(question, context)
        confidence = self._confidence(context, missing)

        if not context:
            return DraftAnswer(
                question=question,
                answer_text=(
                    "I do not have enough local context to answer that truthfully yet. "
                    "Please provide the relevant details before I send a response."
                ),
                confidence="low",
                missing_info_questions=missing or ["Please add source context for this question."],
                private_reasoning_summary="No retrieved chunks were available, so any specific answer would risk inventing facts.",
                needs_confirmation=["Add or confirm the missing facts before sending."],
            )

        llm_answer = self._draft_with_llm(question, context)
        answer_text = llm_answer if llm_answer else self._draft_with_templates(question, context, missing)
        claimed_facts = self._claimed_facts(context)
        used_sources = [result.chunk.display_name for result in context]

        needs_confirmation = []
        if missing:
            needs_confirmation.append("The question touches facts that are missing or not fully confirmed in local context.")
        if confidence != "high":
            needs_confirmation.append("Review the answer carefully before sending because confidence is not high.")

        return DraftAnswer(
            question=question,
            answer_text=answer_text,
            confidence=confidence,
            used_context_sources=used_sources,
            missing_info_questions=missing,
            private_reasoning_summary=self._private_summary(context),
            claimed_facts=claimed_facts,
            needs_confirmation=needs_confirmation,
        )

    def _confidence(self, context: list[RetrievalResult], missing: list[str]) -> str:
        if missing:
            return "low"
        if len(context) >= 3:
            return "high"
        return "medium"

    def _context_text(self, context: list[RetrievalResult], max_chars: int = 8000) -> str:
        parts = []
        for result in context:
            parts.append(f"Source: {result.chunk.display_name}\n{result.chunk.text}")
        return "\n\n---\n\n".join(parts)[:max_chars]

    def _draft_with_llm(self, question: str, context: list[RetrievalResult]) -> str | None:
        # Legacy template answerer no longer calls hosted LLMs directly. The CLI
        # uses NIMGemmaAnswerer for NVIDIA NIM generation.
        return None

    def _draft_with_templates(
        self,
        question: str,
        context: list[RetrievalResult],
        missing: list[str],
    ) -> str:
        q = question.lower()
        if missing:
            return (
                "I want to answer this accurately, but my local context is missing a required detail. "
                f"Before I respond, I need to confirm: {'; '.join(missing)}"
            )
        if "3+" in q or "three years" in q or "years of experience" in q:
            return EXPERIENCE_GAP_RESPONSE
        if "why hyperspell" in q or ("why" in q and "hyperspell" in q):
            return (
                "Hyperspell stands out to me because memory and context are becoming core infrastructure for AI agents. "
                "A model alone is not enough; useful agents need the right user, product, and workflow context at the right time. "
                "That connects directly to my AI/full-stack work, especially my dynamic AI-powered portfolio using React, Node.js, "
                "Express, Tailwind CSS, Claude 3 through Hugging Face, and Qdrant for retrieval. I am excited about building "
                "developer-facing infrastructure that makes AI products more useful, reliable, and contextual."
            )
        if "tell me about yourself" in q or "introduce yourself" in q:
            return (
                "I am Chetas Nikunjbhai Parekh, an M.S. Computer Science student at San Francisco State University and an "
                "early-career full-stack AI builder based in San Francisco. I work across Python, JavaScript/TypeScript, React, "
                "Node.js, Express, Tailwind CSS, LLM APIs, Qdrant, and data visualization. My strongest relevant project is a "
                "dynamic AI-powered portfolio that combines a React/Tailwind frontend, Node/Express backend, Claude 3 through "
                "Hugging Face, and Qdrant retrieval to answer questions from personalized context. I am also a 5x hackathon "
                "winner, so I am comfortable learning quickly, narrowing scope, communicating tradeoffs, and shipping under pressure."
            )
        if "product engineer" in q:
            return (
                "Product engineering fits me because I like working across the full product loop: understanding the user problem, "
                "designing the interaction, building frontend and backend pieces, integrating AI systems, debugging failures, and "
                "improving the product based on feedback. For Hyperspell, that means caring not just about model calls, but about "
                "whether the system retrieves the right context, whether developers can integrate it cleanly, and whether failure "
                "states are understandable."
            )
        if any(term in q for term in ("customer", "debug", "issue", "bug", "support")):
            return (
                "I would start by acknowledging the customer's problem and clarifying the expected behavior. Then I would reproduce "
                "the issue with the same inputs and environment, inspect logs, request payloads, response codes, retrieval results, "
                "and model outputs, and isolate whether the problem is in the frontend, backend, retrieval layer, model behavior, "
                "data quality, or configuration. If there is a safe workaround, I would communicate it quickly. Then I would fix the "
                "root cause, add a regression test or monitoring signal, and keep the customer updated with clear next steps."
            )

        facts = self._claimed_facts(context)
        fact_sentence = " ".join(facts[:3]) if facts else "My background is strongest in AI/full-stack product building."
        return (
            f"My answer would start from the relevant context in my background: {fact_sentence} "
            f"I would approach this in a practical product-engineering way: {PRODUCT_ENGINEERING_FRAMEWORK} "
            f"If this is customer-facing, I would also use a debugging approach like: {CUSTOMER_DEBUGGING_FRAMEWORK}"
        )

    def _missing_info_questions(self, question: str, context: list[RetrievalResult]) -> list[str]:
        q = question.lower()
        context_text = " ".join(result.chunk.text.lower() for result in context)
        missing: list[str] = []
        for topic, triggers in SENSITIVE_UNKNOWN_TOPICS.items():
            if not any(trigger in q for trigger in triggers):
                continue
            if topic == "full-time experience" and ("do not have 3+ years" in context_text or "early-career" in context_text):
                continue
            affirmative_patterns = AFFIRMATIVE_FACT_PATTERNS.get(topic, [])
            if affirmative_patterns and any(pattern in context_text for pattern in affirmative_patterns):
                continue
            missing.append(f"Confirm {topic} before answering.")
        return missing

    def _claimed_facts(self, context: list[RetrievalResult]) -> list[str]:
        facts: list[str] = []
        seen: set[str] = set()
        for result in context:
            for line in result.chunk.text.splitlines():
                cleaned = re.sub(r"^\s*[-*#]+\s*", "", line).strip()
                if not cleaned or len(cleaned) < 25 or cleaned.lower().startswith("replace this file"):
                    continue
                if cleaned in seen:
                    continue
                seen.add(cleaned)
                facts.append(cleaned)
                if len(facts) >= 8:
                    return facts
        return facts

    def _private_summary(self, context: list[RetrievalResult]) -> str:
        lines = []
        for result in context:
            lines.append(f"- {result.chunk.display_name}: {result.reason}")
        return "Retrieved chunks used for grounding:\n" + "\n".join(lines)


class NIMGemmaAnswerer:
    """Retrieve candidate context and draft answers with NVIDIA NIM Gemma."""

    def __init__(self, retriever: object, llm: NIMGemmaClient, settings: AppSettings | None = None) -> None:
        self.retriever = retriever
        self.llm = llm
        self.settings = settings or llm.settings
        self._guards = Answerer(self.settings)

    def draft_answer(
        self,
        question: str,
        top_k: int = 8,
        full_context: bool = False,
        long_mode: bool = False,
    ) -> DraftAnswer:
        """Retrieve context, call Gemma, and return a private explainable draft."""

        results = self._retrieve(question, top_k=top_k, full_context=full_context)
        missing = self._guards._missing_info_questions(question, results)
        if not results:
            return DraftAnswer(
                question=question,
                answer_text="I do not have that information in my current context.",
                confidence="low",
                private_model_reasoning="",
                missing_info_questions=missing or ["Add candidate context for this question before answering."],
                private_reasoning_summary="No retrieval chunks were available, so the model was not called.",
                needs_confirmation=["Add source context before sending."],
            )

        if missing:
            return DraftAnswer(
                question=question,
                answer_text=(
                    "I do not have that information in my current context. "
                    f"Missing details to confirm: {'; '.join(missing)}"
                ),
                confidence="low",
                private_model_reasoning="",
                used_context_sources=[result.chunk.display_name for result in results],
                missing_info_questions=missing,
                private_reasoning_summary=self._private_summary(results, full_context=full_context),
                claimed_facts=self._guards._claimed_facts(results),
                needs_confirmation=["Confirm missing facts before sending."],
            )

        messages = self._build_messages(question, results, long_mode=long_mode)
        model_output = self.llm.generate_response(
            messages,
            max_tokens=choose_max_tokens(question, self.settings, long_mode=long_mode),
            temperature=self.settings.nim_temperature,
        )
        answer = model_output["final_answer"]
        length_warning = overlong_warning(answer)
        confidence = "high" if len(results) >= 3 else "medium"
        needs_confirmation = [] if confidence == "high" else ["Review carefully before sending because confidence is not high."]
        if length_warning:
            needs_confirmation.append(length_warning)
        return DraftAnswer(
            question=question,
            answer_text=answer,
            confidence=confidence,
            private_model_reasoning=model_output.get("private_reasoning", ""),
            used_context_sources=[result.chunk.display_name for result in results],
            missing_info_questions=[],
            private_reasoning_summary=self._private_summary(results, full_context=full_context),
            claimed_facts=self._guards._claimed_facts(results),
            needs_confirmation=needs_confirmation,
        )

    def _retrieve(self, question: str, top_k: int, full_context: bool) -> list[RetrievalResult]:
        if full_context:
            chunks = getattr(self.retriever, "chunks", [])
            return [
                RetrievalResult(
                    chunk=chunk,
                    score=1.0,
                    rank=rank,
                    method="full_context",
                    reason="Full-context mode was explicitly requested by the user.",
                )
                for rank, chunk in enumerate(chunks, start=1)
            ]
        return self.retriever.retrieve(question, top_k=top_k)

    def _build_messages(
        self,
        question: str,
        results: list[RetrievalResult],
        *,
        long_mode: bool = False,
    ) -> list[dict[str, str]]:
        context_block = "\n\n".join(
            f"[Source: {result.chunk.source_file}, chunk {result.chunk.chunk_index}]\n{result.chunk.text}"
            for result in results
        )
        system_prompt = f"""
{SYSTEM_CANDIDATE_IDENTITY}

{HYPERSPELL_ROLE_CONTEXT}

You are Chetas Nikunjbhai Parekh's interview agent for the Hyperspell Product Engineer role.
Answer in first person as Chetas.
Be honest, concise, technical, and product-minded.
Use only the provided context.
Do not invent facts.
Tie answers to Hyperspell's AI-agent memory/context product when relevant.
If discussing the 3+ years requirement, acknowledge that Chetas is earlier-career and explain the relevant AI/full-stack/project/hackathon experience.
Prefer concrete examples over generic claims.
Do not mention private retrieval details, source names, or chunk numbers in the answer.

Truthfulness rules:
{TRUTHFULNESS_GUARDRAILS}
""".strip()
        user_prompt = f"""
Interview question:
{question}

Retrieved candidate context:
{context_block}

Draft a strong interview answer.
Keep it concise but complete.
Make it sound like a real person, not a resume parser.
{answer_length_instruction(question)}
{"Long mode is explicitly approved for this draft, but stay concise and do not use extra length unless it improves the answer." if long_mode else "Never generate more than 2500 tokens unless the user explicitly approved long mode."}
If information is missing, say: "I do not have that information in my current context."
""".strip()
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _private_summary(self, results: list[RetrievalResult], *, full_context: bool) -> str:
        mode = "full context" if full_context else "hybrid retrieval"
        lines = [f"Context mode: {mode}."]
        for result in results:
            lines.append(f"- {result.chunk.display_name}: {result.reason}")
        return "\n".join(lines)
