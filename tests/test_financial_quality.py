"""Tests for Financial Quality Analyst preparation and output models."""

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from equity_research_agent.agents.financial_quality import (
    build_financial_quality_analysis_prompt,
    validate_financial_quality_provenance,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.financial_quality import (
    FinancialQualityAnalysis,
    FinancialQualityEvidence,
)
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
from equity_research_agent.models.provenance import SourceReference


def make_source() -> SourceReference:
    """Create stable financial provenance for Financial Quality fixtures."""

    return SourceReference(
        provider="test_provider",
        source_type="income_statement",
        source_id="TEST-income-2025",
        url=HttpUrl("https://example.com/income-statement"),
        captured_on=date(2026, 8, 19),
    )


def make_profile() -> CompanyProfile:
    """Create normalized company context for Financial Quality tests."""

    profile_source = SourceReference(
        provider="test_provider",
        source_type="company_overview",
        source_id="TEST-overview",
        url=HttpUrl("https://example.com/company-overview"),
        captured_on=date(2026, 8, 19),
    )
    return CompanyProfile(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency="USD",
        ),
        name="Test Company",
        description="Test Company sells enterprise software subscriptions.",
        sources=(profile_source,),
    )


def make_financial_risk_context() -> FinancialRiskContext:
    """Create sourced deterministic financial context for Financial Quality tests."""

    source = make_source()
    return FinancialRiskContext(
        metrics=(
            FinancialRiskMetric(
                metric="operating_margin",
                value=Decimal("0.25"),
                unit="percentage",
                source_ids=(source.source_id,),
            ),
        ),
        sources=(source,),
    )


def test_prompt_preserves_the_financial_evidence_boundary() -> None:
    prompt = build_financial_quality_analysis_prompt(
        make_profile(), make_financial_risk_context()
    )

    assert "Use only the supplied context" in prompt
    assert "do not invent facts" in prompt
    assert "perform new calculations" in prompt
    assert "apply thresholds" in prompt
    assert "make forecasts" in prompt
    assert "peer comparisons" in prompt
    assert "exactly the union" in prompt
    assert "structured evidence records" in prompt
    assert "unavailable or\ninsufficient" in prompt
    assert "either array may be empty" in prompt


def test_prompt_serializes_metrics_and_financial_sources_only() -> None:
    prompt = build_financial_quality_analysis_prompt(
        make_profile(), make_financial_risk_context()
    )
    context = json.loads(prompt.split("Financial-quality context:\n", maxsplit=1)[1])

    assert context["financial_risk_context"] == {
        "metrics": [
            {
                "metric": "operating_margin",
                "source_ids": ["TEST-income-2025"],
                "unit": "percentage",
                "value": "0.25",
            }
        ],
        "sources": [
            {
                "captured_on": "2026-08-19",
                "period_end": None,
                "provider": "test_provider",
                "retrieved_at": None,
                "source_id": "TEST-income-2025",
                "source_type": "income_statement",
                "url": "https://example.com/income-statement",
            }
        ],
    }
    assert "TEST-overview" not in prompt
    assert "Test Company sells enterprise software subscriptions." not in prompt


def test_financial_quality_analysis_accepts_known_evidence_sources() -> None:
    source = make_source()
    analysis = FinancialQualityAnalysis(
        overall_assessment=FinancialQualityEvidence(
            claim="The supplied margin indicates profitable operations.",
            metric_names=("operating_margin",),
            source_ids=(source.source_id,),
        ),
        strengths=(
            FinancialQualityEvidence(
                claim="The supplied operating margin is positive.",
                metric_names=("operating_margin",),
                source_ids=(source.source_id,),
            ),
        ),
        concerns=(
            FinancialQualityEvidence(
                claim="The context contains only one metric.",
                metric_names=("operating_margin",),
                source_ids=(source.source_id,),
            ),
        ),
        sources=(source,),
    )

    assert analysis.overall_assessment.source_ids == ("TEST-income-2025",)


def test_financial_quality_analysis_allows_empty_strengths_and_concerns() -> None:
    source = make_source()

    analysis = FinancialQualityAnalysis(
        overall_assessment=FinancialQualityEvidence(
            claim="The supplied metric is available for interpretation.",
            metric_names=("operating_margin",),
            source_ids=(source.source_id,),
        ),
        sources=(source,),
    )

    assert analysis.strengths == ()
    assert analysis.concerns == ()


def test_financial_quality_analysis_rejects_conflicting_source_references() -> None:
    source = make_source()
    conflicting_source = source.model_copy(
        update={"url": HttpUrl("https://example.com/conflicting-statement")}
    )

    with pytest.raises(ValueError, match="conflicting source references"):
        FinancialQualityAnalysis(
            overall_assessment=FinancialQualityEvidence(
                claim="The supplied metric is available for interpretation.",
                metric_names=("operating_margin",),
                source_ids=(source.source_id,),
            ),
            sources=(source, conflicting_source),
        )


