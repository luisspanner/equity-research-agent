"""Shared transport helpers for Groq-backed analysts."""

import json
import os
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from json import JSONDecodeError
from typing import Protocol, Self
from urllib.error import HTTPError, URLError
from urllib.request import Request

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "equity-research-agent/0.1"


class _ReadableResponse(Protocol):
    """Minimal response behavior required by the Groq transport."""

    def read(self) -> bytes: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool | None: ...


type GroqOpener = Callable[..., AbstractContextManager[_ReadableResponse]]
type ErrorType = type[RuntimeError]


def validate_groq_settings(
    api_key: str, model: str, timeout_seconds: float
) -> None:
    """Validate settings shared by every Groq-backed analyst."""

    if not api_key.strip():
        raise ValueError("api_key must not be blank")
    if not model.strip():
        raise ValueError("model must not be blank")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")


def groq_api_key_from_environment() -> str:
    """Return the configured Groq API key."""

    api_key = os.environ.get("GROQ_API_KEY")
    if api_key is None:
        raise ValueError("GROQ_API_KEY environment variable is not set")
    return api_key


def build_json_chat_request(model: str, prompt: str) -> dict[str, object]:
    """Build a JSON-mode chat-completions request body."""

    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }


def post_json_chat_request(
    *,
    api_key: str,
    request_body: Mapping[str, object],
    timeout_seconds: float,
    opener: GroqOpener,
    error_type: ErrorType,
    http_error_message: Callable[[HTTPError], str] | None = None,
) -> Mapping[str, object]:
    """Send one Groq request and return its decoded JSON object."""

    request = Request(
        GROQ_API_URL,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": GROQ_USER_AGENT,
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        message = (
            http_error_message(error)
            if http_error_message is not None
            else "could not retrieve a valid Groq response"
        )
        raise error_type(message) from None
    except (URLError, UnicodeDecodeError, JSONDecodeError):
        raise error_type("could not retrieve a valid Groq response") from None

    if not isinstance(response_payload, dict):
        raise error_type("Groq response must be a JSON object")
    return response_payload


def extract_response_content(
    payload: Mapping[str, object], *, error_type: ErrorType
) -> str:
    """Extract the first text response from a chat-completions payload."""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise error_type("Groq response has no completion choices")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise error_type("Groq completion choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise error_type("Groq completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise error_type("Groq completion message has no text content")
    return content


def parse_json_object(content: str, *, error_type: ErrorType) -> dict[str, object]:
    """Parse assistant content and require a JSON object."""

    try:
        payload = json.loads(content)
    except JSONDecodeError:
        raise error_type("Groq response content must be valid JSON") from None

    if not isinstance(payload, dict):
        raise error_type("Groq response content must be a JSON object")
    return payload
