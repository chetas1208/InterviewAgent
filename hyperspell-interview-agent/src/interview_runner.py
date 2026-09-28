"""Typer CLI for ingesting context and running the SuperMe interview loop."""

from __future__ import annotations

import time
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from typer import Argument, Option

from .answerer import NIMGemmaAnswerer
from .answerer import overlong_warning
from .config import get_settings
from .github_ingest import ingest_github as run_github_ingest
from .ingest import build_chunks_from_directory
from .linkedin_pdf_ingest import find_linkedin_pdf
from .linkedin_pdf_ingest import ingest_linkedin_pdf as run_linkedin_pdf_ingest
from .llm_nim import NIMGemmaClient
from .models import DraftAnswer, InterviewEvent
from .retrieval import HybridRetriever
from .superme_client import SuperMeClientWrapper
from .utils import console, ensure_dir, extract_interview_id, read_json, stage_requires_repo_work, write_json

app = typer.Typer(help="Explainable Hyperspell SuperMe interview agent.")
SESSION_FILE = "session.json"

logger.remove()
logger.add(sys.stderr, level="WARNING")


def _session_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / SESSION_FILE


def _load_session(artifacts_dir: Path) -> dict[str, Any]:
    path = _session_path(artifacts_dir)
    if not path.exists():
        raise typer.BadParameter("No session found. Run `python -m src.interview_runner start` first.")
    return read_json(path)


def _save_session(artifacts_dir: Path, interview_id: str, payload: dict[str, Any] | None = None) -> None:
    write_json(_session_path(artifacts_dir), {"interview_id": interview_id, "last_start_response": payload or {}})


def _load_retriever() -> HybridRetriever:
    settings = get_settings()
    return HybridRetriever.load(settings.artifacts_dir, build_dense=True)


def _has_secret(secret: object) -> bool:
    return bool(secret and getattr(secret, "get_secret_value")().strip())


def _build_nim_answerer() -> NIMGemmaAnswerer:
    settings = get_settings()
    retriever = HybridRetriever.load(settings.artifacts_dir, build_dense=True)
    try:
        llm = NIMGemmaClient(settings)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    return NIMGemmaAnswerer(retriever, llm, settings=settings)


def _draft_with_nim(question: str, *, full_context: bool = False, long_mode: bool = False) -> DraftAnswer:
    answerer = _build_nim_answerer()
    return answerer.draft_answer(question, top_k=8, full_context=full_context, long_mode=long_mode)


def _require_available_nim_model() -> NIMGemmaClient:
    settings = get_settings()
    try:
        llm = NIMGemmaClient(settings)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if not llm.check_model_available():
        console.print("[red]Gemma 4 is not available for this NIM endpoint/key. Use another available model or run local NIM.[/red]")
        raise typer.Exit(code=1)
    return llm


def _display_draft(draft: DraftAnswer) -> None:
    console.print(Panel(draft.question, title="Question", border_style="cyan"))
    console.print(Panel(draft.answer_text, title=f"Draft Answer | Confidence: {draft.confidence}", border_style="green"))
    if draft.private_model_reasoning:
        console.print(
            Panel(
                draft.private_model_reasoning,
                title="Model Reasoning | Local Review Only",
                border_style="magenta",
            )
        )

    table = Table(title="Private Grounding Explanation")
    table.add_column("Item")
    table.add_column("Details")
    table.add_row("Used sources", "\n".join(draft.used_context_sources) or "None")
    table.add_row("Claimed facts", "\n".join(f"- {fact}" for fact in draft.claimed_facts) or "None")
    table.add_row("Missing info", "\n".join(f"- {item}" for item in draft.missing_info_questions) or "None")
    table.add_row("Needs confirmation", "\n".join(f"- {item}" for item in draft.needs_confirmation) or "None")
    table.add_row("Why these chunks", draft.private_reasoning_summary or "No explanation available.")
    console.print(table)


def _display_interviewer_prompt(question: str, stage_name: str | None = None) -> None:
    """Show the interviewer prompt before any local drafting or blocking decision."""

    title = "Interviewer Prompt"
    if stage_name:
        title = f"Interviewer Prompt | {stage_name}"
    console.print(Panel(question, title=title, border_style="cyan"))


