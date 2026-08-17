"""Preparation of source-bounded inputs for a Business Analyst LLM call."""

import json

from equity_research_agent.models.company import CompanyProfile


def build_business_analysis_prompt(profile: CompanyProfile) -> str:
    """Build a deterministic prompt from the normalized company profile.

    This module deliberately does not call an LLM. A later adapter can send this
    prompt to a selected provider and validate its response as ``BusinessAnalysis``.
    """

    source_context = [
        {
            "source_id": source.source_id,
            "provider": source.provider,
            "source_type": source.source_type,
            "url": str(source.url),
        }
        for source in profile.sources
    ]
    context = {
        "company_name": profile.name,
        "ticker": profile.security.canonical_symbol,
        "country": profile.country,
        "sector": profile.sector,
        "industry": profile.industry,
        "description": profile.description,
        "sources": source_context,
    }

    return """You are the Business Analyst for an equity research workflow.

Use only the supplied company-profile context. Do not invent facts, perform
financial calculations, or rely on knowledge not present in the context. State
missing information in limitations. Separate factual evidence from your
interpretation, and cite every factual claim using one or more supplied source IDs.

Return JSON with these fields:
- business_model: string
- primary_offerings: non-empty array of strings
- customers_and_end_markets: string
- revenue_model: string
- competitive_positioning: string
- evidence: non-empty array of {claim: string, source_ids: non-empty array of strings}
- limitations: array of strings

Company-profile context:
""" + json.dumps(context, indent=2, sort_keys=True)
