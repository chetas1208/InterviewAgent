"""Defensive wrapper around the optional SuperMe SDK."""

from __future__ import annotations

import importlib
from typing import Any, Callable

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import AppSettings
from .models import InterviewEvent
from .utils import awaiting_input, extract_interview_id, extract_question, extract_stage_manual_intervention, extract_stage_name, extract_stage_number, object_to_dict


class SuperMeIntegrationError(RuntimeError):
    """Raised when SuperMe SDK integration cannot proceed safely."""


class SuperMeClientWrapper:
    """Runtime adapter for SuperMe's private SDK.

    The SDK package is intentionally optional so local retrieval/tests still run
    before live credentials and the private package are available.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        """Instantiate and return the SDK client."""

        if self._client is None:
            self.settings.require_superme()
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        try:
            module = importlib.import_module("superme_sdk")
        except ImportError as exc:
            raise SuperMeIntegrationError(
                "Could not import `superme_sdk`. Install the private SuperMe SDK package or wheel first."
            ) from exc

        api_key = self.settings.superme_api_key
        if api_key is None:
            raise SuperMeIntegrationError("SUPERME_API_KEY is required.")
        secret = api_key.get_secret_value()

        for class_name in ("SuperMeClient", "Client", "SuperMe"):
            client_class = getattr(module, class_name, None)
            if client_class is None:
                continue
            for args, kwargs in (
                ((), {"api_key": secret}),
                ((secret,), {}),
                ((), {}),
            ):
                try:
                    return client_class(*args, **kwargs)
                except TypeError:
                    continue
        raise SuperMeIntegrationError(
            "Imported `superme_sdk`, but could not find a supported client class. "
            "Expected one of: SuperMeClient, Client, SuperMe."
        )

    def start_interview(self, role_id: str | None = None) -> dict[str, Any]:
        """Start an interview and return the raw SDK response as a dictionary."""

        role = role_id or self.settings.superme_role_id
        return self._call_with_variants(
            ("start_interview", "create_interview", "interviews.start", "interviews.create"),
            ((), {"role_id": role}),
            ((role,), {}),
            ((), {"roleId": role}),
        )

    def get_interview_status(self, interview_id: str) -> InterviewEvent:
        """Fetch and normalize interview status."""

        payload = self._call_with_variants(
            ("get_interview_status", "interview_status", "get_status", "interviews.get_status", "interviews.status"),
            ((), {"interview_id": interview_id}),
            ((interview_id,), {}),
            ((), {"interviewId": interview_id}),
        )
        return InterviewEvent(
            interview_id=extract_interview_id(payload) or interview_id,
            status=str(payload.get("status") or payload.get("state") or "unknown"),
            stage_number=extract_stage_number(payload),
            stage_name=extract_stage_name(payload),
            question=extract_question(payload),
            awaiting_input=awaiting_input(payload),
            manual_intervention=extract_stage_manual_intervention(payload),
            raw=payload,
        )

    def get_interview_transcript(self, interview_id: str) -> dict[str, Any]:
        """Fetch transcript if the SDK supports it."""

        return self._call_with_variants(
            ("get_interview_transcript", "interview_transcript", "get_transcript", "interviews.transcript"),
            ((), {"interview_id": interview_id}),
            ((interview_id,), {}),
            ((), {"interviewId": interview_id}),
        )

    def stream_interview(self, interview_id: str) -> Any:
        """Return the SDK interview event stream if supported."""

        method_names = ("stream_interview", "interviews.stream")
        variants = (
            ((), {"interview_id": interview_id}),
            ((interview_id,), {}),
            ((), {"interviewId": interview_id}),
        )
        methods = [(name, self._resolve_method(name)) for name in method_names]
        methods = [(name, method) for name, method in methods if method is not None]
        if not methods:
            raise SuperMeIntegrationError(
                "The installed SuperMe SDK does not expose stream_interview. Polling status is still supported if get_interview_status exists."
            )
        last_type_error: TypeError | None = None
        for method_name, method in methods:
            for args, kwargs in variants:
                try:
                    return self._retry_call(method, *args, **{k: v for k, v in kwargs.items() if v is not None})
                except TypeError as exc:
                    last_type_error = exc
                    continue
        raise SuperMeIntegrationError(f"Found stream_interview, but its signature did not match supported patterns: {last_type_error}")

    def send_interview_message(
        self,
        interview_id: str,
        message: str,
        stage_number: int | None = None,
        attachments: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send a manually approved response through the SDK."""

        kwargs = {"interview_id": interview_id, "message": message}
        if stage_number is not None:
            kwargs["stage_number"] = stage_number
        if attachments:
            kwargs["attachments"] = attachments

        return self._call_with_variants(
            ("send_interview_message", "send_message", "interviews.send_message", "interviews.respond"),
            ((), kwargs),
            ((interview_id, message), {}),
            ((), {"interviewId": interview_id, "message": message, "stageNumber": stage_number}),
        )

    def submit_interview(self, interview_id: str) -> dict[str, Any]:
        """Submit the interview after exact manual confirmation."""

        return self._call_with_variants(
            ("submit_interview", "submit", "interviews.submit"),
            ((), {"interview_id": interview_id}),
            ((interview_id,), {}),
            ((), {"interviewId": interview_id}),
        )

    def _resolve_method(self, method_name: str) -> Callable[..., Any] | None:
        target = self.client
        for part in method_name.split("."):
            target = getattr(target, part, None)
            if target is None:
                return None
        return target if callable(target) else None

    def _call_with_variants(
        self,
        method_names: tuple[str, ...],
        *variants: tuple[tuple[Any, ...], dict[str, Any]],
    ) -> dict[str, Any]:
        methods = [(name, self._resolve_method(name)) for name in method_names]
        methods = [(name, method) for name, method in methods if method is not None]
        if not methods:
            raise SuperMeIntegrationError(
                "The installed SuperMe SDK does not expose any expected method: "
                f"{', '.join(method_names)}. Check the SDK docs and update `superme_client.py`."
            )

        last_type_error: TypeError | None = None
        for method_name, method in methods:
            for args, kwargs in variants:
                try:
                    return object_to_dict(self._retry_call(method, *args, **{k: v for k, v in kwargs.items() if v is not None}))
                except TypeError as exc:
                    last_type_error = exc
                    continue
        raise SuperMeIntegrationError(
            "Found a SuperMe SDK method, but its signature did not match the supported call patterns. "
            f"Last TypeError: {last_type_error}"
        )

    @retry(
        retry=retry_if_exception(lambda exc: not isinstance(exc, (TypeError, SuperMeIntegrationError)) and _is_transient(exc)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _retry_call(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return method(*args, **kwargs)


def _is_transient(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    name = exc.__class__.__name__.lower()
    return any(token in name for token in ("timeout", "connection", "network", "temporary"))
