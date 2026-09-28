"""NVIDIA NIM Gemma client using the OpenAI-compatible chat API."""

from __future__ import annotations

import re
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AppSettings, get_settings

try:  # Imported lazily enough that tests can inject a fake client.
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    OpenAI = None  # type: ignore[assignment]


def split_reasoning_and_final(raw_text: str) -> tuple[str, str]:
    """Extract local-only reasoning from `<think>` blocks when present."""

    if not raw_text:
        return "", ""
    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
    matches = pattern.findall(raw_text)
    private_reasoning = "\n\n".join(match.strip() for match in matches if match.strip())
    final_answer = pattern.sub("", raw_text).strip()
    return private_reasoning, final_answer


class NIMGemmaClient:
    """Small wrapper around NVIDIA NIM's OpenAI-compatible chat API."""

    def __init__(self, settings: AppSettings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.nim_base_url
        self.model = self.settings.nim_model
        self.api_key = self.settings.nim_api_key.get_secret_value() if self.settings.nim_api_key else None

        self.settings.require_nim()

        if client is not None:
            self.client = client
            return

        if OpenAI is None:
            raise RuntimeError("The `openai` package is required for NVIDIA NIM. Run `pip install -r requirements.txt`.")

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "not-used",
        )

    def check_model_available(self) -> bool:
        """Return True if the configured model is visible on this endpoint."""

        try:
            models = self.client.models.list()
            available = {model.id for model in models.data}
            return self.model in available
        except Exception:
            return False

    @retry(wait=wait_exponential(min=1, max=12), stop=stop_after_attempt(3), reraise=True)
    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate a final answer string using Gemma through NVIDIA NIM."""

        result = self.generate_response(messages, max_tokens=max_tokens, temperature=temperature)
        return result["final_answer"]

    @retry(wait=wait_exponential(min=1, max=12), stop=stop_after_attempt(3), reraise=True)
    def generate_response(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, str]:
        """Generate a response and separate local reasoning from the final answer."""

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.settings.nim_max_tokens,
            "temperature": temperature if temperature is not None else self.settings.nim_temperature,
            "stream": False,
        }

        if self.settings.nim_enable_reasoning:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": True},
                "include_reasoning": self.settings.nim_include_reasoning,
            }

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        content = (message.content or "").strip()
        reasoning_content = (getattr(message, "reasoning_content", "") or "").strip()
        extracted_reasoning, final_answer = split_reasoning_and_final(content)
        private_reasoning = reasoning_content or extracted_reasoning

        if not final_answer:
            raise RuntimeError("NIM returned an empty answer.")

        return {
            "private_reasoning": private_reasoning.strip(),
            "final_answer": final_answer.strip(),
            "raw_content": content,
        }