def _summarize_long_answer(answer: str, limit_words: int = 180) -> str:
    """Return a compact review summary for overlong drafts."""

    words = answer.split()
    if len(words) <= limit_words:
        return answer
    return " ".join(words[:limit_words]) + " ..."


def _prompt_for_question(status_event: InterviewEvent | None = None) -> str:
    if status_event and status_event.question:
        return status_event.question
    return typer.prompt("Paste the current interview question")


def _status_line(event: InterviewEvent) -> str:
    """Return a human-readable status line for polling output."""

    parts = [f"Status: {event.status}"]
    if event.stage_number is not None or event.stage_name:
        stage_bits = []
        if event.stage_number is not None:
            stage_bits.append(f"stage {event.stage_number}")
        if event.stage_name:
            stage_bits.append(event.stage_name)
        parts.append(" | ".join(stage_bits))
    if event.awaiting_input:
        parts.append("awaiting your answer")
    elif event.manual_intervention:
        parts.append("manual input stage")
    else:
        parts.append("SuperMe-controlled stage")
    return " | ".join(parts)


def _approved_answer_text(draft: DraftAnswer) -> str | None:
    settings = get_settings()
    if not settings.require_answer_approval:
        return draft.answer_text

    warning = overlong_warning(draft.answer_text)
    if warning:
        console.print(f"[red]{warning}[/red]")
        console.print(Panel(_summarize_long_answer(draft.answer_text), title="Long Draft Summary", border_style="yellow"))
        console.print("[yellow]Summarize or edit before sending unless you explicitly approve this long draft.[/yellow]")
        long_choice = typer.prompt("Type SEND LONG DRAFT to allow sending as-is, edit to edit, or N to cancel", default="N").strip()
        if long_choice == "edit":
            edited = typer.edit(draft.answer_text)
            if edited and edited.strip():
                return edited.strip()
            pasted = typer.prompt("Paste final compressed answer to send")
            return pasted.strip() if pasted.strip() else None
        if long_choice != "SEND LONG DRAFT":
            return None

    choice = typer.prompt("Send this final answer to SuperMe? [y/N/edit]", default="N").strip().lower()
    if choice in {"y", "yes"}:
        return draft.answer_text
    if choice == "edit":
        edited = typer.edit(draft.answer_text)
        if edited and edited.strip():
            return edited.strip()
        pasted = typer.prompt("Paste final answer to send")
        return pasted.strip() if pasted.strip() else None
    return None


def _send_answer(interview_id: str, draft: DraftAnswer, stage_number: int | None) -> None:
    approved = _approved_answer_text(draft)
    if not approved:
        console.print("[yellow]Answer not sent.[/yellow]")
        return
    settings = get_settings()
    client = SuperMeClientWrapper(settings)
    response = client.send_interview_message(interview_id, approved, stage_number=stage_number)
    console.print(Panel(Pretty(response), title="Send Response", border_style="green"))


@app.command()
def ingest() -> None:
    """Refresh optional context sources, load `./data`, and build retrieval artifacts."""

    settings = get_settings()
    ensure_dir(settings.artifacts_dir)
    if _has_secret(settings.github_token):
        try:
            run_github_ingest(
                data_dir=settings.data_dir,
                token=settings.github_token.get_secret_value(),
                username=settings.github_username,
            )
        except RuntimeError as exc:
            console.print(f"[yellow]GitHub ingestion skipped: {exc}[/yellow]")
    run_linkedin_pdf_ingest(settings.data_dir)
    documents, chunks = build_chunks_from_directory(settings.data_dir)
    retriever = HybridRetriever(
        chunks,
        embedding_model_name=settings.embedding_model_name,
        cross_encoder_model_name=settings.cross_encoder_model_name,
        build_dense=True,
    )
    retriever.save(settings.artifacts_dir)
    console.print(f"Loaded {len(documents)} documents and built {len(chunks)} chunks.")
    if retriever.embeddings is None:
        console.print("[yellow]Dense embeddings were not built. BM25 retrieval will still work; install/check sentence-transformers for dense search.[/yellow]")


