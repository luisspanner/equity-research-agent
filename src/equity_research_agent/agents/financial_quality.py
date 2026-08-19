"""Preparation of source-bounded inputs for a Financial Quality Analyst."""

import json

from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_quality import (
    FinancialQualityAnalysis,
    FinancialQualityEvidence,
)
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)


def build_financial_quality_analysis_prompt(
    profile: CompanyProfile,
    financial_risk_context: FinancialRiskContext,
) -> str:
    """Build a deterministic prompt from financial metrics and their sources."""

    context = {
        "company": {
            "name": profile.name,
            "ticker": profile.security.canonical_symbol,
        },
        "financial_risk_context": financial_risk_context.model_dump(mode="json"),
    }

    return """You are the Financial Quality Analyst for an equity research workflow.

Use only the supplied context. Interpret the supplied deterministic financial
metrics; do not invent facts, perform new calculations, apply thresholds,
make forecasts, or make peer comparisons. Every assessment or finding must
name the supplied metric or metrics it relies on and cite exactly the union of
those metrics' source IDs. Do not make figures or financial claims outside the
structured evidence records. Use limitations only for unavailable or
insufficient information.

Return JSON with these fields:
- overall_assessment: {claim: string, metric_names: non-empty array of strings,
  source_ids: non-empty array of strings}
- strengths: array of {claim: string, metric_names: non-empty array
  of strings, source_ids: non-empty array of strings}
- concerns: array of {claim: string, metric_names: non-empty array
  of strings, source_ids: non-empty array of strings}
- limitations: array of strings

Provide an overall assessment and evidence for it. Include strengths or concerns
only when the supplied metrics support them; either array may be empty.

Financial-quality context:
""" + json.dumps(context, indent=2, sort_keys=True)


def validate_financial_quality_provenance(
    analysis: FinancialQualityAnalysis,
    financial_risk_context: FinancialRiskContext,
) -> None:
    """Require context-equivalent sources and exact metric-linked citations."""

    _validate_analysis_sources(analysis, financial_risk_context)

    metric_names = [metric.metric for metric in financial_risk_context.metrics]
    if len(set(metric_names)) != len(metric_names):
        raise ValueError("financial risk context contains duplicate metric names")
    metrics_by_name = {
        metric.metric: metric for metric in financial_risk_context.metrics
    }
    evidence_records = (
        analysis.overall_assessment,
        *analysis.strengths,
        *analysis.concerns,
    )
    for evidence in evidence_records:
        _validate_evidence_metric_provenance(evidence, metrics_by_name)


def _validate_analysis_sources(
    analysis: FinancialQualityAnalysis,
    financial_risk_context: FinancialRiskContext,
) -> None:
    """Require analysis sources to be the full, unaltered context source set."""

    analysis_sources_by_id = {source.source_id: source for source in analysis.sources}
    context_sources_by_id = {
        source.source_id: source for source in financial_risk_context.sources
    }
    if set(analysis_sources_by_id) != set(context_sources_by_id):
        raise ValueError("analysis sources do not match financial risk context sources")

    for source_id, context_source in context_sources_by_id.items():
        if analysis_sources_by_id[source_id] != context_source:
            raise ValueError(
                "analysis source references do not match financial risk context"
            )


def _validate_evidence_metric_provenance(
    evidence: FinancialQualityEvidence,
    metrics_by_name: dict[str, FinancialRiskMetric],
) -> None:
    """Validate one metric-linked finding against its deterministic inputs."""

    unknown_metric_names = set(evidence.metric_names) - set(metrics_by_name)
    if unknown_metric_names:
        names = ", ".join(sorted(unknown_metric_names))
        raise ValueError(f"analysis refers to unknown metric names: {names}")

    expected_source_ids: set[str] = set()
    for metric_name in evidence.metric_names:
        expected_source_ids.update(metrics_by_name[metric_name].source_ids)
    if set(evidence.source_ids) != expected_source_ids:
        raise ValueError("analysis source IDs do not match the referenced metrics")
