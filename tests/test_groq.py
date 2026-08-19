"""Focused tests for shared Groq transport and response handling."""

import json
from urllib.request import Request

import pytest

from equity_research_agent.agents._groq import (
    build_json_chat_request,
    extract_response_content,
    post_json_chat_request,
)


class FakeGroqError(RuntimeError):
    """Adapter-style error used to verify helper error translation."""


class FakeResponse:
    """Minimal context-managed HTTP response for shared helper tests."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def extract_content_from_response_payload(payload: object) -> str:
    """Round-trip a fake payload through the shared request helpers."""

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        return FakeResponse(json.dumps(payload).encode())

    response = post_json_chat_request(
        api_key="test-key",
        request_body=build_json_chat_request("test-model", "test prompt"),
        timeout_seconds=10.0,
        opener=fake_urlopen,
        error_type=FakeGroqError,
    )
    return extract_response_content(response, error_type=FakeGroqError)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"choices": ["not an object"]}, "completion choice must be an object"),
        ({"choices": [{}]}, "completion choice has no message"),
        (
            {"choices": [{"message": "not an object"}]},
            "completion choice has no message",
        ),
        (
            {"choices": [{"message": {"content": 42}}]},
            "completion message has no text content",
        ),
    ],
)
def test_nested_response_shape_failures_are_rejected(
    payload: object, message: str
) -> None:
    with pytest.raises(FakeGroqError, match=message):
        extract_content_from_response_payload(payload)


def test_response_content_is_returned_for_valid_nested_shape() -> None:
    payload = {"choices": [{"message": {"content": '{"result": "ok"}'}}]}

    assert extract_content_from_response_payload(payload) == '{"result": "ok"}'
