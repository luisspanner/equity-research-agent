"""Processing of retrieved primary-source filings."""

from equity_research_agent.filings.text import (
    FilingTextExtractionError,
    extract_filing_text,
)

__all__ = ["FilingTextExtractionError", "extract_filing_text"]
