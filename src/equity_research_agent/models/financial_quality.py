"""Structured, source-aware output for financial-quality analysis."""

from pydantic import Field, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference


class FinancialQualityEvidence(DomainModel):
    """One sourced claim supporting a financial-quality interpretation."""

    claim: NonEmptyString
    metric_names: tuple[NonEmptyString, ...] = Field(min_length=1)
    source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_references(self) -> "FinancialQualityEvidence":
        """Prevent ambiguous metric and source provenance within one finding."""

        if len(set(self.metric_names)) != len(self.metric_names):
            raise ValueError("metric_names must not contain duplicates")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids must not contain duplicates")
        return self


class FinancialQualityAnalysis(DomainModel):
    """LLM interpretation of deterministic, source-bounded financial metrics."""

    overall_assessment: FinancialQualityEvidence
    strengths: tuple[FinancialQualityEvidence, ...] = ()
    concerns: tuple[FinancialQualityEvidence, ...] = ()
    limitations: tuple[NonEmptyString, ...] = ()
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_sources(self) -> "FinancialQualityAnalysis":
        """Ensure every evidence claim cites a supplied financial source."""

        sources_by_id: dict[str, SourceReference] = {}
        for source in self.sources:
            existing_source = sources_by_id.get(source.source_id)
            if existing_source is not None and existing_source != source:
                raise ValueError(
                    f"source ID {source.source_id} refers to conflicting "
                    "source references"
                )
            sources_by_id[source.source_id] = source

        available_source_ids = set(sources_by_id)
        evidence_records = (
            self.overall_assessment,
            *self.strengths,
            *self.concerns,
        )
        for evidence in evidence_records:
            unknown_source_ids = set(evidence.source_ids) - available_source_ids
            if unknown_source_ids:
                unknown_ids = ", ".join(sorted(unknown_source_ids))
                raise ValueError(
                    f"evidence refers to unknown source IDs: {unknown_ids}"
                )
        return self
