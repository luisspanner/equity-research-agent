"""Tests for V0 command-line research orchestration."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from equity_research_agent import main, run_research
from equity_research_agent.filings.disclosed_risk_pipeline import (
    DisclosedRiskPipelineResult,
)
from equity_research_agent.models.financial_quality import (
    FinancialQualityAnalysis,
    FinancialQualityEvidence,
)
from equity_research_agent.models.financial_risk import (
    FinancialRiskContext,
    FinancialRiskMetric,
)
from equity_research_agent.models.provenance import SourceReference


def test_run_research_orchestrates_the_v0_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    profile = object()
    financials = object()
    market_snapshot = object()
    metrics = object()
    financial_risk_context = object()
    business_analysis = object()
    bear_analysis = object()
    financial_quality_analysis = object()
    disclosed_risk_analysis = object()
    disclosed_risk_result = DisclosedRiskPipelineResult(
        analysis=disclosed_risk_analysis
    )
    synthesis = object()
    filing_provider = object()
    disclosed_risk_analyst = object()

    class FakeProvider:
        def get_company_profile(self, ticker: str) -> object:
            events.append(("profile", ticker))
            return profile

        def get_annual_financials(self, ticker: str) -> object:
            events.append(("financials", ticker))
            return financials

        def get_market_snapshot(self, ticker: str) -> object:
            events.append(("market", ticker))
            return market_snapshot

    class FakeBusinessAnalyst:
        def analyze(self, received_profile: object) -> object:
            events.append(("business", received_profile))
            return business_analysis

    class FakeBearAnalyst:
        def analyze(
            self,
            received_profile: object,
            received_business_analysis: object,
            received_financial_risk_context: object,
        ) -> object:
            events.append(
                (
                    "bear",
                    received_profile,
                    received_business_analysis,
                    received_financial_risk_context,
                )
            )
            return bear_analysis

    class FakeSynthesizer:
        def analyze(
            self,
            received_profile: object,
            received_business_analysis: object,
            received_bear_analysis: object,
            received_financial_quality_analysis: object,
            received_disclosed_risk_analysis: object,
        ) -> object:
            events.append(
                (
                    "synthesis",
                    received_profile,
                    received_business_analysis,
                    received_bear_analysis,
                    received_financial_quality_analysis,
                    received_disclosed_risk_analysis,
                )
            )
            return synthesis

    class FakeFinancialQualityAnalyst:
        def analyze(
            self,
            received_profile: object,
            received_financial_risk_context: object,
        ) -> object:
            events.append(
                ("financial-quality", received_profile, received_financial_risk_context)
            )
            return financial_quality_analysis

    def fake_assemble(
        received_financials: object, received_market_snapshot: object
    ) -> object:
        events.append(("metrics", received_financials, received_market_snapshot))
        return metrics

    def fake_render(*received_inputs: object) -> str:
        events.append(("report", *received_inputs))
        return "# Test report"

    def fake_resolve_disclosed_risk_analysis(
        received_ticker: str,
        received_profile: object,
        received_filing_provider: object,
        received_disclosed_risk_analyst: object,
    ) -> object:
        events.append(
            (
                "disclosed-risk",
                received_ticker,
                received_profile,
                received_filing_provider,
                received_disclosed_risk_analyst,
            )
        )
        return disclosed_risk_result

    monkeypatch.setattr(
        "equity_research_agent.resolve_disclosed_risk_analysis",
        fake_resolve_disclosed_risk_analysis,
    )
    monkeypatch.setattr(
        "equity_research_agent.assemble_financial_metrics", fake_assemble
    )

    def fake_build_context(
        received_metrics: object,
        received_financials: object,
        received_market_snapshot: object,
    ) -> object:
        events.append(
            (
                "financial-risk",
                received_metrics,
                received_financials,
                received_market_snapshot,
            )
        )
        return financial_risk_context

    monkeypatch.setattr(
        "equity_research_agent.build_financial_risk_context", fake_build_context
    )
    monkeypatch.setattr("equity_research_agent.render_research_report", fake_render)
    monkeypatch.setattr(
        "equity_research_agent.validate_financial_quality_provenance",
        lambda analysis, context: None,
    )

    report = run_research(
        "ASML",
        FakeProvider(),  # type: ignore[arg-type]
        filing_provider,  # type: ignore[arg-type]
        FakeBusinessAnalyst(),  # type: ignore[arg-type]
        FakeBearAnalyst(),  # type: ignore[arg-type]
        FakeFinancialQualityAnalyst(),  # type: ignore[arg-type]
        disclosed_risk_analyst,  # type: ignore[arg-type]
        FakeSynthesizer(),  # type: ignore[arg-type]
    )

    assert report == "# Test report"
    assert events == [
        ("profile", "ASML"),
        (
            "disclosed-risk",
            "ASML",
            profile,
            filing_provider,
            disclosed_risk_analyst,
        ),
        ("financials", "ASML"),
        ("market", "ASML"),
        ("metrics", financials, market_snapshot),
        ("financial-risk", metrics, financials, market_snapshot),
        ("business", profile),
        ("bear", profile, business_analysis, financial_risk_context),
        ("financial-quality", profile, financial_risk_context),
        (
            "synthesis",
            profile,
            business_analysis,
            bear_analysis,
            financial_quality_analysis,
            disclosed_risk_analysis,
        ),
        (
            "report",
            profile,
            metrics,
            business_analysis,
            bear_analysis,
            financial_quality_analysis,
            synthesis,
            disclosed_risk_result,
        ),
    ]


def test_run_research_rejects_invalid_financial_quality_protocol_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = SourceReference(
        provider="test_provider",
        source_type="income_statement",
        source_id="TEST-income-2025",
        url=HttpUrl("https://example.com/income-statement"),
        captured_on=date(2026, 8, 19),
    )
    context = FinancialRiskContext(
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
    invalid_analysis = FinancialQualityAnalysis(
        overall_assessment=FinancialQualityEvidence(
            claim="This claim refers to an unavailable metric.",
            metric_names=("unknown_metric",),
            source_ids=(source.source_id,),
        ),
        sources=(source,),
    )

    class FakeProvider:
        def get_company_profile(self, ticker: str) -> object:
            return object()

        def get_annual_financials(self, ticker: str) -> object:
            return object()

        def get_market_snapshot(self, ticker: str) -> object:
            return object()

    class FakeFinancialQualityAnalyst:
        def analyze(
            self, profile: object, risk_context: object
        ) -> FinancialQualityAnalysis:
            return invalid_analysis

    class FakeBusinessAnalyst:
        def analyze(self, profile: object) -> object:
            return object()

    class FakeBearAnalyst:
        def analyze(
            self, profile: object, business_analysis: object, risk_context: object
        ) -> object:
            return object()

    monkeypatch.setattr(
        "equity_research_agent.assemble_financial_metrics", lambda *args: object()
    )
    monkeypatch.setattr(
        "equity_research_agent.build_financial_risk_context", lambda *args: context
    )
    monkeypatch.setattr(
        "equity_research_agent.resolve_disclosed_risk_analysis", lambda *args: object()
    )

    with pytest.raises(ValueError, match="unknown metric names"):
        run_research(
            "TEST",
            FakeProvider(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            FakeBusinessAnalyst(),  # type: ignore[arg-type]
            FakeBearAnalyst(),  # type: ignore[arg-type]
            FakeFinancialQualityAnalyst(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )


def test_run_research_rejects_altered_financial_quality_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = SourceReference(
        provider="test_provider",
        source_type="income_statement",
        source_id="TEST-income-2025",
        url=HttpUrl("https://example.com/income-statement"),
        captured_on=date(2026, 8, 19),
    )
    context = FinancialRiskContext(
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
    altered_analysis = FinancialQualityAnalysis(
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

    class FakeProvider:
        def get_company_profile(self, ticker: str) -> object:
            return object()

        def get_annual_financials(self, ticker: str) -> object:
            return object()

        def get_market_snapshot(self, ticker: str) -> object:
            return object()

    class FakeBusinessAnalyst:
        def analyze(self, profile: object) -> object:
            return object()

    class FakeBearAnalyst:
        def analyze(
            self, profile: object, business_analysis: object, risk_context: object
        ) -> object:
            return object()

    class FakeFinancialQualityAnalyst:
        def analyze(
            self, profile: object, risk_context: object
        ) -> FinancialQualityAnalysis:
            return altered_analysis

    monkeypatch.setattr(
        "equity_research_agent.assemble_financial_metrics", lambda *args: object()
    )
    monkeypatch.setattr(
        "equity_research_agent.build_financial_risk_context", lambda *args: context
    )
    monkeypatch.setattr(
        "equity_research_agent.resolve_disclosed_risk_analysis", lambda *args: object()
    )

    with pytest.raises(ValueError, match="source references do not match"):
        run_research(
            "TEST",
            FakeProvider(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            FakeBusinessAnalyst(),  # type: ignore[arg-type]
            FakeBearAnalyst(),  # type: ignore[arg-type]
            FakeFinancialQualityAnalyst(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )


def test_main_builds_components_and_prints_the_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    provider = object()
    filing_provider = object()
    business_analyst = object()
    bear_analyst = object()
    financial_quality_analyst = object()
    disclosed_risk_analyst = object()
    synthesizer = object()

    def fake_alpha_vantage_provider(api_key: str) -> object:
        calls.append(("provider", api_key))
        return provider

    def fake_edgar_filing_provider(user_agent: str) -> object:
        calls.append(("filing-provider", user_agent))
        return filing_provider

    class FakeBusinessAnalyst:
        @classmethod
        def from_environment(cls) -> object:
            calls.append("business")
            return business_analyst

    class FakeBearAnalyst:
        @classmethod
        def from_environment(cls) -> object:
            calls.append("bear")
            return bear_analyst

    class FakeSynthesizer:
        @classmethod
        def from_environment(cls) -> object:
            calls.append("synthesis")
            return synthesizer

    class FakeFinancialQualityAnalyst:
        @classmethod
        def from_environment(cls) -> object:
            calls.append("financial-quality")
            return financial_quality_analyst

    class FakeDisclosedRiskAnalyst:
        @classmethod
        def from_environment(cls) -> object:
            calls.append("disclosed-risk")
            return disclosed_risk_analyst

    def fake_run_research(*received_inputs: object) -> str:
        calls.append(("run", *received_inputs))
        return "# Test report"

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-key")
    monkeypatch.setenv(
        "EDGAR_CONTACT_USER_AGENT", "Equity Research Agent test@example.test"
    )
    monkeypatch.setattr(
        "equity_research_agent.AlphaVantageProvider", fake_alpha_vantage_provider
    )
    monkeypatch.setattr(
        "equity_research_agent.EdgarFilingProvider", fake_edgar_filing_provider
    )
    monkeypatch.setattr(
        "equity_research_agent.GroqBusinessAnalyst", FakeBusinessAnalyst
    )
    monkeypatch.setattr("equity_research_agent.GroqBearAnalyst", FakeBearAnalyst)
    monkeypatch.setattr(
        "equity_research_agent.GroqFinancialQualityAnalyst",
        FakeFinancialQualityAnalyst,
    )
    monkeypatch.setattr(
        "equity_research_agent.GroqDisclosedRiskAnalyst", FakeDisclosedRiskAnalyst
    )
    monkeypatch.setattr(
        "equity_research_agent.GroqResearchSynthesizer", FakeSynthesizer
    )
    monkeypatch.setattr("equity_research_agent.run_research", fake_run_research)

    main(["ASML"])

    assert capsys.readouterr().out == "# Test report\n"
    assert calls == [
        ("provider", "alpha-key"),
        ("filing-provider", "Equity Research Agent test@example.test"),
        "business",
        "bear",
        "financial-quality",
        "disclosed-risk",
        "synthesis",
        (
            "run",
            "ASML",
            provider,
            filing_provider,
            business_analyst,
            bear_analyst,
            financial_quality_analyst,
            disclosed_risk_analyst,
            synthesizer,
        ),
    ]


def test_main_requires_alpha_vantage_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        main(["ASML"])

    assert "ALPHA_VANTAGE_API_KEY environment variable is not set" in (
        capsys.readouterr().err
    )


def test_main_requires_edgar_contact_user_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-key")
    monkeypatch.delenv("EDGAR_CONTACT_USER_AGENT", raising=False)

    with pytest.raises(SystemExit):
        main(["ASML"])

    assert "EDGAR_CONTACT_USER_AGENT environment variable is not set" in (
        capsys.readouterr().err
    )
