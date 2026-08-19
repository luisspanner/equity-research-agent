"""External data-provider adapters."""

from equity_research_agent.data.providers.alpha_vantage_provider import (
    AlphaVantageProvider,
    AlphaVantageProviderError,
)
from equity_research_agent.data.providers.base import (
    FilingProvider,
    FinancialDataProvider,
)
from equity_research_agent.data.providers.edgar_provider import (
    EdgarFilingProvider,
    EdgarProviderError,
)

__all__ = [
    "AlphaVantageProvider",
    "AlphaVantageProviderError",
    "EdgarFilingProvider",
    "EdgarProviderError",
    "FilingProvider",
    "FinancialDataProvider",
]
