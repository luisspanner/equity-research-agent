"""Pure Markdown rendering of a completed V0 research analysis."""

from decimal import Decimal

from equity_research_agent.filings.disclosed_risk_pipeline import (
    DisclosedRiskPipelineResult,
    DisclosedRiskUnavailableReason,
)
from equity_research_agent.models.bear_analysis import BearAnalysis
from equity_research_agent.models.business_analysis import BusinessAnalysis
from equity_research_agent.models.company import CompanyProfile
from equity_research_agent.models.financial_quality import (
    FinancialQualityAnalysis,
    FinancialQualityEvidence,
)
from equity_research_agent.models.metrics import FinancialMetrics
from equity_research_agent.models.provenance import SourceReference
from equity_research_agent.models.synthesis import ResearchSynthesis


def render_research_report(
    profile: CompanyProfile,
    metrics: FinancialMetrics,
    business_analysis: BusinessAnalysis,
    bear_analysis: BearAnalysis,
    financial_quality_analysis: FinancialQualityAnalysis,
    synthesis: ResearchSynthesis,
    disclosed_risk_result: DisclosedRiskPipelineResult,
) -> str:
    """Render sourced analysis into deterministic, human-readable Markdown.

    ``synthesis.sources`` already includes the disclosed-risk analysis's
    sources when available, since the Research Synthesizer merges them
    deterministically; this function does not merge them again.
    """

    lines = [
        f"# {profile.name} ({profile.security.canonical_symbol})",
        "",
        "*Research summary only; not an investment recommendation.*",
        "",
        "## Company",
        "",
        f"- Exchange: {profile.security.exchange}",
        f"- Listing currency: {profile.security.listing_currency}",
        _optional_detail("Country", profile.country),
        _optional_detail("Sector", profile.sector),
        _optional_detail("Industry", profile.industry),
        "",
        profile.description,
        "",
        "## Deterministic Financial Metrics",
        "",
        f"- Latest reporting period: {metrics.latest_period_end.isoformat()}",
        f"- Reporting currency: {metrics.reporting_currency}",
        "",
        "### Growth",
        "",
        _metric_line("Revenue CAGR", metrics.revenue_cagr, "percentage", metrics),
        _metric_line("EPS CAGR", metrics.eps_cagr, "percentage", metrics),
        _metric_line(
            "Share count CAGR", metrics.share_count_cagr, "percentage", metrics
        ),
        "",
        "### Profitability",
        "",
        _metric_line("Free cash flow", metrics.fcf, "currency", metrics),
        _metric_line("FCF margin", metrics.fcf_margin, "percentage", metrics),
        _metric_line("Gross margin", metrics.gross_margin, "percentage", metrics),
        _metric_line(
            "Operating margin", metrics.operating_margin, "percentage", metrics
        ),
        _metric_line("EBITDA", metrics.ebitda, "currency", metrics),
        "",
        "### Leverage and Capital Efficiency",
        "",
        _metric_line("Net debt", metrics.net_debt, "currency", metrics),
        _metric_line(
            "Net debt / EBITDA", metrics.net_debt_to_ebitda, "multiple", metrics
        ),
        _metric_line("Return on equity", metrics.roe, "percentage", metrics),
        _metric_line("ROIC", metrics.roic, "percentage", metrics),
        "",
        "### Market Metrics",
        "",
        _metric_line("P/E", metrics.pe_ratio, "multiple", metrics, "pe_ratio"),
        _metric_line(
            "FCF yield", metrics.fcf_yield, "percentage", metrics, "fcf_yield"
        ),
        _metric_line(
            "EV / EBITDA", metrics.ev_to_ebitda, "multiple", metrics, "ev_to_ebitda"
        ),
        "",
        "## Financial Quality (LLM Interpretation)",
        "",
        "### Overall Assessment",
        "",
        _evidence_line(
            financial_quality_analysis.overall_assessment.claim,
            financial_quality_analysis.overall_assessment.source_ids,
        ),
        "",
        *_financial_quality_findings(
            "Strengths", financial_quality_analysis.strengths
        ),
        *_financial_quality_findings(
            "Concerns", financial_quality_analysis.concerns
        ),
        *_analysis_limitations(financial_quality_analysis.limitations),
        "",
        "## Business Analysis (LLM Interpretation)",
        "",
        f"### Business Model\n\n{business_analysis.business_model}",
        "",
        "### Primary Offerings",
        "",
        *_bullets(business_analysis.primary_offerings),
        "",
        "### Customers and End Markets\n\n"
        f"{business_analysis.customers_and_end_markets}",
        "",
        f"### Revenue Model\n\n{business_analysis.revenue_model}",
        "",
        f"### Competitive Positioning\n\n{business_analysis.competitive_positioning}",
        "",
        "### Evidence",
        "",
        *[
            _evidence_line(item.claim, item.source_ids)
            for item in business_analysis.evidence
        ],
        *_analysis_limitations(business_analysis.limitations),
        "",
        "## Bear Case (LLM Interpretation)",
        "",
        "### Risks",
        "",
        *[
            _risk_line(risk.risk, risk.downside_mechanism, risk.source_ids)
            for risk in bear_analysis.risks
        ],
        "",
        "### Thesis Killers",
        "",
        *_bullets(bear_analysis.thesis_killers),
        *_analysis_limitations(bear_analysis.limitations),
        "",
        *_disclosed_risk_section(disclosed_risk_result),
        "## Research Synthesis (LLM Interpretation)",
        "",
        f"### Investment Thesis\n\n{synthesis.investment_thesis}",
        "",
        "### Supporting Points",
        "",
        *_bullets(synthesis.supporting_points),
        "",
        "### Risk Summary",
        "",
        *_bullets(synthesis.risk_summary),
        "",
        "### Open Research Questions",
        "",
        *_bullets(synthesis.open_research_questions),
        "",
        "### Evidence",
        "",
        *[_evidence_line(item.claim, item.source_ids) for item in synthesis.evidence],
        *_analysis_limitations(synthesis.limitations),
        "",
        "## Sources",
        "",
        *[_source_line(source) for source in synthesis.sources],
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def _optional_detail(label: str, value: str | None) -> str | None:
    """Render optional company metadata only when it is available."""

    if value is None:
        return None
    return f"- {label}: {value}"


def _metric_line(
    label: str,
    value: Decimal | None,
    format_kind: str,
    metrics: FinancialMetrics,
    metric_name: str | None = None,
) -> str:
    """Render one metric, preserving missing values and explicit withholding reasons."""

    if value is None:
        reason = _unavailability_reason(metrics, metric_name)
        suffix = f" — {reason}" if reason is not None else ""
        return f"- {label}: Not available{suffix}"
    formatted_value = _format_metric(value, format_kind, metrics.reporting_currency)
    return f"- {label}: {formatted_value}"


def _unavailability_reason(
    metrics: FinancialMetrics, metric_name: str | None
) -> str | None:
    """Return the explicit reason a market metric was deliberately withheld."""

    if metric_name is None:
        return None
    for item in metrics.market_metric_unavailabilities:
        if item.metric == metric_name:
            return item.reason
    return None


def _format_metric(value: Decimal, format_kind: str, currency: str) -> str:
    """Format an already-calculated metric without changing its financial meaning."""

    if format_kind == "currency":
        return f"{currency} {_format_number(value)}"
    if format_kind == "percentage":
        return f"{value * Decimal('100'):.2f}%"
    if format_kind == "multiple":
        return f"{value:.2f}x"
    raise ValueError(f"unknown metric format kind: {format_kind}")


def _format_number(value: Decimal) -> str:
    """Display Decimal values with grouping while preserving their supplied scale."""

    return format(value, ",f")


def _evidence_line(claim: str, source_ids: tuple[str, ...]) -> str:
    """Render an evidence claim beside the source IDs that support it."""

    citations = ", ".join(f"[{source_id}]" for source_id in source_ids)
    return f"- {claim} {citations}"


def _financial_quality_findings(
    heading: str, findings: tuple[FinancialQualityEvidence, ...]
) -> list[str]:
    """Render an optional financial-quality finding group."""

    if not findings:
        return []
    return [
        f"### {heading}",
        "",
        *[_evidence_line(item.claim, item.source_ids) for item in findings],
        "",
    ]


def _risk_line(risk: str, mechanism: str, source_ids: tuple[str, ...]) -> str:
    """Render a bear risk, causal mechanism, and source citations on one line."""

    citations = ", ".join(f"[{source_id}]" for source_id in source_ids)
    return f"- **{risk}** {mechanism} {citations}"


def _disclosed_risk_section(result: DisclosedRiskPipelineResult) -> list[str]:
    """Render the filer's own disclosed risks, or why they are unavailable."""

    heading = "## Disclosed Risks (Filing Interpretation)"
    if result.analysis is None:
        reason = _disclosed_risk_unavailable_reason_text(result)
        return [heading, "", f"- Not available — {reason}", ""]
    return [
        heading,
        "",
        "### Risks",
        "",
        *[
            _evidence_line(risk.risk, risk.source_ids)
            for risk in result.analysis.disclosed_risks
        ],
        *_analysis_limitations(result.analysis.limitations),
        "",
    ]


def _disclosed_risk_unavailable_reason_text(
    result: DisclosedRiskPipelineResult,
) -> str:
    """Return a readable reason for a missing disclosed-risk analysis."""

    assert result.unavailable_reason is not None
    if (
        result.unavailable_reason
        == DisclosedRiskUnavailableReason.RISK_FACTORS_SECTION_UNAVAILABLE
    ):
        assert result.risk_factors_reason is not None
        detail = result.risk_factors_reason.value.replace("_", " ")
        return f"risk factors section unavailable ({detail})"
    return result.unavailable_reason.value.replace("_", " ")


def _analysis_limitations(limitations: tuple[str, ...]) -> list[str]:
    """Render analysis limitations only when the LLM identified them."""

    if not limitations:
        return []
    return ["", "### Limitations", "", *_bullets(limitations)]


def _bullets(items: tuple[str, ...]) -> list[str]:
    """Render a sequence as Markdown bullet points."""

    return [f"- {item}" for item in items]


def _source_line(source: SourceReference) -> str:
    """Render credential-safe provenance for a source in the consolidated list."""

    if source.captured_on is not None:
        when = f"captured {source.captured_on.isoformat()}"
    else:
        assert source.retrieved_at is not None
        when = f"retrieved {source.retrieved_at.isoformat()}"
    return (
        f"- [{source.source_id}] {source.provider} / {source.source_type} — "
        f"{source.url} ({when})"
    )
