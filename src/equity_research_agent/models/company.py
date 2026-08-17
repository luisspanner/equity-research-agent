"""Company and security identity domain models."""

from pydantic import Field

from equity_research_agent.models.common import (
    Cik,
    CurrencyCode,
    DomainModel,
    NonEmptyString,
)
from equity_research_agent.models.provenance import SourceReference


class SecurityIdentity(DomainModel):
    """A listed security, separate from its issuer reporting identity."""

    input_symbol: NonEmptyString
    canonical_symbol: NonEmptyString
    exchange: NonEmptyString
    listing_currency: CurrencyCode
    reporting_currency: CurrencyCode | None = None
    cik: Cik | None = None


class CompanyProfile(DomainModel):
    """Normalized company facts accompanied by their source references."""

    security: SecurityIdentity
    name: NonEmptyString
    description: NonEmptyString
    country: NonEmptyString | None = None
    sector: NonEmptyString | None = None
    industry: NonEmptyString | None = None
    sources: tuple[SourceReference, ...] = Field(min_length=1)
