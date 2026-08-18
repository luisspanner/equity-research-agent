"""Groq-backed execution of the source-bounded research-synthesis prompt."""

import json
import os
from collections.abc import Mapping
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from equity_research_agent.agents.synthesis import (
    _merge_sources,
    build_research_synthesis_prompt,
)
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.synthesis import ResearchSynthesis


class GroqResearchSynthesizerError(RuntimeError):
    """Raised when a Groq research-synthesis response cannot be used safely."""


class GroqResearchSynthesizer:
    """Run the Research Synthesizer with Groq's OpenAI GPT-OSS 120B model."""

    _API_URL = "https://api.groq.com/openai/v1/chat/completions"
    _DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Create a synthesizer with explicit credentials and request settings."""

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
    def from_environment(cls) -> "GroqResearchSynthesizer":
        """Create a synthesizer from the ``GROQ_API_KEY`` environment variable."""

        api_key = os.environ.get("GROQ_API_KEY")
        if api_key is None:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        return cls(api_key)

    def analyze(
        self,
        profile: CompanyProfile,
        business_analysis: BusinessAnalysis,
        bear_analysis: BearAnalysis,
    ) -> ResearchSynthesis:
        """Return source-validated research synthesis for one company."""

        request_body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": build_research_synthesis_prompt(
                        profile, business_analysis, bear_analysis
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
        }
        response_payload = self._post(request_body)
        response_content = _response_content(response_payload)

        try:
            synthesis_payload = json.loads(response_content)
        except JSONDecodeError:
            raise GroqResearchSynthesizerError(
                "Groq response content must be valid JSON"
            ) from None

        if not isinstance(synthesis_payload, dict):
            raise GroqResearchSynthesizerError(
                "Groq response content must be a JSON object"
            )

        synthesis_payload["sources"] = [
            source.model_dump(mode="json")
            for source in _merge_sources(
                business_analysis.sources, bear_analysis.sources
            )
        ]
        try:
            return ResearchSynthesis.model_validate_json(json.dumps(synthesis_payload))
        except ValidationError:
            raise GroqResearchSynthesizerError(
                "Groq response does not match the ResearchSynthesis schema"
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
            raise GroqResearchSynthesizerError(
                "could not retrieve a valid Groq response"
            ) from None

        if not isinstance(response_payload, dict):
            raise GroqResearchSynthesizerError("Groq response must be a JSON object")
        return response_payload


def _response_content(payload: Mapping[str, object]) -> str:
    """Extract the first text response from a chat-completions payload."""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GroqResearchSynthesizerError("Groq response has no completion choices")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise GroqResearchSynthesizerError("Groq completion choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise GroqResearchSynthesizerError("Groq completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise GroqResearchSynthesizerError(
            "Groq completion message has no text content"
        )
    return content
