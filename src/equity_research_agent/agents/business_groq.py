"""Groq-backed execution of the source-bounded Business Analyst prompt."""

import json
import re
from collections.abc import Mapping
from json import JSONDecodeError
from urllib.error import HTTPError
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
from equity_research_agent.agents.business import build_business_analysis_prompt
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile


class GroqBusinessAnalystError(RuntimeError):
    """Raised when a Groq Business Analyst response cannot be used safely."""


_CREDENTIAL_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|authorization)\s*[:=]\s*"
    r"(?:Bearer\s+)?[^\s,;]+"
)


class GroqBusinessAnalyst:
    """Run the Business Analyst with Groq's OpenAI GPT-OSS 120B model."""

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
    def from_environment(cls) -> "GroqBusinessAnalyst":
        """Create an analyst from the ``GROQ_API_KEY`` environment variable."""

        return cls(groq_api_key_from_environment())

    def analyze(self, profile: CompanyProfile) -> BusinessAnalysis:
        """Return source-validated business analysis for one company profile."""

        request_body = build_json_chat_request(
            self._model, build_business_analysis_prompt(profile)
        )
        response_payload = post_json_chat_request(
            api_key=self._api_key,
            request_body=request_body,
            timeout_seconds=self._timeout_seconds,
            opener=urlopen,
            error_type=GroqBusinessAnalystError,
            http_error_message=_safe_http_error_message,
        )
        response_content = extract_response_content(
            response_payload, error_type=GroqBusinessAnalystError
        )
        analysis_payload = parse_json_object(
            response_content, error_type=GroqBusinessAnalystError
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
