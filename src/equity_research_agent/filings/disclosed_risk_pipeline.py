"""Orchestration from a ticker to one filing-derived disclosed-risk analysis.

Composes capabilities that already exist separately -- CIK resolution, annual
report discovery, document retrieval, sectioning, and Risk Factors selection
-- into the one bounded path the Disclosed Risk Analyst needs. Every *expected*
reason a filing cannot supply an analysis (no resolvable CIK, no annual report
on file, a filing shape sectioning cannot read, no unique Risk Factors section)
becomes a typed unavailable result rather than an exception, so a filing-side
gap does not fail an entire research run. Genuine provider or transport
failures are not caught here and propagate to the caller, the same as any
other provider call in the workflow.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from equity_research_agent.data.providers.base import FilingProvider
from equity_research_agent.data.providers.edgar import EdgarNormalizationError
from equity_research_agent.filings.risk_factors import (
    RiskFactorsSectionUnavailableReason,
    select_risk_factors_section,
)
from equity_research_agent.filings.sections import (
    FilingSectioningError,
    extract_filing_sections,
)
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.disclosed_risk_analysis import DisclosedRiskAnalysis
from equity_research_agent.models.filings import FilingReference, FilingSection


class DisclosedRiskUnavailableReason(StrEnum):
    """Why filing-derived disclosed-risk analysis could not be produced."""

    CIK_UNRESOLVED = "cik_unresolved"
    ANNUAL_REPORT_NOT_FOUND = "annual_report_not_found"
    FILING_NOT_SECTIONABLE = "filing_not_sectionable"
    RISK_FACTORS_SECTION_UNAVAILABLE = "risk_factors_section_unavailable"


@dataclass(frozen=True)
class DisclosedRiskPipelineResult:
    """One disclosed-risk analysis, or an explicit reason it is unavailable.

    Exactly one of ``analysis`` and ``unavailable_reason`` is present.
    ``risk_factors_reason`` carries the more specific reason
    ``select_risk_factors_section`` returned, and is only present alongside
    ``RISK_FACTORS_SECTION_UNAVAILABLE``.
    """

    analysis: DisclosedRiskAnalysis | None = None
    unavailable_reason: DisclosedRiskUnavailableReason | None = None
    risk_factors_reason: RiskFactorsSectionUnavailableReason | None = None

    def __post_init__(self) -> None:
        if (self.analysis is None) == (self.unavailable_reason is None):
            raise ValueError(
                "exactly one of analysis and unavailable_reason must be provided"
            )
        has_risk_factors_reason = (
            self.unavailable_reason
            == DisclosedRiskUnavailableReason.RISK_FACTORS_SECTION_UNAVAILABLE
        )
        if (self.risk_factors_reason is not None) != has_risk_factors_reason:
            raise ValueError(
                "risk_factors_reason must be provided if and only if "
                "unavailable_reason is RISK_FACTORS_SECTION_UNAVAILABLE"
            )


class DisclosedRiskAnalyst(Protocol):
    """Produce a structured disclosed-risk analysis from one filing section."""

    def analyze(
        self, filing: FilingReference, section: FilingSection
    ) -> DisclosedRiskAnalysis:
        """Analyze the risks a filer discloses in one section of a filing."""


def resolve_disclosed_risk_analysis(
    ticker: str,
    profile: CompanyProfile,
    filing_provider: FilingProvider,
    disclosed_risk_analyst: DisclosedRiskAnalyst,
) -> DisclosedRiskPipelineResult:
    """Return a filing-derived disclosed-risk analysis, or why one is unavailable.

    Prefers the CIK already carried by ``profile.security.cik``, resolving
    through SEC EDGAR only when the profile did not supply one, to avoid an
    extra network call in the common case.
    """

    cik = profile.security.cik
    if cik is None:
        try:
            cik = filing_provider.resolve_cik(ticker)
        except EdgarNormalizationError:
            return DisclosedRiskPipelineResult(
                unavailable_reason=DisclosedRiskUnavailableReason.CIK_UNRESOLVED
            )

    try:
        filing = filing_provider.get_latest_annual_report(cik)
    except EdgarNormalizationError:
        return DisclosedRiskPipelineResult(
            unavailable_reason=DisclosedRiskUnavailableReason.ANNUAL_REPORT_NOT_FOUND
        )

    retrieved = filing_provider.get_document(filing)

    try:
        sectioned = extract_filing_sections(retrieved)
    except FilingSectioningError:
        return DisclosedRiskPipelineResult(
            unavailable_reason=DisclosedRiskUnavailableReason.FILING_NOT_SECTIONABLE
        )

    selection = select_risk_factors_section(sectioned)
    if not selection.is_available:
        assert selection.unavailable_reason is not None
        return DisclosedRiskPipelineResult(
            unavailable_reason=(
                DisclosedRiskUnavailableReason.RISK_FACTORS_SECTION_UNAVAILABLE
            ),
            risk_factors_reason=selection.unavailable_reason,
        )

    assert selection.section is not None
    analysis = disclosed_risk_analyst.analyze(filing, selection.section)
    return DisclosedRiskPipelineResult(analysis=analysis)
