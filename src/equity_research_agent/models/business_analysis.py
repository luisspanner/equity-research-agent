"""Structured, source-aware output for qualitative business analysis."""

from pydantic import Field, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference


class BusinessAnalysisEvidence(DomainModel):
    """A factual claim supporting an LLM's qualitative interpretation."""

    claim: NonEmptyString
    source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)


class BusinessAnalysis(DomainModel):
    """LLM interpretation of a company's business, grounded in supplied sources."""

    business_model: NonEmptyString
    primary_offerings: tuple[NonEmptyString, ...] = Field(min_length=1)
    customers_and_end_markets: NonEmptyString
    revenue_model: NonEmptyString
    competitive_positioning: NonEmptyString
    evidence: tuple[BusinessAnalysisEvidence, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...] = ()
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_sources(self) -> "BusinessAnalysis":
        """Ensure every factual claim refers to a supplied source."""

        available_source_ids = {source.source_id for source in self.sources}
        for item in self.evidence:
            unknown_source_ids = set(item.source_ids) - available_source_ids
            if unknown_source_ids:
                unknown_ids = ", ".join(sorted(unknown_source_ids))
                raise ValueError(
                    f"evidence refers to unknown source IDs: {unknown_ids}"
                )
        return self
