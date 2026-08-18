"""Structured, source-aware output for qualitative bear-case analysis."""

from pydantic import Field, model_validator

from equity_research_agent.models.common import DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference


class BearRisk(DomainModel):
    """A downside risk and the mechanism through which it could affect the company."""

    risk: NonEmptyString
    downside_mechanism: NonEmptyString
    source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)


class BearAnalysis(DomainModel):
    """LLM interpretation of a company's downside case, grounded in sources."""

    risks: tuple[BearRisk, ...] = Field(min_length=1)
    thesis_killers: tuple[NonEmptyString, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...] = ()
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_risk_sources(self) -> "BearAnalysis":
        """Ensure every downside risk refers to a supplied source."""

        available_source_ids = {source.source_id for source in self.sources}
        for risk in self.risks:
            unknown_source_ids = set(risk.source_ids) - available_source_ids
            if unknown_source_ids:
                unknown_ids = ", ".join(sorted(unknown_source_ids))
                raise ValueError(
                    f"risk refers to unknown source IDs: {unknown_ids}"
                )
        return self
