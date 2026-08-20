"""Groq-backed execution of the source-bounded Disclosed Risk Analyst prompt."""

import json
from urllib.request import urlopen

from pydantic import ValidationError

from equity_research_agent.agents._groq import (
    build_json_chat_request,
    extract_response_content,
    groq_api_key_from_environment,
    parse_json_object,
    post_json_chat_request,
    validate_groq_settings,
)
from equity_research_agent.agents.disclosed_risk import (
    build_disclosed_risk_analysis_prompt,
    filing_section_source,
)
from equity_research_agent.models.disclosed_risk_analysis import DisclosedRiskAnalysis
from equity_research_agent.models.filings import FilingReference, FilingSection


class GroqDisclosedRiskAnalystError(RuntimeError):
    """Raised when a Groq Disclosed Risk Analyst response cannot be used safely."""


class GroqDisclosedRiskAnalyst:
    """Run the Disclosed Risk Analyst with Groq's OpenAI GPT-OSS 120B model."""

    _DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Create an analyst with explicit credentials and request settings."""

        validate_groq_settings(api_key, model, timeout_seconds)

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "GroqDisclosedRiskAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        return cls(groq_api_key_from_environment())

    def analyze(
        self, filing: FilingReference, section: FilingSection
    ) -> DisclosedRiskAnalysis:
        """Return source-validated disclosed-risk analysis for one filing section."""

        request_body = build_json_chat_request(
            self._model, build_disclosed_risk_analysis_prompt(filing, section)
        )
        response_payload = post_json_chat_request(
            api_key=self._api_key,
            request_body=request_body,
            timeout_seconds=self._timeout_seconds,
            opener=urlopen,
            error_type=GroqDisclosedRiskAnalystError,
        )
        response_content = extract_response_content(
            response_payload, error_type=GroqDisclosedRiskAnalystError
        )
        analysis_payload = parse_json_object(
            response_content, error_type=GroqDisclosedRiskAnalystError
        )

        analysis_payload["sources"] = [
            filing_section_source(filing, section).model_dump(mode="json")
        ]
        try:
            return DisclosedRiskAnalysis.model_validate_json(
                json.dumps(analysis_payload)
            )
        except ValidationError:
            raise GroqDisclosedRiskAnalystError(
                "Groq response does not match the DisclosedRiskAnalysis schema"
            ) from None
