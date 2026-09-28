from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config import AppSettings
from src.llm_nim import NIMGemmaClient
from src.llm_nim import split_reasoning_and_final


class FakeChatClient:
    def __init__(self) -> None:
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=self)
        self.models = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="<think>private</think>hello",
                        reasoning_content="",
                    )
                )
            ]
        )

    def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id="google/gemma-4-31b-it")])


def local_settings(**overrides) -> AppSettings:
    values = {
        "nim_base_url": "http://0.0.0.0:8000/v1",
        "nim_api_key": None,
        "nim_enable_reasoning": False,
        "nim_include_reasoning": False,
    }
    values.update(overrides)
    return AppSettings(_env_file=None, **values)


def test_nim_config_loading_defaults() -> None:
    settings = AppSettings(_env_file=None, nim_api_key="key")

    client = NIMGemmaClient(settings=settings, client=FakeChatClient())

    assert client.base_url == "https://integrate.api.nvidia.com/v1"
    assert client.model == "google/gemma-4-31b-it"
    assert settings.nim_enable_reasoning is True
    assert settings.nim_include_reasoning is True


def test_missing_nim_api_key_fails_for_hosted_base_url() -> None:
    settings = AppSettings(_env_file=None, nim_api_key=None, nim_base_url="https://integrate.api.nvidia.com/v1")

    with pytest.raises(RuntimeError, match="Missing NIM_API_KEY"):
        NIMGemmaClient(settings=settings, client=FakeChatClient())


def test_local_nim_uses_not_used_api_key(monkeypatch) -> None:
    captured = {}

    class FakeOpenAI:
        def __init__(self, *, base_url: str, api_key: str) -> None:
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: None))
            self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=[]))

    monkeypatch.setattr("src.llm_nim.OpenAI", FakeOpenAI)

    NIMGemmaClient(settings=local_settings())

    assert captured["base_url"] == "http://0.0.0.0:8000/v1"
    assert captured["api_key"] == "not-used"


def test_reasoning_params_only_included_when_enabled() -> None:
    fake = FakeChatClient()
    client = NIMGemmaClient(settings=local_settings(), client=fake)

    client.generate([{"role": "user", "content": "hello"}])

    assert "extra_body" not in fake.last_kwargs

    reasoning_fake = FakeChatClient()
    reasoning_client = NIMGemmaClient(
        settings=local_settings(nim_enable_reasoning=True, nim_include_reasoning=True),
        client=reasoning_fake,
    )

    reasoning_client.generate([{"role": "user", "content": "hello"}])

    assert reasoning_fake.last_kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True},
        "include_reasoning": True,
    }


def test_model_availability_check() -> None:
    client = NIMGemmaClient(settings=local_settings(), client=FakeChatClient())

    assert client.check_model_available() is True


def test_split_reasoning_and_final_extracts_think_blocks() -> None:
    reasoning, final = split_reasoning_and_final("<think>step one</think>Final answer")

    assert reasoning == "step one"
    assert final == "Final answer"


def test_generate_response_returns_reasoning_and_final() -> None:
    client = NIMGemmaClient(settings=local_settings(), client=FakeChatClient())

    result = client.generate_response([{"role": "user", "content": "hello"}])

    assert result["private_reasoning"] == "private"
    assert result["final_answer"] == "hello"
