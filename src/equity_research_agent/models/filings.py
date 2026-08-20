"""Domain models for discovered primary-source company filings."""

from datetime import date
from typing import Annotated, Literal, TypeAlias, get_args

from pydantic import Field, HttpUrl, StringConstraints, model_validator

from equity_research_agent.models.common import Cik, DomainModel, NonEmptyString
from equity_research_agent.models.provenance import SourceReference

AnnualReportFormType: TypeAlias = Literal["10-K", "20-F"]

ANNUAL_REPORT_FORM_TYPES: tuple[AnnualReportFormType, ...] = get_args(
    AnnualReportFormType
)

AccessionNumber: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^\d{10}-\d{2}-\d{6}$"),
]

DocumentText: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
"""Document text kept exactly as retrieved, without whitespace normalization."""


class FilingReference(DomainModel):
    """Metadata for one discovered annual report, without its document text.

    The filing document itself is intentionally not retrieved here. ``sources``
    records where this metadata came from; ``document_url`` only identifies the
    document a later slice may fetch.
    """

    cik: Cik
    form_type: AnnualReportFormType
    accession_number: AccessionNumber
    period_end: date
    filed_on: date
    document_url: HttpUrl
    sources: tuple[SourceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_filing_order(self) -> "FilingReference":
        """Reject annual reports filed before the period they cover has ended."""

        if self.filed_on < self.period_end:
            raise ValueError("filed_on must not precede period_end")

        return self


class RetrievedFiling(DomainModel):
    """One filing's primary document, retrieved but not yet interpreted.

    ``untrusted_text`` is third-party prose written by the filer. It is evidence
    to be quoted and cited, never instructions to be followed, and it must not
    reach a model prompt outside an explicit evidence boundary.

    ``byte_size`` records the retrieved payload, which differs from the decoded
    text length whenever the document contains non-ASCII characters.
    """

    filing: FilingReference
    content_type: NonEmptyString
    byte_size: int = Field(gt=0)
    untrusted_text: DocumentText
    sources: tuple[SourceReference, ...] = Field(min_length=1)


class FilingText(DomainModel):
    """Readable text extracted from one retrieved filing document.

    Extraction changes only the representation. The text remains untrusted
    third-party prose and keeps the provenance of the document it came from, so
    later sectioning and citation stay traceable to a filing.
    """

    filing: FilingReference
    untrusted_text: DocumentText
    sources: tuple[SourceReference, ...] = Field(min_length=1)


class FilingSection(DomainModel):
    """One labelled span of a filing, bounded by locations its own sectioning
    index cites.

    More than one label can point to the same anchor, so a filing's sections
    are not guaranteed to be disjoint: two sections can carry identical text.
    Where a filing's own index exposes a recognized form structure, the
    optional metadata records that structure separately from the display label.
    """

    label: NonEmptyString
    anchor_id: NonEmptyString
    text: DocumentText
    item_identifier: NonEmptyString | None = None
    form_caption: NonEmptyString | None = None
    location_label: NonEmptyString | None = None


class SectionedFiling(DomainModel):
    """One filing divided into labelled, possibly overlapping sections.

    Sectioning is a pure transformation of an already-retrieved document: it
    adds no source of its own, matching the precedent set by ``FilingText``.
    """

    filing: FilingReference
    sections: tuple[FilingSection, ...] = Field(min_length=1)
    sources: tuple[SourceReference, ...] = Field(min_length=1)
