"""Small shared utilities for CLI display and SDK response normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def ensure_dir(path: Path) -> Path:
    """Create a directory if needed and return it."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON object with stable formatting."""

    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def object_to_dict(value: Any) -> dict[str, Any]:
    """Best-effort conversion of SDK responses to dictionaries."""

    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {"value": str(value)}


def extract_interview_id(payload: dict[str, Any]) -> str | None:
    """Extract an interview ID from common SDK response shapes."""

    for key in ("interview_id", "interviewId", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    for key in ("interview", "data", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = extract_interview_id(nested)
            if found:
                return found
    return None


def extract_question(payload: dict[str, Any]) -> str | None:
    """Extract the current interview question from common response shapes."""

    question_keys = (
        "question",
        "current_question",
        "currentQuestion",
        "prompt",
        "input_prompt",
        "message",
    )
    for key in question_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("stage", "current_stage", "data", "result", "interview"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = extract_question(nested)
            if found:
                return found

    stage_message_question = _extract_question_from_stage_messages(payload)
    if stage_message_question:
        return stage_message_question
    return None


def _extract_question_from_stage_messages(payload: dict[str, Any]) -> str | None:
    """Extract the most relevant company prompt from stage message history."""

    stages = payload.get("stages")
    if not isinstance(stages, list):
        return None

    target_stage_numbers: list[int] = []
    direct_stage_number = payload.get("stage_number")
    if isinstance(direct_stage_number, int):
        target_stage_numbers.append(direct_stage_number)
    elif isinstance(direct_stage_number, str) and direct_stage_number.isdigit():
        target_stage_numbers.append(int(direct_stage_number))

    active_stage = extract_active_stage(payload)
    if isinstance(active_stage, dict):
        active_stage_number = active_stage.get("stage_number")
        if isinstance(active_stage_number, int):
            target_stage_numbers.append(active_stage_number)
        elif isinstance(active_stage_number, str) and active_stage_number.isdigit():
            target_stage_numbers.append(int(active_stage_number))

    normalized_targets = {stage_number for stage_number in target_stage_numbers}

    exact_stage_candidates: list[tuple[int, str]] = []
    live_stage_candidates: list[tuple[int, int, str]] = []
    fallback_candidates: list[tuple[int, int, str]] = []

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        messages = stage.get("messages")
        if not isinstance(messages, list):
            continue
        stage_number = stage.get("stage_number")
        stage_rank = int(stage_number) if isinstance(stage_number, int) else 0
        is_live_stage = (
            str(stage.get("status", "")).lower() in {"active", "awaiting_input"}
            or bool(stage.get("manual_intervention"))
        )
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).lower()
            content = message.get("content")
            if role != "company" or not isinstance(content, str) or not content.strip():
                continue
            normalized_content = content.strip()
            if stage_rank in normalized_targets:
                exact_stage_candidates.append((message_index, normalized_content))
            if is_live_stage:
                live_stage_candidates.append((stage_rank, message_index, normalized_content))
            fallback_candidates.append((stage_rank, message_index, normalized_content))

    if exact_stage_candidates:
        exact_stage_candidates.sort(key=lambda item: item[0])
        return exact_stage_candidates[-1][1]
    if live_stage_candidates:
        live_stage_candidates.sort(key=lambda item: (item[0], item[1]))
        return live_stage_candidates[-1][2]
    if not fallback_candidates:
        return None

    fallback_candidates.sort(key=lambda item: (item[0], item[1]))
    return fallback_candidates[-1][2]


def extract_active_stage(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the current active stage from common interview payload shapes."""

    current_stage = payload.get("current_stage")
    if isinstance(current_stage, dict):
        return current_stage

    stages = payload.get("stages")
    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict) and str(stage.get("status", "")).lower() == "active":
                return stage
    return None


def awaiting_input(payload: dict[str, Any]) -> bool:
    """Return whether a status payload appears to need candidate input."""

    for key in ("awaiting_input", "awaitingInput", "needs_input", "requires_input"):
        if key in payload:
            return bool(payload[key])
    status = str(payload.get("status", "")).lower()
    state = str(payload.get("state", "")).lower()
    combined = f"{status} {state}"
    if any(token in combined for token in ("awaiting", "waiting", "needs_input", "input_required")):
        return True

    active_stage = extract_active_stage(payload)
    if isinstance(active_stage, dict):
        return bool(active_stage.get("manual_intervention"))
    return False


def extract_stage_number(payload: dict[str, Any]) -> int | None:
    """Extract the current stage number when present."""

    for key in ("stage_number", "stageNumber", "stage", "step"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    nested = payload.get("current_stage")
    if isinstance(nested, dict):
        return extract_stage_number(nested)
    active_stage = extract_active_stage(payload)
    if isinstance(active_stage, dict):
        value = active_stage.get("stage_number")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def extract_stage_name(payload: dict[str, Any]) -> str | None:
    """Extract the current active stage name when present."""

    active_stage = extract_active_stage(payload)
    if isinstance(active_stage, dict):
        value = active_stage.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_stage_manual_intervention(payload: dict[str, Any]) -> bool:
    """Return whether the active stage requires manual intervention."""

    active_stage = extract_active_stage(payload)
    if isinstance(active_stage, dict):
        return bool(active_stage.get("manual_intervention"))
    return False


def stage_requires_repo_work(stage_name: str | None, question: str | None) -> bool:
    """Return whether the current prompt is a hands-on repo task, not a profile Q&A."""

    exact_stage_names = {
        "orientation & bug triage",
        "fix the critical bug",
        "implement feature from ambiguous spec",
        "review the ai-generated pr",
        "complete the half-built integration",
        "debug a production issue",
    }
    normalized_stage_name = (stage_name or "").strip().lower()
    if normalized_stage_name in exact_stage_names:
        return True

    text = f"{stage_name or ''}\n{question or ''}".lower()
    keyword_hits = sum(
        keyword in text
        for keyword in (
            "repo",
            "codebase",
            "run tests",
            "write a failing test",
            "implement",
            "fix the bug",
            "pull request",
            "integration",
            "migration script",
            "re-index",
            "sandbox",
            "inspect the repo",
            "actual code",
        )
    )
    return keyword_hits >= 2


def normalize_whitespace(text: str) -> str:
    """Collapse excessive spaces while preserving paragraph breaks."""

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
