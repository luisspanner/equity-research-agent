"""Source-aware deterministic inputs for financial-risk analysis."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference


class FinancialRiskMetric(DomainModel):
    """One deterministic metric with the sources needed to reproduce it."""

    metric: NonEmptyString
    value: Decimal
    unit: Literal["currency", "percentage", "multiple"]
    source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)


class FinancialRiskContext(DomainModel):
    """Financial metrics and the source references available for risk analysis."""

    metrics: tuple[FinancialRiskMetric, ...] = Field(min_length=1)
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metric_sources(self) -> "FinancialRiskContext":
        """Ensure each metric cites only sources supplied in this context."""

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
        for metric in self.metrics:
            unknown_source_ids = set(metric.source_ids) - available_source_ids
            if unknown_source_ids:
                unknown_ids = ", ".join(sorted(unknown_source_ids))
                raise ValueError(
                    f"metric refers to unknown source IDs: {unknown_ids}"
                )
        return self
