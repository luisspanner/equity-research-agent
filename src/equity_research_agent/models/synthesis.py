"""Structured, source-aware output for the final qualitative research synthesis."""

from pydantic import Field, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference


class SynthesisEvidence(DomainModel):
    """A factual claim supporting the research synthesis."""

    claim: NonEmptyString
    source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)


class ResearchSynthesis(DomainModel):
    """LLM research summary, grounded in the supplied source references."""

    investment_thesis: NonEmptyString
    supporting_points: tuple[NonEmptyString, ...] = Field(min_length=1)
    risk_summary: tuple[NonEmptyString, ...] = Field(min_length=1)
    open_research_questions: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence: tuple[SynthesisEvidence, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...] = ()
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_sources(self) -> "ResearchSynthesis":
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
