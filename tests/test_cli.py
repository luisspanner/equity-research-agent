"""Tests for V0 command-line research orchestration."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from equity_research_agent import main, run_research
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
    synthesis = object()

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
        ) -> object:
            events.append(
                (
                    "synthesis",
                    received_profile,
                    received_business_analysis,
                    received_bear_analysis,
                    received_financial_quality_analysis,
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
        FakeBusinessAnalyst(),  # type: ignore[arg-type]
        FakeBearAnalyst(),  # type: ignore[arg-type]
        FakeFinancialQualityAnalyst(),  # type: ignore[arg-type]
        FakeSynthesizer(),  # type: ignore[arg-type]
    )

    assert report == "# Test report"
    assert events == [
        ("profile", "ASML"),
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
        ),
        (
            "report",
            profile,
            metrics,
            business_analysis,
            bear_analysis,
            financial_quality_analysis,
            synthesis,
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

    with pytest.raises(ValueError, match="unknown metric names"):
        run_research(
            "TEST",
            FakeProvider(),  # type: ignore[arg-type]
            FakeBusinessAnalyst(),  # type: ignore[arg-type]
            FakeBearAnalyst(),  # type: ignore[arg-type]
            FakeFinancialQualityAnalyst(),  # type: ignore[arg-type]
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

    with pytest.raises(ValueError, match="source references do not match"):
        run_research(
            "TEST",
            FakeProvider(),  # type: ignore[arg-type]
            FakeBusinessAnalyst(),  # type: ignore[arg-type]
            FakeBearAnalyst(),  # type: ignore[arg-type]
            FakeFinancialQualityAnalyst(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )


def test_main_builds_components_and_prints_the_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    provider = object()
    business_analyst = object()
    bear_analyst = object()
    financial_quality_analyst = object()
    synthesizer = object()

    def fake_alpha_vantage_provider(api_key: str) -> object:
        calls.append(("provider", api_key))
        return provider

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

    def fake_run_research(*received_inputs: object) -> str:
        calls.append(("run", *received_inputs))
        return "# Test report"

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-key")
    monkeypatch.setattr(
        "equity_research_agent.AlphaVantageProvider", fake_alpha_vantage_provider
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
        "equity_research_agent.GroqResearchSynthesizer", FakeSynthesizer
    )
    monkeypatch.setattr("equity_research_agent.run_research", fake_run_research)

    main(["ASML"])

    assert capsys.readouterr().out == "# Test report\n"
    assert calls == [
        ("provider", "alpha-key"),
        "business",
        "bear",
        "financial-quality",
        "synthesis",
        (
            "run",
            "ASML",
            provider,
            business_analyst,
            bear_analyst,
            financial_quality_analyst,
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
