"""Typed domain models used at system boundaries."""

from equity_research_agent.models.bear_analysis import BearAnalysis, BearRisk
from equity_research_agent.models.business_analysis import (
    BusinessAnalysis,
    BusinessAnalysisEvidence,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.filings import (
    AnnualReportFormType,
    FilingReference,
)
from equity_research_agent.models.financial_quality import (
    FinancialQualityAnalysis,
    FinancialQualityEvidence,
)
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
from equity_research_agent.models.financials import (
    AnnualFinancials,
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriod,
    IncomeStatement,
    MarketSnapshot,
)
from equity_research_agent.models.metrics import FinancialMetrics, MetricUnavailability
from equity_research_agent.models.provenance import SourceReference
from equity_research_agent.models.synthesis import ResearchSynthesis, SynthesisEvidence

__all__ = [
    "AnnualFinancials",
    "AnnualReportFormType",
    "BalanceSheet",
    "BearAnalysis",
    "BearRisk",
    "BusinessAnalysis",
    "BusinessAnalysisEvidence",
    "CashFlowStatement",
    "CompanyProfile",
    "FilingReference",
    "FiscalPeriod",
    "FinancialMetrics",
    "FinancialQualityAnalysis",
    "FinancialQualityEvidence",
    "FinancialRiskContext",
    "FinancialRiskMetric",
    "IncomeStatement",
    "MarketSnapshot",
    "MetricUnavailability",
    "ResearchSynthesis",
    "SecurityIdentity",
    "SourceReference",
    "SynthesisEvidence",
]
