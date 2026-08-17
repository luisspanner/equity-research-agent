"""Models for recording the origin of normalized data."""

from datetime import date, datetime
from urllib.parse import parse_qsl

from pydantic import HttpUrl, field_validator, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString


class SourceReference(DomainModel):
    """A source with either a known capture date or an exact retrieval timestamp."""

    provider: NonEmptyString
    source_type: NonEmptyString
    source_id: NonEmptyString
    url: HttpUrl
    captured_on: date | None = None
    retrieved_at: datetime | None = None
    period_end: date | None = None

    @field_validator("url")
    @classmethod
    def reject_credential_bearing_url(cls, url: HttpUrl) -> HttpUrl:
        """Prevent source artifacts from retaining API credentials in query strings."""

        credential_keys = {"apikey", "api_key", "token"}
        query_parameters = parse_qsl(url.query or "", keep_blank_values=True)
        if any(key.lower() in credential_keys for key, _ in query_parameters):
            raise ValueError("source URL must not contain credential query parameters")

        return url

    @model_validator(mode="after")
    def validate_retrieval_time(self) -> "SourceReference":
        """Require one unambiguous representation of when the source was obtained."""

        if (self.captured_on is None) == (self.retrieved_at is None):
            raise ValueError("provide exactly one of captured_on or retrieved_at")

        if self.retrieved_at is not None and self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")

        return self
