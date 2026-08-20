"""Structured, source-aware output for a filer's own disclosed risk factors."""

from pydantic import Field, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference


class DisclosedRisk(DomainModel):
    """One risk the filer itself names in its own disclosed risk factors."""

    risk: NonEmptyString
    source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)


class DisclosedRiskAnalysis(DomainModel):
    """LLM interpretation of a filer's own disclosed risks, grounded in sources.

    Distinct from ``BearAnalysis``: this extracts risks the company itself
    names in its filing, not risks inferred from business and financial
    context.
    """

    disclosed_risks: tuple[DisclosedRisk, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...] = ()
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_risk_sources(self) -> "DisclosedRiskAnalysis":
        """Ensure every disclosed risk refers to a supplied source."""

        available_source_ids = {source.source_id for source in self.sources}
        for risk in self.disclosed_risks:
            unknown_source_ids = set(risk.source_ids) - available_source_ids
            if unknown_source_ids:
                unknown_ids = ", ".join(sorted(unknown_source_ids))
                raise ValueError(
                    f"disclosed risk refers to unknown source IDs: {unknown_ids}"
                )
        return self
