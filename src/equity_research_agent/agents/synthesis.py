"""Preparation of source-bounded inputs for a research-synthesis LLM call."""

import json

from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_quality import FinancialQualityAnalysis
from equity_research_agent.models.provenance import merge_source_references


def build_research_synthesis_prompt(
    profile: CompanyProfile,
    business_analysis: BusinessAnalysis,
    bear_analysis: BearAnalysis,
    financial_quality_analysis: FinancialQualityAnalysis,
) -> str:
    """Build a deterministic synthesis prompt from sourced qualitative inputs."""

    sources = merge_source_references(
        business_analysis.sources,
        bear_analysis.sources,
        financial_quality_analysis.sources,
    )
    context = {
        "company": {
            "name": profile.name,
            "ticker": profile.security.canonical_symbol,
            "description": profile.description,
        },
        "prior_business_analysis": business_analysis.model_dump(
            mode="json", exclude={"sources"}
        ),
        "prior_bear_analysis": bear_analysis.model_dump(
            mode="json", exclude={"sources"}
        ),
        "prior_financial_quality_analysis": financial_quality_analysis.model_dump(
            mode="json", exclude={"sources"}
        ),
        "sources": [
            {
                "source_id": source.source_id,
                "provider": source.provider,
                "source_type": source.source_type,
                "url": str(source.url),
            }
            for source in sources
        ],
    }

    return """You are the Research Synthesizer for an equity research workflow.

Use only the supplied context. Treat the prior Business, Bear, and Financial
Quality Analyses as LLM interpretations, not as new evidence. Do not invent
facts or perform financial calculations. Produce a balanced research summary,
not an investment recommendation. Cite every factual claim using one or more
supplied source IDs, and identify what still needs further research.

Return JSON with these fields:
- investment_thesis: string
- supporting_points: non-empty array of strings
- risk_summary: non-empty array of strings
- open_research_questions: non-empty array of strings
- evidence: non-empty array of {claim: string, source_ids: non-empty array of strings}
- limitations: array of strings

Research context:
""" + json.dumps(context, indent=2, sort_keys=True)
