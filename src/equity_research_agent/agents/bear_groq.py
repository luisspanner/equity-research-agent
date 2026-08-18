"""Groq-backed execution of the source-bounded Bear Analyst prompt."""

import json
import os
from collections.abc import Mapping
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from equity_research_agent.agents.bear import build_bear_analysis_prompt
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile


class GroqBearAnalystError(RuntimeError):
    """Raised when a Groq Bear Analyst response cannot be used safely."""


class GroqBearAnalyst:
    """Run the Bear Analyst with Groq's OpenAI GPT-OSS 120B model."""

    _API_URL = "https://api.groq.com/openai/v1/chat/completions"
    _DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Create an analyst with explicit credentials and request settings."""

        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if not model.strip():
            raise ValueError("model must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "GroqBearAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        api_key = os.environ.get("GROQ_API_KEY")
        if api_key is None:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        return cls(api_key)

    def analyze(
        self, profile: CompanyProfile, business_analysis: BusinessAnalysis
    ) -> BearAnalysis:
        """Return source-validated bear analysis for one company profile."""

        request_body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": build_bear_analysis_prompt(profile, business_analysis),
                }
            ],
            "response_format": {"type": "json_object"},
        }
        response_payload = self._post(request_body)
        response_content = _response_content(response_payload)

        try:
            analysis_payload = json.loads(response_content)
        except JSONDecodeError:
            raise GroqBearAnalystError(
                "Groq response content must be valid JSON"
            ) from None

        if not isinstance(analysis_payload, dict):
            raise GroqBearAnalystError(
                "Groq response content must be a JSON object"
            )

        analysis_payload["sources"] = [
            source.model_dump(mode="json") for source in business_analysis.sources
        ]
        try:
            return BearAnalysis.model_validate_json(json.dumps(analysis_payload))
        except ValidationError:
            raise GroqBearAnalystError(
                "Groq response does not match the BearAnalysis schema"
            ) from None

    def _post(self, request_body: Mapping[str, object]) -> Mapping[str, object]:
        """Send a JSON chat-completions request without exposing credentials."""

        request = Request(
            self._API_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, UnicodeDecodeError, JSONDecodeError):
            raise GroqBearAnalystError(
                "could not retrieve a valid Groq response"
            ) from None

        if not isinstance(response_payload, dict):
            raise GroqBearAnalystError("Groq response must be a JSON object")
        return response_payload


def _response_content(payload: Mapping[str, object]) -> str:
    """Extract the first text response from a chat-completions payload."""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GroqBearAnalystError("Groq response has no completion choices")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise GroqBearAnalystError("Groq completion choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise GroqBearAnalystError("Groq completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise GroqBearAnalystError("Groq completion message has no text content")
    return content
