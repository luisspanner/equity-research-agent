"""Groq-backed execution of the source-bounded Financial Quality Analyst."""

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
    def from_environment(cls) -> "GroqFinancialQualityAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        return cls(groq_api_key_from_environment())

    def analyze(
        self,
        profile: CompanyProfile,
        financial_risk_context: FinancialRiskContext,
    ) -> FinancialQualityAnalysis:
        """Return source-validated financial-quality analysis for one company."""

        request_body = build_json_chat_request(
            self._model,
            build_financial_quality_analysis_prompt(
                profile, financial_risk_context
            ),
        )
        response_payload = post_json_chat_request(
            api_key=self._api_key,
            request_body=request_body,
            timeout_seconds=self._timeout_seconds,
            opener=urlopen,
            error_type=GroqFinancialQualityAnalystError,
        )
        response_content = extract_response_content(
            response_payload, error_type=GroqFinancialQualityAnalystError
        )
        analysis_payload = parse_json_object(
            response_content, error_type=GroqFinancialQualityAnalystError
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
