"""Tests for the ticker-to-disclosed-risk-analysis orchestration pipeline."""

from datetime import date, datetime, timezone

import pytest
from pydantic import HttpUrl

from equity_research_agent.data.providers.edgar import EdgarNormalizationError
from equity_research_agent.data.providers.edgar_provider import EdgarProviderError
from equity_research_agent.filings.disclosed_risk_pipeline import (
    DisclosedRiskPipelineResult,
    DisclosedRiskUnavailableReason,
    resolve_disclosed_risk_analysis,
)
from equity_research_agent.filings.risk_factors import (
    RiskFactorsSectionUnavailableReason,
)
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.disclosed_risk_analysis import (
    DisclosedRisk,
    DisclosedRiskAnalysis,
)
from equity_research_agent.models.filings import (
    FilingReference,
    FilingSection,
    RetrievedFiling,
)
from equity_research_agent.models.provenance import SourceReference

DOCUMENT_URL = HttpUrl(
    "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/test-10k.htm"
)

_SECTIONABLE_DOCUMENT_WITH_RISK_FACTORS = """
<html><body>
<div id="business"></div><p>Business discussion.</p>
<div id="risks"></div><p>Risk factors discussion.</p>
<table>
  <tr><th></th><th></th><th>Page</th></tr>
  <tr>
    <td><a href="#business">Item 1.</a></td>
    <td><a href="#business">Business</a></td>
    <td><a href="#business">1</a></td>
  </tr>
  <tr>
    <td><a href="#risks">Item 1A.</a></td>
    <td><a href="#risks">Risk Factors</a></td>
    <td><a href="#risks">2</a></td>
  </tr>
</table>
</body></html>
"""

_SECTIONABLE_DOCUMENT_WITHOUT_RISK_FACTORS = """
<html><body>
<div id="business"></div><p>Business discussion.</p>
<table>
  <tr><th></th><th></th><th>Page</th></tr>
  <tr>
    <td><a href="#business">Item 1.</a></td>
    <td><a href="#business">Business</a></td>
    <td><a href="#business">1</a></td>
  </tr>
</table>
</body></html>
"""

_UNSECTIONABLE_DOCUMENT = "<html><body><p>No internal links here.</p></body></html>"


def make_source() -> SourceReference:
    """Create provenance for a filing's submissions-index metadata."""

    return SourceReference(
        provider="sec_edgar",
        source_type="submissions_index",
        source_id="CIK0000000001-submissions",
        url=HttpUrl("https://data.sec.gov/submissions/CIK0000000001.json"),
        retrieved_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )


def make_profile(cik: str | None) -> CompanyProfile:
    """Create a company profile carrying an optional already-known CIK."""

    return CompanyProfile(
        security=SecurityIdentity(
            input_symbol="TEST",
            canonical_symbol="TEST",
            exchange="TEST",
            listing_currency="USD",
            cik=cik,
        ),
        name="Test Company",
        description="A test company.",
        sources=(
            SourceReference(
                provider="test_provider",
                source_type="company_overview",
                source_id="TEST-overview",
                url=HttpUrl("https://example.com/company-overview"),
                captured_on=date(2026, 8, 21),
            ),
        ),
    )


def make_filing() -> FilingReference:
    """Create a minimal 10-K filing reference for pipeline tests."""

    return FilingReference(
        cik="1",
        form_type="10-K",
        accession_number="0000000000-26-000001",
        period_end=date(2025, 12, 31),
        filed_on=date(2026, 2, 25),
        document_url=DOCUMENT_URL,
        sources=(make_source(),),
    )


def make_retrieved(filing: FilingReference, document: str) -> RetrievedFiling:
    """Create a retrieved filing wrapping the supplied synthetic HTML."""

    return RetrievedFiling(
        filing=filing,
        content_type="text/html",
        byte_size=len(document.encode()),
        untrusted_text=document,
        sources=(make_source(),),
    )


class FakeFilingProvider:
    """A configurable filing provider for exercising each pipeline branch."""

    def __init__(
        self,
        *,
        resolve_cik_result: str | Exception = "1",
        annual_report_result: FilingReference | Exception | None = None,
        document: str = _SECTIONABLE_DOCUMENT_WITH_RISK_FACTORS,
        document_error: Exception | None = None,
    ) -> None:
        self.resolve_cik_result = resolve_cik_result
        self.annual_report_result = annual_report_result or make_filing()
        self.document = document
        self.document_error = document_error
        self.resolve_cik_calls: list[str] = []
        self.get_latest_annual_report_calls: list[str] = []
        self.get_document_calls: list[FilingReference] = []

    def resolve_cik(self, ticker: str) -> str:
        self.resolve_cik_calls.append(ticker)
        if isinstance(self.resolve_cik_result, Exception):
            raise self.resolve_cik_result
        return self.resolve_cik_result

    def get_latest_annual_report(self, cik: str) -> FilingReference:
        self.get_latest_annual_report_calls.append(cik)
        if isinstance(self.annual_report_result, Exception):
            raise self.annual_report_result
        return self.annual_report_result

    def get_document(self, filing: FilingReference) -> RetrievedFiling:
        self.get_document_calls.append(filing)
        if self.document_error is not None:
            raise self.document_error
        return make_retrieved(filing, self.document)


