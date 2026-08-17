"""Shared validation rules for domain models."""

from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, StringConstraints


class DomainModel(BaseModel):
    """Immutable, strict base model for normalized project data."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


NonEmptyString: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

CurrencyCode: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"),
]

Cik: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=10, pattern=r"^\d+$"),
]