def test_validate_financial_quality_provenance_requires_exact_multi_metric_union(
) -> None:
    income_source = make_source()
    cash_flow_source = SourceReference(
        provider="test_provider",
        source_type="cash_flow_statement",
        source_id="TEST-cash-flow-2025",
        url=HttpUrl("https://example.com/cash-flow-statement"),
        captured_on=date(2026, 8, 19),
    )
    context = FinancialRiskContext(
        metrics=(
            FinancialRiskMetric(
                metric="operating_margin",
                value=Decimal("0.25"),
                unit="percentage",
                source_ids=(income_source.source_id,),
            ),
            FinancialRiskMetric(
                metric="fcf_margin",
                value=Decimal("0.20"),
                unit="percentage",
                source_ids=(cash_flow_source.source_id,),
            ),
        ),
        sources=(income_source, cash_flow_source),
    )
    analysis = FinancialQualityAnalysis(
        overall_assessment=FinancialQualityEvidence(
            claim="The supplied profitability metrics support an assessment.",
            metric_names=("operating_margin", "fcf_margin"),
            source_ids=(income_source.source_id, cash_flow_source.source_id),
        ),
        sources=(income_source, cash_flow_source),
    )

    validate_financial_quality_provenance(analysis, context)

    invalid_analysis = analysis.model_copy(
        update={
            "overall_assessment": analysis.overall_assessment.model_copy(
                update={"source_ids": (income_source.source_id,)}
            )
        }
    )
    with pytest.raises(ValueError, match="do not match"):
        validate_financial_quality_provenance(invalid_analysis, context)

    missing_source_analysis = analysis.model_copy(
        update={"sources": (income_source,)}
    )
    with pytest.raises(ValueError, match="sources do not match"):
        validate_financial_quality_provenance(missing_source_analysis, context)

    extra_source = SourceReference(
        provider="test_provider",
        source_type="balance_sheet",
        source_id="TEST-balance-sheet-2025",
        url=HttpUrl("https://example.com/balance-sheet"),
        captured_on=date(2026, 8, 19),
    )
    extra_source_analysis = analysis.model_copy(
        update={"sources": (*analysis.sources, extra_source)}
    )
    with pytest.raises(ValueError, match="sources do not match"):
        validate_financial_quality_provenance(extra_source_analysis, context)


def test_validate_financial_quality_provenance_rejects_altered_context_source() -> None:
    source = make_source()
    context = make_financial_risk_context()
    analysis = FinancialQualityAnalysis(
        overall_assessment=FinancialQualityEvidence(
            claim="The supplied metric supports an assessment.",
            metric_names=("operating_margin",),
            source_ids=(source.source_id,),
        ),
        sources=(
            source.model_copy(
                update={"url": HttpUrl("https://example.com/altered-statement")}
            ),
        ),
    )

    with pytest.raises(ValueError, match="source references do not match"):
        validate_financial_quality_provenance(analysis, context)


def test_financial_quality_analysis_rejects_unknown_evidence_sources() -> None:
    with pytest.raises(ValueError, match="unknown source IDs: missing-source"):
        FinancialQualityAnalysis(
            overall_assessment=FinancialQualityEvidence(
                claim="The supplied metrics are limited.",
                metric_names=("operating_margin",),
                source_ids=("missing-source",),
            ),
            strengths=(
                FinancialQualityEvidence(
                    claim="The metric is available.",
                    metric_names=("operating_margin",),
                    source_ids=(make_source().source_id,),
                ),
            ),
            concerns=(
                FinancialQualityEvidence(
                    claim="The context contains only one metric.",
                    metric_names=("operating_margin",),
                    source_ids=(make_source().source_id,),
                ),
            ),
            sources=(make_source(),),
        )


def test_financial_quality_analysis_requires_structured_findings() -> None:
    source = make_source()

    with pytest.raises(ValueError):
        FinancialQualityAnalysis(
            overall_assessment="An unsupported string assessment",
            strengths=(),
            concerns=(),
            sources=(source,),
        )


@pytest.mark.parametrize(
    ("field_name", "duplicate_values", "message"),
    [
        ("metric_names", ("operating_margin", "operating_margin"), "metric_names"),
        ("source_ids", ("TEST-income-2025", "TEST-income-2025"), "source_ids"),
    ],
)
def test_financial_quality_evidence_rejects_duplicate_references(
    field_name: str,
    duplicate_values: tuple[str, str],
    message: str,
) -> None:
    source = make_source()
    values = {
        "claim": "The supplied metric is available.",
        "metric_names": ("operating_margin",),
        "source_ids": (source.source_id,),
    }
    values[field_name] = duplicate_values

    with pytest.raises(ValueError, match=message):
        FinancialQualityEvidence(**values)
