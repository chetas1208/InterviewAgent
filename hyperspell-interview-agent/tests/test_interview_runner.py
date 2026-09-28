from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.interview_runner import app
from src.models import DocumentChunk
from src.models import InterviewEvent
from src.utils import extract_question


runner = CliRunner()


class FakeRetriever:
    def __init__(self, chunks, **kwargs) -> None:
        self.chunks = chunks
        self.embeddings = None

    def save(self, artifacts_dir: Path) -> None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)


def test_ingest_command_does_not_require_linkedin_token(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    data_dir.mkdir()
    artifacts_dir.mkdir()

    settings = SimpleNamespace(
        artifacts_dir=artifacts_dir,
        data_dir=data_dir,
        github_token=None,
        github_username=None,
        linkedin_profile_url="",
        embedding_model_name="test-model",
        cross_encoder_model_name=None,
    )

    chunks = [
        DocumentChunk(
            id="chunk-1",
            text="candidate context",
            source_file="candidate_context.md",
            chunk_index=0,
        )
    ]

    monkeypatch.setattr("src.interview_runner.get_settings", lambda: settings)
    monkeypatch.setattr("src.interview_runner.run_linkedin_pdf_ingest", lambda data_dir: None)
    monkeypatch.setattr("src.interview_runner.build_chunks_from_directory", lambda data_dir: ([data_dir / "candidate_context.md"], chunks))
    monkeypatch.setattr("src.interview_runner.HybridRetriever", FakeRetriever)

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "Loaded 1 documents and built 1 chunks." in result.output


def test_run_reports_superme_controlled_stage_when_not_awaiting_input(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "session.json").write_text('{"interview_id": "int_test"}', encoding="utf-8")

    settings = SimpleNamespace(
        artifacts_dir=artifacts_dir,
        require_final_submit_approval=True,
        final_submit_phrase="SUBMIT HYPERSPELL INTERVIEW",
    )

    event = InterviewEvent(
        interview_id="int_test",
        status="active",
        stage_number=3,
        stage_name="Adaptive Questions",
        question=None,
        awaiting_input=False,
        manual_intervention=False,
        raw={},
    )

    class FakeClient:
        def get_interview_status(self, interview_id: str) -> InterviewEvent:
            return event

    monkeypatch.setattr("src.interview_runner.get_settings", lambda: settings)
    monkeypatch.setattr("src.interview_runner._require_available_nim_model", lambda: object())
    monkeypatch.setattr("src.interview_runner.SuperMeClientWrapper", lambda settings: FakeClient())
    monkeypatch.setattr("src.interview_runner._load_retriever", lambda: object())
    monkeypatch.setattr("src.interview_runner.NIMGemmaAnswerer", lambda retriever, llm, settings=None: object())

    result = runner.invoke(app, ["run", "--max-empty-polls", "1", "--poll-seconds", "2"])

    assert result.exit_code == 0
    assert "Status: active | stage 3 | Adaptive Questions | SuperMe-controlled stage" in result.output
    assert "No input needed after repeated polls." in result.output


def test_extract_question_falls_back_to_latest_stage_company_message() -> None:
    payload = {
        "status": "awaiting_input",
        "stages": [
            {
                "stage_number": 4,
                "status": "awaiting_input",
                "messages": [{"role": "company", "content": "Stage 4 prompt"}],
            },
            {
                "stage_number": 5,
                "status": "awaiting_input",
                "messages": [{"role": "company", "content": "Stage 5 prompt"}],
            },
            {
                "stage_number": 6,
                "status": "active",
                "messages": None,
            },
        ],
    }

    assert extract_question(payload) == "Stage 5 prompt"


def test_extract_question_prefers_active_or_awaiting_stage_messages() -> None:
    payload = {
        "status": "awaiting_input",
        "stage_number": 4,
        "stages": [
            {
                "stage_number": 3,
                "status": "completed",
                "messages": [{"role": "company", "content": "Old stage prompt"}],
            },
            {
                "stage_number": 4,
                "status": "awaiting_input",
                "manual_intervention": True,
                "messages": [{"role": "company", "content": "Current stage prompt"}],
            },
            {
                "stage_number": 5,
                "status": "pending",
                "messages": [{"role": "company", "content": "Future stage prompt"}],
            },
        ],
    }

    assert extract_question(payload) == "Current stage prompt"


def test_run_blocks_candidate_context_drafting_for_repo_stage(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "session.json").write_text('{"interview_id": "int_test"}', encoding="utf-8")

    settings = SimpleNamespace(
        artifacts_dir=artifacts_dir,
        require_final_submit_approval=True,
        final_submit_phrase="SUBMIT HYPERSPELL INTERVIEW",
    )

    event = InterviewEvent(
        interview_id="int_test",
        status="awaiting_input",
        stage_number=5,
        stage_name="Fix the Critical Bug",
        question="Please inspect the repo, write a failing test, implement the fix, and run tests.",
        awaiting_input=True,
        manual_intervention=True,
        raw={},
    )

    class FakeClient:
        def get_interview_status(self, interview_id: str) -> InterviewEvent:
            return event

    def fail_if_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("NIM model loading should not happen for repo work stages")

    monkeypatch.setattr("src.interview_runner.get_settings", lambda: settings)
    monkeypatch.setattr("src.interview_runner.SuperMeClientWrapper", lambda settings: FakeClient())
    monkeypatch.setattr("src.interview_runner._require_available_nim_model", fail_if_called)
    monkeypatch.setattr("src.interview_runner._load_retriever", fail_if_called)
    monkeypatch.setattr("src.interview_runner._prompt_for_question", lambda status_event=None: event.question)

    result = runner.invoke(app, ["run", "--max-empty-polls", "1", "--poll-seconds", "2"])

    assert result.exit_code == 0
    assert "Interviewer Prompt | Fix the Critical Bug" in result.output
    assert "Please inspect the repo" in result.output
    assert "hands-on repo/code task" in result.output
