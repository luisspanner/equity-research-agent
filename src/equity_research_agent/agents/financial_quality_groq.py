"""Groq-backed execution of the source-bounded Financial Quality Analyst."""

import json
import os
from collections.abc import Mapping
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from equity_research_agent.agents.financial_quality import (
    build_financial_quality_analysis_prompt,
    validate_financial_quality_provenance,
)
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_quality import FinancialQualityAnalysis
from equity_research_agent.models.financial_risk import FinancialRiskContext


class GroqFinancialQualityAnalystError(RuntimeError):
    """Raised when a Groq financial-quality response cannot be used safely."""


class GroqFinancialQualityAnalyst:
    """Run the Financial Quality Analyst with Groq's OpenAI GPT-OSS 120B model."""

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
    def from_environment(cls) -> "GroqFinancialQualityAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        api_key = os.environ.get("GROQ_API_KEY")
        if api_key is None:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        return cls(api_key)

    def analyze(
        self,
        profile: CompanyProfile,
        financial_risk_context: FinancialRiskContext,
    ) -> FinancialQualityAnalysis:
        """Return source-validated financial-quality analysis for one company."""

        request_body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": build_financial_quality_analysis_prompt(
                        profile, financial_risk_context
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
        }
        response_payload = self._post(request_body)
        response_content = _response_content(response_payload)

        try:
            analysis_payload = json.loads(response_content)
        except JSONDecodeError:
            raise GroqFinancialQualityAnalystError(
                "Groq response content must be valid JSON"
            ) from None

        if not isinstance(analysis_payload, dict):
            raise GroqFinancialQualityAnalystError(
                "Groq response content must be a JSON object"
            )

        analysis_payload["sources"] = [
            source.model_dump(mode="json")
            for source in financial_risk_context.sources
        ]
        try:
            analysis = FinancialQualityAnalysis.model_validate_json(
                json.dumps(analysis_payload)
            )
        except ValidationError:
            raise GroqFinancialQualityAnalystError(
                "Groq response does not match the FinancialQualityAnalysis schema"
            ) from None
        try:
            validate_financial_quality_provenance(analysis, financial_risk_context)
        except ValueError as error:
            raise GroqFinancialQualityAnalystError(str(error)) from None
        return analysis

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
        except (HTTPError, URLError, UnicodeDecodeError, JSONDecodeError):
            raise GroqFinancialQualityAnalystError(
                "could not retrieve a valid Groq response"
            ) from None

        if not isinstance(response_payload, dict):
            raise GroqFinancialQualityAnalystError(
                "Groq response must be a JSON object"
            )
        return response_payload


def _response_content(payload: Mapping[str, object]) -> str:
    """Extract the first text response from a chat-completions payload."""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GroqFinancialQualityAnalystError(
            "Groq response has no completion choices"
        )

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise GroqFinancialQualityAnalystError(
            "Groq completion choice must be an object"
        )
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise GroqFinancialQualityAnalystError("Groq completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise GroqFinancialQualityAnalystError(
            "Groq completion message has no text content"
        )
    return content