class FakeDisclosedRiskAnalyst:
    """Record what the pipeline supplies and return a fixed analysis."""

    def __init__(self) -> None:
        self.calls: list[tuple[FilingReference, FilingSection]] = []

    def analyze(
        self, filing: FilingReference, section: FilingSection
    ) -> DisclosedRiskAnalysis:
        self.calls.append((filing, section))
        source = SourceReference(
            provider="sec_edgar",
            source_type="filing_section",
            source_id="0000000000-26-000001:risks",
            url=HttpUrl(f"{DOCUMENT_URL}#risks"),
            captured_on=date(2026, 2, 25),
        )
        return DisclosedRiskAnalysis(
            disclosed_risks=(
                DisclosedRisk(
                    risk="A disclosed risk.", source_ids=(source.source_id,)
                ),
            ),
            sources=(source,),
        )


def test_uses_profile_cik_without_resolving_when_present() -> None:
    provider = FakeFilingProvider()
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik="1"), provider, analyst
    )

    assert provider.resolve_cik_calls == []
    assert provider.get_latest_annual_report_calls == ["1"]
    assert result.analysis is not None
    assert result.analysis.disclosed_risks[0].risk == "A disclosed risk."


def test_falls_back_to_resolve_cik_when_profile_cik_is_missing() -> None:
    provider = FakeFilingProvider(resolve_cik_result="42")
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik=None), provider, analyst
    )

    assert provider.resolve_cik_calls == ["TEST"]
    assert provider.get_latest_annual_report_calls == ["42"]
    assert result.analysis is not None


def test_cik_unresolved_when_resolve_cik_finds_no_match() -> None:
    provider = FakeFilingProvider(
        resolve_cik_result=EdgarNormalizationError("no CIK found for ticker 'TEST'")
    )
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik=None), provider, analyst
    )

    assert result == DisclosedRiskPipelineResult(
        unavailable_reason=DisclosedRiskUnavailableReason.CIK_UNRESOLVED
    )
    assert provider.get_latest_annual_report_calls == []


def test_resolve_cik_transport_failure_propagates() -> None:
    provider = FakeFilingProvider(
        resolve_cik_result=EdgarProviderError("transport failure")
    )
    analyst = FakeDisclosedRiskAnalyst()

    with pytest.raises(EdgarProviderError):
        resolve_disclosed_risk_analysis(
            "TEST", make_profile(cik=None), provider, analyst
        )


def test_annual_report_not_found_when_normalization_fails() -> None:
    provider = FakeFilingProvider(
        annual_report_result=EdgarNormalizationError(
            "recent submissions contain no 10-K or 20-F annual report"
        )
    )
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik="1"), provider, analyst
    )

    assert result == DisclosedRiskPipelineResult(
        unavailable_reason=DisclosedRiskUnavailableReason.ANNUAL_REPORT_NOT_FOUND
    )
    assert provider.get_document_calls == []


def test_annual_report_transport_failure_propagates() -> None:
    provider = FakeFilingProvider(
        annual_report_result=EdgarProviderError("transport failure")
    )
    analyst = FakeDisclosedRiskAnalyst()

    with pytest.raises(EdgarProviderError):
        resolve_disclosed_risk_analysis(
            "TEST", make_profile(cik="1"), provider, analyst
        )


def test_document_retrieval_failure_propagates() -> None:
    provider = FakeFilingProvider(document_error=EdgarProviderError("bad document"))
    analyst = FakeDisclosedRiskAnalyst()

    with pytest.raises(EdgarProviderError):
        resolve_disclosed_risk_analysis(
            "TEST", make_profile(cik="1"), provider, analyst
        )


def test_filing_not_sectionable_when_document_has_no_index() -> None:
    provider = FakeFilingProvider(document=_UNSECTIONABLE_DOCUMENT)
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik="1"), provider, analyst
    )

    assert result == DisclosedRiskPipelineResult(
        unavailable_reason=DisclosedRiskUnavailableReason.FILING_NOT_SECTIONABLE
    )


def test_risk_factors_section_unavailable_surfaces_the_specific_reason() -> None:
    provider = FakeFilingProvider(document=_SECTIONABLE_DOCUMENT_WITHOUT_RISK_FACTORS)
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik="1"), provider, analyst
    )

    assert result == DisclosedRiskPipelineResult(
        unavailable_reason=(
            DisclosedRiskUnavailableReason.RISK_FACTORS_SECTION_UNAVAILABLE
        ),
        risk_factors_reason=(
            RiskFactorsSectionUnavailableReason.EXPECTED_ITEM_NOT_FOUND
        ),
    )
    assert analyst.calls == []


def test_invokes_the_analyst_with_the_selected_section_on_success() -> None:
    provider = FakeFilingProvider()
    analyst = FakeDisclosedRiskAnalyst()

    result = resolve_disclosed_risk_analysis(
        "TEST", make_profile(cik="1"), provider, analyst
    )

    assert len(analyst.calls) == 1
    called_filing, called_section = analyst.calls[0]
    assert called_filing == provider.annual_report_result
    assert called_section.item_identifier == "1A"
    assert result.analysis is not None


def test_pipeline_result_requires_exactly_one_of_analysis_or_reason() -> None:
    with pytest.raises(ValueError, match="exactly one of analysis"):
        DisclosedRiskPipelineResult()


def test_pipeline_result_requires_risk_factors_reason_only_for_that_reason() -> None:
    with pytest.raises(ValueError, match="risk_factors_reason"):
        DisclosedRiskPipelineResult(
            unavailable_reason=DisclosedRiskUnavailableReason.CIK_UNRESOLVED,
            risk_factors_reason=(
                RiskFactorsSectionUnavailableReason.EXPECTED_ITEM_NOT_FOUND
            ),
        )