@app.command("ingest-github")
def ingest_github(max_repos: int = Option(default=12, min=1, help="Maximum repositories to include.")) -> None:
    """Fetch GitHub repository context into `data/github_context.md`."""

    settings = get_settings()
    token = settings.github_token.get_secret_value() if settings.github_token else None
    run_github_ingest(
        max_repos=max_repos,
        data_dir=settings.data_dir,
        token=token,
        username=settings.github_username,
    )


@app.command("ingest-linkedin")
def ingest_linkedin() -> None:
    """Extract LinkedIn PDF context into `data/linkedin_context.md` if available."""

    settings = get_settings()
    run_linkedin_pdf_ingest(settings.data_dir)


@app.command("show-linkedin")
def show_linkedin() -> None:
    """Show LinkedIn PDF detection and a preview of extracted local context."""

    settings = get_settings()
    pdf_path = find_linkedin_pdf(settings.data_dir)
    context_path = settings.data_dir / "linkedin_context.md"
    console.print(f"LinkedIn PDF exists: {'yes' if pdf_path else 'no'}")
    console.print(f"LinkedIn PDF path: {pdf_path if pdf_path else 'None'}")
    if context_path.exists():
        preview = context_path.read_text(encoding="utf-8", errors="replace")[:2000]
        console.print(Panel(preview, title="linkedin_context.md Preview", border_style="cyan"))
    else:
        console.print("linkedin_context.md not found.")


@app.command()
def start() -> None:
    """Start the SuperMe interview and save the session."""

    settings = get_settings()
    settings.require_superme()
    client = SuperMeClientWrapper(settings)
    response = client.start_interview(settings.superme_role_id)
    interview_id = extract_interview_id(response)
    if not interview_id:
        raise typer.BadParameter("SuperMe start response did not include an interview ID.")
    _save_session(settings.artifacts_dir, interview_id, response)
    console.print(f"Started interview: [bold]{interview_id}[/bold]")


@app.command()
def status() -> None:
    """Print current interview status."""

    settings = get_settings()
    session = _load_session(settings.artifacts_dir)
    client = SuperMeClientWrapper(settings)
    event = client.get_interview_status(session["interview_id"])
    console.print(Panel(Pretty(event.model_dump()), title="Interview Status", border_style="cyan"))


@app.command()
def ask(
    question: str = Argument(help="Interview question to answer locally."),
    full_context: bool = Option(default=False, help="Send all chunks to NIM instead of retrieved top chunks."),
    long_mode: bool = Option(default=False, help="Allow generation up to NIM_ABSOLUTE_MAX_TOKENS."),
) -> None:
    """Draft a local NIM Gemma answer without sending anything to SuperMe."""

    draft = _draft_with_nim(question, full_context=full_context, long_mode=long_mode)
    _display_draft(draft)
    console.print("[yellow]Local draft only. Nothing was sent to SuperMe.[/yellow]")


@app.command()
def answer(
    question: str | None = Argument(default=None, help="Optional question. If omitted, status or prompt is used."),
    full_context: bool = Option(default=False, help="Send all chunks to NIM instead of retrieved top chunks."),
    long_mode: bool = Option(default=False, help="Allow generation up to NIM_ABSOLUTE_MAX_TOKENS."),
) -> None:
    """Draft an answer with NIM, show private explanation, and ask before sending."""

    settings = get_settings()
    session = None
    status_event = None
    try:
        session = _load_session(settings.artifacts_dir)
        client = SuperMeClientWrapper(settings)
        status_event = client.get_interview_status(session["interview_id"])
    except Exception as exc:
        logger.debug(f"Could not load live status for answer command: {exc}")
        session = None

    current_question = question or _prompt_for_question(status_event)
    _display_interviewer_prompt(current_question, status_event.stage_name if status_event else None)
    if stage_requires_repo_work(status_event.stage_name if status_event else None, current_question):
        console.print(
            "[yellow]This prompt requires repo inspection or code changes. Automated candidate-context drafting is disabled for this stage.[/yellow]"
        )
        if session:
            console.print("[yellow]Inspect the repo first, then come back with a real implementation summary before sending anything.[/yellow]")
        return
    draft = _draft_with_nim(current_question, full_context=full_context, long_mode=long_mode)
    _display_draft(draft)

    if session:
        _send_answer(session["interview_id"], draft, status_event.stage_number if status_event else None)
    else:
        console.print("[yellow]No saved session found; draft was not sent.[/yellow]")


