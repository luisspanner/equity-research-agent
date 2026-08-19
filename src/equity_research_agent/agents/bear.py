"""Preparation of source-bounded inputs for a Bear Analyst LLM call."""

import json

from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_risk import FinancialRiskContext
from equity_research_agent.models.provenance import merge_source_references


def build_bear_analysis_prompt(
    profile: CompanyProfile,
    business_analysis: BusinessAnalysis,
    financial_risk_context: FinancialRiskContext,
) -> str:
    """Build a deterministic bear-case prompt from sourced qualitative inputs."""

    sources = merge_source_references(
        business_analysis.sources, financial_risk_context.sources
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
        "financial_risk_context": financial_risk_context.model_dump(
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

    return """You are the Bear Analyst for an equity research workflow.

Use only the supplied context. Treat the prior Business Analysis as an LLM
interpretation, not as new evidence. Do not invent facts or perform financial
calculations. Identify plausible downside risks and explain each risk's causal
mechanism. Cite each risk using one or more supplied source IDs. State missing
information in limitations. For any claim relying on a financial-risk metric,
cite the source IDs listed for that metric.

Return JSON with these fields:
- risks: non-empty array of {risk: string, downside_mechanism: string,
  source_ids: non-empty array of strings}
- thesis_killers: non-empty array of strings
- limitations: array of strings

Research context:
""" + json.dumps(context, indent=2, sort_keys=True)
