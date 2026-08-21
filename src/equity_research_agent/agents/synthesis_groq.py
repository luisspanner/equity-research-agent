"""Groq-backed execution of the source-bounded research-synthesis prompt."""

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
from equity_research_agent.agents.synthesis import build_research_synthesis_prompt
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.disclosed_risk_analysis import DisclosedRiskAnalysis
from equity_research_agent.models.financial_quality import FinancialQualityAnalysis
from equity_research_agent.models.provenance import merge_source_references
from equity_research_agent.models.synthesis import ResearchSynthesis


class GroqResearchSynthesizerError(RuntimeError):
    """Raised when a Groq research-synthesis response cannot be used safely."""


class GroqResearchSynthesizer:
    """Run the Research Synthesizer with Groq's OpenAI GPT-OSS 120B model."""

    _DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Create a synthesizer with explicit credentials and request settings."""

        validate_groq_settings(api_key, model, timeout_seconds)

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "GroqResearchSynthesizer":
        """Create a synthesizer from the ``GROQ_API_KEY`` environment variable."""

        return cls(groq_api_key_from_environment())

    def analyze(
        self,
        profile: CompanyProfile,
        business_analysis: BusinessAnalysis,
        bear_analysis: BearAnalysis,
        financial_quality_analysis: FinancialQualityAnalysis,
        disclosed_risk_analysis: DisclosedRiskAnalysis | None,
    ) -> ResearchSynthesis:
        """Return source-validated research synthesis for one company."""

        request_body = build_json_chat_request(
            self._model,
            build_research_synthesis_prompt(
                profile,
                business_analysis,
                bear_analysis,
                financial_quality_analysis,
                disclosed_risk_analysis,
            ),
        )
        response_payload = post_json_chat_request(
            api_key=self._api_key,
            request_body=request_body,
            timeout_seconds=self._timeout_seconds,
            opener=urlopen,
            error_type=GroqResearchSynthesizerError,
        )
        response_content = extract_response_content(
            response_payload, error_type=GroqResearchSynthesizerError
        )
        synthesis_payload = parse_json_object(
            response_content, error_type=GroqResearchSynthesizerError
        )

        synthesis_payload["sources"] = [
            source.model_dump(mode="json")
            for source in merge_source_references(
                business_analysis.sources,
                bear_analysis.sources,
                financial_quality_analysis.sources,
                disclosed_risk_analysis.sources
                if disclosed_risk_analysis is not None
                else (),
            )
        ]
        try:
            return ResearchSynthesis.model_validate_json(json.dumps(synthesis_payload))
        except ValidationError:
            raise GroqResearchSynthesizerError(
                "Groq response does not match the ResearchSynthesis schema"
            ) from None