@app.command()
def run(
    poll_seconds: int = Option(default=8, min=2, help="Seconds between status polls."),
    max_empty_polls: int = Option(default=20, min=1, help="Stop after this many polls without input."),
) -> None:
    """Guided start/resume loop with manual approval for every answer."""

    settings = get_settings()
    ensure_dir(settings.artifacts_dir)
    client = SuperMeClientWrapper(settings)
    session_path = _session_path(settings.artifacts_dir)

    if session_path.exists():
        session = read_json(session_path)
        interview_id = session["interview_id"]
        console.print(f"Resuming interview: [bold]{interview_id}[/bold]")
    else:
        response = client.start_interview(settings.superme_role_id)
        interview_id = extract_interview_id(response)
        if not interview_id:
            raise typer.BadParameter("SuperMe start response did not include an interview ID.")
        _save_session(settings.artifacts_dir, interview_id, response)
        console.print(f"Started interview: [bold]{interview_id}[/bold]")

    answerer: NIMGemmaAnswerer | None = None
    empty_polls = 0
    while True:
        event = client.get_interview_status(interview_id)
        console.print(_status_line(event))

        if event.awaiting_input or event.question:
            question = _prompt_for_question(event)
            _display_interviewer_prompt(question, event.stage_name)
            if stage_requires_repo_work(event.stage_name, question):
                console.print(
                    "[yellow]This is a hands-on repo/code task. Automated candidate-context drafting is disabled for this stage.[/yellow]"
                )
                console.print(
                    "[yellow]Use the interviewer prompt above as the task brief, inspect the repo or sandbox, then restart or answer manually with real code findings.[/yellow]"
                )
                return

            if answerer is None:
                llm = _require_available_nim_model()
                retriever = _load_retriever()
                answerer = NIMGemmaAnswerer(retriever, llm, settings=settings)

            draft = answerer.draft_answer(question, top_k=8)
            _display_draft(draft)
            _send_answer(interview_id, draft, event.stage_number)
            empty_polls = 0
            continue

        status_text = event.status.lower()
        if any(token in status_text for token in ("complete", "finished", "ready_to_submit", "ready for submit")):
            console.print("[yellow]Interview appears complete or ready to submit. Final submission still requires exact confirmation.[/yellow]")
            phrase = settings.final_submit_phrase
            confirmation = typer.prompt(f"Type {phrase!r} to submit now, or anything else to stop", default="")
            if confirmation == phrase:
                response = client.submit_interview(interview_id)
                console.print(Panel(Pretty(response), title="Submit Response", border_style="green"))
            else:
                console.print("Stopped without submitting.")
            return

        empty_polls += 1
        if empty_polls >= max_empty_polls:
            console.print("[yellow]No input needed after repeated polls. SuperMe is still handling the current stage, so the guided loop is stopping for now.[/yellow]")
            return
        time.sleep(poll_seconds)


@app.command()
def submit() -> None:
    """Submit the interview only after exact manual confirmation."""

    settings = get_settings()
    session = _load_session(settings.artifacts_dir)
    phrase = settings.final_submit_phrase
    if settings.require_final_submit_approval:
        confirmation = typer.prompt(f"Type exactly {phrase!r} to submit")
    else:
        confirmation = phrase
    if confirmation != phrase:
        console.print("[yellow]Submission cancelled.[/yellow]")
        return
    client = SuperMeClientWrapper(settings)
    response = client.submit_interview(session["interview_id"])
    console.print(Panel(Pretty(response), title="Submit Response", border_style="green"))


if __name__ == "__main__":
    app()
