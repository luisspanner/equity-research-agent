"""Tests for V0 command-line research orchestration."""

import pytest

from equity_research_agent import main, run_research


def test_run_research_orchestrates_the_v0_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    profile = object()
    financials = object()
    market_snapshot = object()
    metrics = object()
    business_analysis = object()
    bear_analysis = object()
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
            self, received_profile: object, received_business_analysis: object
        ) -> object:
            events.append(("bear", received_profile, received_business_analysis))
            return bear_analysis

    class FakeSynthesizer:
        def analyze(
            self,
            received_profile: object,
            received_business_analysis: object,
            received_bear_analysis: object,
        ) -> object:
            events.append(
                (
                    "synthesis",
                    received_profile,
                    received_business_analysis,
                    received_bear_analysis,
                )
            )
            return synthesis

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
    monkeypatch.setattr("equity_research_agent.render_research_report", fake_render)

    report = run_research(
        "ASML",
        FakeProvider(),  # type: ignore[arg-type]
        FakeBusinessAnalyst(),  # type: ignore[arg-type]
        FakeBearAnalyst(),  # type: ignore[arg-type]
        FakeSynthesizer(),  # type: ignore[arg-type]
    )

    assert report == "# Test report"
    assert events == [
        ("profile", "ASML"),
        ("financials", "ASML"),
        ("market", "ASML"),
        ("metrics", financials, market_snapshot),
        ("business", profile),
        ("bear", profile, business_analysis),
        ("synthesis", profile, business_analysis, bear_analysis),
        ("report", profile, metrics, business_analysis, bear_analysis, synthesis),
    ]


def test_main_builds_components_and_prints_the_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    provider = object()
    business_analyst = object()
    bear_analyst = object()
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
        "equity_research_agent.GroqResearchSynthesizer", FakeSynthesizer
    )
    monkeypatch.setattr("equity_research_agent.run_research", fake_run_research)

    main(["ASML"])

    assert capsys.readouterr().out == "# Test report\n"
    assert calls == [
        ("provider", "alpha-key"),
        "business",
        "bear",
        "synthesis",
        ("run", "ASML", provider, business_analyst, bear_analyst, synthesizer),
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
