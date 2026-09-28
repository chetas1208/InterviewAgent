"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings with secrets kept out of logs and terminal output."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    superme_api_key: SecretStr | None = None
    superme_role_id: str = "43A0pbylxajHuP7wQ8m3"

    nim_api_key: SecretStr | None = None
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_model: str = "google/gemma-4-31b-it"
    nim_enable_reasoning: bool = True
    nim_include_reasoning: bool = True
    nim_max_tokens: int = 1200
    nim_long_max_tokens: int = 2500
    nim_absolute_max_tokens: int = 6000
    nim_temperature: float = 0.2
    require_answer_approval: bool = True
    require_final_submit_approval: bool = True
    final_submit_phrase: str = "SUBMIT HYPERSPELL INTERVIEW"

    github_token: SecretStr | None = None
    github_username: str | None = None
    linkedin_profile_url: str | None = None

    data_dir: Path = Path("data")
    artifacts_dir: Path = Path("artifacts")
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    cross_encoder_model_name: str | None = None

    def require_superme(self) -> None:
        """Raise if live SuperMe commands cannot authenticate."""

        if not self.superme_api_key or not self.superme_api_key.get_secret_value().strip():
            raise RuntimeError("SUPERME_API_KEY is required for live SuperMe interview commands.")
        if not self.superme_role_id.strip():
            raise RuntimeError("SUPERME_ROLE_ID is required for starting an interview.")

    def is_local_nim(self) -> bool:
        """Return whether the configured NIM endpoint is local."""

        base_url = self.nim_base_url.lower()
        return any(host in base_url for host in ("localhost", "127.0.0.1", "0.0.0.0"))

    def require_nim(self) -> None:
        """Raise if hosted NVIDIA NIM cannot authenticate."""

        has_key = bool(self.nim_api_key and self.nim_api_key.get_secret_value().strip())
        if not has_key and not self.is_local_nim():
            raise RuntimeError("Missing NIM_API_KEY for hosted NVIDIA NIM endpoint.")


def get_settings() -> AppSettings:
    """Load `.env` and return typed settings."""

    load_dotenv()
    return AppSettings()
