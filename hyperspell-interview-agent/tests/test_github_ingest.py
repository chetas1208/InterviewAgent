from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.github_ingest import ingest_github, score_repo


class FakeRepo:
    def __init__(
        self,
        name: str,
        description: str,
        language: str,
        *,
        topics: list[str] | None = None,
        fork: bool = False,
        archived: bool = False,
        readme: str = "# README",
    ) -> None:
        self.name = name
        self.description = description
        self.language = language
        self.fork = fork
        self.archived = archived
        self.html_url = f"https://github.com/example/{name}"
        self.stargazers_count = 1
        self.forks_count = 0
        self.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        self.pushed_at = datetime.now(timezone.utc)
        self._topics = topics or []
        self._readme = readme

    def get_topics(self):
        return self._topics

    def get_readme(self):
        return SimpleNamespace(decoded_content=self._readme.encode("utf-8"))

    def get_languages(self):
        return {self.language: 1000}

    def get_commits(self):
        return [SimpleNamespace(commit=SimpleNamespace(message="Initial AI portfolio commit"))]


class FakeUser:
    login = "chetas"

    def __init__(self, repos):
        self._repos = repos

    def get_repos(self):
        return self._repos


class FakeGithub:
    def __init__(self, repos):
        self.user = FakeUser(repos)

    def get_user(self, username=None):
        return self.user


def test_github_ingestion_skips_without_token(tmp_path) -> None:
    result = ingest_github(data_dir=tmp_path, token="", github_client=FakeGithub([]))

    assert result is None
    assert not (tmp_path / "github_context.md").exists()


def test_github_repo_scoring_prefers_ai_full_stack_repos() -> None:
    ai_repo = FakeRepo("ai-portfolio", "LLM Qdrant React portfolio", "TypeScript", topics=["ai", "qdrant"])
    old_fork = FakeRepo("forked-blog", "static blog", "Ruby", fork=True, archived=True, topics=[])

    assert score_repo(ai_repo) > score_repo(old_fork)


def test_github_context_file_is_generated_from_mocked_repo_data(tmp_path) -> None:
    repos = [
        FakeRepo("ai-portfolio", "LLM Qdrant React portfolio", "TypeScript", topics=["ai", "qdrant"]),
        FakeRepo("notes", "Small notes repo", "Markdown", topics=[]),
    ]

    output = ingest_github(data_dir=tmp_path, token="token", username="chetas", github_client=FakeGithub(repos), max_repos=1)

    assert output == tmp_path / "github_context.md"
    text = output.read_text(encoding="utf-8")
    assert "Repository: ai-portfolio" in text
    assert "LLM Qdrant React portfolio" in text
    assert "Initial AI portfolio commit" in text
