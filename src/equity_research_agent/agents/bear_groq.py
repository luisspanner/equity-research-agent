"""Groq-backed execution of the source-bounded Bear Analyst prompt."""

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
from equity_research_agent.agents.bear import build_bear_analysis_prompt
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_risk import FinancialRiskContext
from equity_research_agent.models.provenance import merge_source_references


class GroqBearAnalystError(RuntimeError):
    """Raised when a Groq Bear Analyst response cannot be used safely."""


class GroqBearAnalyst:
    """Run the Bear Analyst with Groq's OpenAI GPT-OSS 120B model."""

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
    def from_environment(cls) -> "GroqBearAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        return cls(groq_api_key_from_environment())

    def analyze(
        self,
        profile: CompanyProfile,
        business_analysis: BusinessAnalysis,
        financial_risk_context: FinancialRiskContext,
    ) -> BearAnalysis:
        """Return source-validated bear analysis for one company profile."""

        request_body = build_json_chat_request(
            self._model,
            build_bear_analysis_prompt(
                profile, business_analysis, financial_risk_context
            ),
        )
        response_payload = post_json_chat_request(
            api_key=self._api_key,
            request_body=request_body,
            timeout_seconds=self._timeout_seconds,
            opener=urlopen,
            error_type=GroqBearAnalystError,
        )
        response_content = extract_response_content(
            response_payload, error_type=GroqBearAnalystError
        )
        analysis_payload = parse_json_object(
            response_content, error_type=GroqBearAnalystError
        )

        analysis_payload["sources"] = [
            source.model_dump(mode="json")
            for source in merge_source_references(
                business_analysis.sources, financial_risk_context.sources
            )
        ]
        try:
            return BearAnalysis.model_validate_json(json.dumps(analysis_payload))
        except ValidationError:
            raise GroqBearAnalystError(
                "Groq response does not match the BearAnalysis schema"
            ) from None
