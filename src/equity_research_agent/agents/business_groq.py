"""Groq-backed execution of the source-bounded Business Analyst prompt."""

import json
import os
import re
from collections.abc import Mapping
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from equity_research_agent.agents.business import build_business_analysis_prompt
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile


class GroqBusinessAnalystError(RuntimeError):
    """Raised when a Groq Business Analyst response cannot be used safely."""


_CREDENTIAL_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|authorization)\s*[:=]\s*[^\s,;]+"
)


class GroqBusinessAnalyst:
    """Run the Business Analyst with Groq's OpenAI GPT-OSS 120B model."""

    _API_URL = "https://api.groq.com/openai/v1/chat/completions"
    _DEFAULT_MODEL = "openai/gpt-oss-120b"
    _USER_AGENT = "equity-research-agent/0.1"

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
    def from_environment(cls) -> "GroqBusinessAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        api_key = os.environ.get("GROQ_API_KEY")
        if api_key is None:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        return cls(api_key)

    def analyze(self, profile: CompanyProfile) -> BusinessAnalysis:
        """Return source-validated business analysis for one company profile."""

        request_body = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": build_business_analysis_prompt(profile)}
            ],
            "response_format": {"type": "json_object"},
        }
        response_payload = self._post(request_body)
        response_content = _response_content(response_payload)

        try:
            analysis_payload = json.loads(response_content)
        except JSONDecodeError:
            raise GroqBusinessAnalystError(
                "Groq response content must be valid JSON"
            ) from None

        if not isinstance(analysis_payload, dict):
            raise GroqBusinessAnalystError(
                "Groq response content must be a JSON object"
            )

        analysis_payload["sources"] = [
            source.model_dump(mode="json") for source in profile.sources
        ]
        try:
            return BusinessAnalysis.model_validate_json(json.dumps(analysis_payload))
        except ValidationError:
            raise GroqBusinessAnalystError(
                "Groq response does not match the BusinessAnalysis schema"
            ) from None

    def _post(self, request_body: Mapping[str, object]) -> Mapping[str, object]:
        """Send a JSON chat-completions request without exposing credentials."""

        request = Request(
            self._API_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": self._USER_AGENT,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise GroqBusinessAnalystError(_safe_http_error_message(error)) from None
        except (URLError, UnicodeDecodeError, JSONDecodeError):
            raise GroqBusinessAnalystError(
                "could not retrieve a valid Groq response"
            ) from None

        if not isinstance(response_payload, dict):
            raise GroqBusinessAnalystError("Groq response must be a JSON object")
        return response_payload


def _response_content(payload: Mapping[str, object]) -> str:
    """Extract the first text response from a chat-completions payload."""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GroqBusinessAnalystError("Groq response has no completion choices")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise GroqBusinessAnalystError("Groq completion choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise GroqBusinessAnalystError("Groq completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise GroqBusinessAnalystError("Groq completion message has no text content")
    return content


def _safe_http_error_message(error: HTTPError) -> str:
    """Return a credential-safe Groq HTTP diagnostic when one is available."""

    message = f"Groq HTTP {error.code}"
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError):
        return message

    if not isinstance(payload, Mapping):
        return message
    error_payload = payload.get("error")
    if isinstance(error_payload, Mapping):
        provider_message = error_payload.get("message")
    else:
        provider_message = error_payload
    if not isinstance(provider_message, str):
        return message
    safe_message = _CREDENTIAL_VALUE.sub(r"\1=<redacted>", provider_message)
    return f"{message}: {safe_message}"
