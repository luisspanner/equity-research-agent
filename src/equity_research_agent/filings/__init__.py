"""Processing of retrieved primary-source filings."""

from equity_research_agent.filings.risk_factors import (
    RiskFactorsSectionSelection,
    RiskFactorsSectionUnavailableReason,
    select_risk_factors_section,
)
from equity_research_agent.filings.sections import (
    FilingSectioningError,
    extract_filing_sections,
)
from equity_research_agent.filings.text import (
    FilingTextExtractionError,
    extract_filing_text,
)

__all__ = [
    "FilingSectioningError",
    "FilingTextExtractionError",
    "RiskFactorsSectionSelection",
    "RiskFactorsSectionUnavailableReason",
    "extract_filing_sections",
    "extract_filing_text",
    "select_risk_factors_section",
]
