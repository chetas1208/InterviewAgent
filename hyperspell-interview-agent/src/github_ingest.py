"""GitHub repository context ingestion for interview retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DATA_DIR = Path("data")
OUTPUT_FILE_NAME = "github_context.md"

KEYWORDS = {
    "ai",
    "llm",
    "rag",
    "vector",
    "qdrant",
    "portfolio",
    "react",
    "node",
    "express",
    "python",
    "typescript",
    "javascript",
    "visualization",
    "dashboard",
    "nlp",
}


def _safe_topics(repo: Any) -> list[str]:
    try:
        return list(repo.get_topics() or [])
    except Exception:
        return []


def _has_readme(repo: Any) -> bool:
    try:
        repo.get_readme()
        return True
    except Exception:
        return False


def _recently_pushed(repo: Any) -> bool:
    pushed_at = getattr(repo, "pushed_at", None)
    if not pushed_at:
        return False
    if pushed_at.tzinfo is None:
        pushed_at = pushed_at.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - pushed_at).days
    return age_days <= 365


def score_repo(repo: Any) -> float:
    """Score repositories for interview relevance, not popularity."""

    score = 0.0
    topics = _safe_topics(repo)
    language = getattr(repo, "language", None) or ""
    text = " ".join(
        [
            getattr(repo, "name", "") or "",
            getattr(repo, "description", "") or "",
            " ".join(topics),
            language,
        ]
    ).lower()

    for keyword in KEYWORDS:
        if keyword in text:
            score += 2

    if language in {"Python", "TypeScript", "JavaScript"}:
        score += 3
    if _recently_pushed(repo):
        score += 2
    if _has_readme(repo):
        score += 2
    if getattr(repo, "description", None):
        score += 1
    if getattr(repo, "fork", False):
        score -= 5
    if getattr(repo, "archived", False):
        score -= 3
    return score


def safe_decode_readme(repo: Any, max_chars: int = 12000) -> str:
    """Return README text if available, truncated for retrieval quality."""

    try:
        readme = repo.get_readme()
        return readme.decoded_content.decode("utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def get_languages(repo: Any) -> dict[str, int]:
    """Return repository language byte counts."""

    try:
        return dict(repo.get_languages())
    except Exception:
        return {}


def get_recent_commits(repo: Any, limit: int = 10) -> list[str]:
    """Return recent commit subject lines without fetching source files."""

    commits: list[str] = []
    try:
        for commit in repo.get_commits()[:limit]:
            message = commit.commit.message.splitlines()[0].strip()
            if message:
                commits.append(message)
    except Exception:
        pass
    return commits


def repo_to_markdown(repo: Any) -> str:
    """Convert safe repository metadata into retrieval-optimized Markdown."""

    topics = _safe_topics(repo)
    languages = get_languages(repo)
    readme = safe_decode_readme(repo)
    commits = get_recent_commits(repo)

    lines = [
        f"# Repository: {getattr(repo, 'name', 'Unknown')}",
        f"URL: {getattr(repo, 'html_url', '')}",
        f"Description: {getattr(repo, 'description', None) or 'No description'}",
        f"Primary language: {getattr(repo, 'language', None) or 'Unknown'}",
        f"Topics: {', '.join(topics) if topics else 'None'}",
        f"Stars: {getattr(repo, 'stargazers_count', 0)}",
        f"Forks: {getattr(repo, 'forks_count', 0)}",
        f"Created: {getattr(repo, 'created_at', '')}",
        f"Updated: {getattr(repo, 'updated_at', '')}",
        f"Pushed: {getattr(repo, 'pushed_at', '')}",
        "",
        "## Languages",
        str(languages),
        "",
        "## Recent commits",
        "\n".join(f"- {commit}" for commit in commits) if commits else "No recent commits found.",
        "",
        "## README",
        readme if readme else "No README found.",
        "",
    ]
    return "\n".join(lines)


def ingest_github(
    max_repos: int = 12,
    *,
    data_dir: Path = DATA_DIR,
    token: str | None = None,
    username: str | None = None,
    github_client: Any | None = None,
) -> Path | None:
    """Fetch GitHub context and write `data/github_context.md` when configured."""

    load_dotenv()
    import os

    token = token if token is not None else os.getenv("GITHUB_TOKEN")
    username = username if username is not None else os.getenv("GITHUB_USERNAME")
    if not token:
        print("GITHUB_TOKEN not set. Skipping GitHub ingestion.")
        return None

    data_dir.mkdir(parents=True, exist_ok=True)

    if github_client is None:
        try:
            from github import Auth, Github
        except ImportError as exc:
            raise RuntimeError("PyGithub is required for GitHub ingestion. Run `pip install -r requirements.txt`.") from exc

        github_client = Github(auth=Auth.Token(token))

    user = github_client.get_user(username) if username else github_client.get_user()
    repos = list(user.get_repos())
    ranked = sorted(repos, key=score_repo, reverse=True)
    selected = ranked[:max_repos]

    sections = [
        "# GitHub Context",
        "Generated from the configured GitHub account. Verify imported information before interview submission.",
        f"GitHub user: {getattr(user, 'login', username or 'Unknown')}",
        f"Selected repositories: {len(selected)}",
        "",
    ]
    sections.extend(repo_to_markdown(repo) for repo in selected)

    output_file = data_dir / OUTPUT_FILE_NAME
    output_file.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
    print(f"Wrote GitHub context to {output_file}")
    return output_file


if __name__ == "__main__":
    ingest_github()
