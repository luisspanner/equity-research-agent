"""Tests for the shared company and provenance domain models."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from equity_research_agent.models.common import DomainModel
from equity_research_agent.models.company import CompanyProfile, SecurityIdentity
from equity_research_agent.models.provenance import SourceReference


def make_source(**overrides: object) -> SourceReference:
    """Create one valid Alpha Vantage source with optional field overrides."""

    values: dict[str, object] = {
        "provider": "alpha_vantage",
        "source_type": "overview",
        "source_id": "ASML-overview",
        "url": "https://www.alphavantage.co/query?function=OVERVIEW&symbol=ASML",
        "captured_on": date(2026, 8, 17),
    }
    values.update(overrides)
    return SourceReference(**values)


def make_security(**overrides: object) -> SecurityIdentity:
    """Create the ASML Nasdaq ADR identity captured during the provider spike."""

    values: dict[str, object] = {
        "input_symbol": "ASML",
        "canonical_symbol": "ASML",
        "exchange": "NASDAQ",
        "listing_currency": "USD",
        "reporting_currency": "EUR",
        "cik": "937966",
    }
    values.update(overrides)
    return SecurityIdentity(**values)


def test_source_reference_accepts_capture_date_without_inventing_timestamp() -> None:
    source = make_source()

    assert source.captured_on == date(2026, 8, 17)
    assert source.retrieved_at is None


def test_source_reference_accepts_exact_timezone_aware_retrieval_timestamp() -> None:
    retrieved_at = datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)

    source = make_source(captured_on=None, retrieved_at=retrieved_at)

    assert source.retrieved_at == retrieved_at
    assert source.captured_on is None


@pytest.mark.parametrize(
    ("captured_on", "retrieved_at"),
    [
        (None, None),
        (date(2026, 8, 17), datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)),
        (None, datetime(2026, 8, 17, 9, 30)),
    ],
)
def test_source_reference_rejects_ambiguous_or_imprecise_retrieval_time(
    captured_on: date | None, retrieved_at: datetime | None
) -> None:
    with pytest.raises(ValidationError):
        make_source(captured_on=captured_on, retrieved_at=retrieved_at)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_id": "   "},
        {"url": "not-a-url"},
        {"url": "https://example.com/query?ApiKey=secret"},
        {"url": "https://example.com/query?api_key=secret"},
        {"url": "https://example.com/query?TOKEN=secret"},
        {"unexpected_field": "not allowed"},
    ],
)
def test_source_reference_rejects_invalid_source_data(
    overrides: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        make_source(**overrides)


def test_security_identity_preserves_asml_adr_currency_distinction() -> None:
    security = make_security()

    assert security.input_symbol == "ASML"
    assert security.canonical_symbol == "ASML"
    assert security.listing_currency == "USD"
    assert security.reporting_currency == "EUR"


@pytest.mark.parametrize(
    "overrides",
    [
        {"listing_currency": "US"},
        {"reporting_currency": "eur"},
        {"cik": ""},
        {"cik": "not-a-cik"},
    ],
)
def test_security_identity_rejects_invalid_identifiers_and_currency_codes(
    overrides: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        make_security(**overrides)


def test_company_profile_keeps_nested_source_provenance() -> None:
    source = make_source()
    profile = CompanyProfile(
        security=make_security(),
        name="ASML Holding N.V. ADR",
        description="Supplier of semiconductor manufacturing equipment.",
        country="Netherlands",
        sector="Technology",
        industry="Semiconductor Equipment & Materials",
        sources=(source,),
    )

    assert profile.sources == (source,)
    assert profile.sources[0].provider == "alpha_vantage"


def test_domain_models_are_frozen_and_reject_unknown_fields() -> None:
    security = make_security()

    with pytest.raises(ValidationError):
        security.exchange = "NYSE"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        make_security(unknown_field="not allowed")


def test_model_json_serialization_preserves_domain_values() -> None:
    source = make_source(period_end=date(2025, 12, 31))
    profile = CompanyProfile(
        security=make_security(),
        name="ASML Holding N.V. ADR",
        description="Supplier of semiconductor manufacturing equipment.",
        sources=(source,),
    )

    serialized = json.loads(profile.model_dump_json())

    assert serialized["security"]["listing_currency"] == "USD"
    assert serialized["security"]["reporting_currency"] == "EUR"
    assert serialized["sources"][0]["captured_on"] == "2026-08-17"
    assert serialized["sources"][0]["retrieved_at"] is None
    assert serialized["sources"][0]["period_end"] == "2025-12-31"
    assert serialized["sources"][0]["url"].startswith("https://www.alphavantage.co/")


class DecimalValue(DomainModel):
    """Small test model verifying the shared numeric configuration."""

    value: Decimal


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_domain_model_rejects_non_finite_decimal_values(value: Decimal) -> None:
    with pytest.raises(ValidationError):
        DecimalValue(value=value)
