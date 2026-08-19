"""Pure normalization of the SEC EDGAR submissions-index payload contract."""

from collections.abc import Mapping, Sequence
from datetime import date

from pydantic import HttpUrl, ValidationError

from equity_research_agent.models.filings import (
    ANNUAL_REPORT_FORM_TYPES,
    AnnualReportFormType,
    FilingReference,
)
from equity_research_agent.models.provenance import SourceReference

ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"

_RECENT_FILING_FIELDS = (
    "accessionNumber",
    "form",
    "filingDate",
    "reportDate",
    "primaryDocument",
)


class EdgarNormalizationError(ValueError):
    """Raised when an EDGAR submissions payload cannot satisfy the filing contract."""


def normalize_latest_annual_report(
    submissions: Mapping[str, object], source: SourceReference
) -> FilingReference:
    """Return the most recently filed 10-K or 20-F described by ``submissions``.

    Amendments such as ``10-K/A`` are not annual reports for this contract and
    are excluded. Only the ``recent`` submissions block is read, so issuers with
    no annual report among their recent filings raise instead of silently
    returning an older or unrelated document.
    """

    cik = _required_cik(submissions)
    columns = _recent_filing_columns(submissions)

    latest_index: int | None = None
    latest_filing_date: date | None = None
    latest_form_type: AnnualReportFormType | None = None
    for index, form in enumerate(columns["form"]):
        form_type = _annual_report_form_type(form)
        if form_type is None:
            continue
        filing_date = _date_value(columns["filingDate"][index], "filingDate")
        if latest_filing_date is None or filing_date > latest_filing_date:
            latest_index = index
            latest_filing_date = filing_date
            latest_form_type = form_type

    if latest_index is None or latest_filing_date is None or latest_form_type is None:
        raise EdgarNormalizationError(
            "recent submissions contain no 10-K or 20-F annual report"
        )

    accession_number = columns["accessionNumber"][latest_index]
    primary_document = columns["primaryDocument"][latest_index].strip()
    if not primary_document:
        raise EdgarNormalizationError(
            "latest annual report has no primary document"
        )

    try:
        return FilingReference(
            cik=cik,
            form_type=latest_form_type,
            accession_number=accession_number,
            period_end=_date_value(columns["reportDate"][latest_index], "reportDate"),
            filed_on=latest_filing_date,
            document_url=HttpUrl(
                _document_url(cik, accession_number, primary_document)
            ),
            sources=(source,),
        )
    except ValidationError as error:
        raise EdgarNormalizationError(
            "latest annual report does not satisfy the filing contract"
        ) from error


def _annual_report_form_type(form: str) -> AnnualReportFormType | None:
    """Return the annual-report form type, excluding amendments and other forms."""

    for form_type in ANNUAL_REPORT_FORM_TYPES:
        if form == form_type:
            return form_type
    return None


def _document_url(cik: str, accession_number: str, primary_document: str) -> str:
    """Build the canonical archive URL for one filing's primary document."""

    return (
        f"{ARCHIVES_BASE_URL}/{int(cik)}/"
        f"{accession_number.replace('-', '')}/{primary_document}"
    )


def _required_cik(submissions: Mapping[str, object]) -> str:
    value = submissions.get("cik")
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str) or not value.strip().isdigit():
        raise EdgarNormalizationError("payload field cik must be a digit string")
    return value.strip().lstrip("0") or "0"


def _recent_filing_columns(
    submissions: Mapping[str, object],
) -> dict[str, Sequence[str]]:
    """Read the parallel ``filings.recent`` arrays required by this contract."""

    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        raise EdgarNormalizationError("payload field filings must be an object")
    recent = filings.get("recent")
    if not isinstance(recent, Mapping):
        raise EdgarNormalizationError("payload field filings.recent must be an object")

    columns: dict[str, Sequence[str]] = {}
    for field in _RECENT_FILING_FIELDS:
        values = recent.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise EdgarNormalizationError(
                f"payload field filings.recent.{field} must be a list of strings"
            )
        columns[field] = values

    lengths = {len(values) for values in columns.values()}
    if len(lengths) != 1:
        raise EdgarNormalizationError(
            "payload field filings.recent has misaligned parallel arrays"
        )
    return columns


def _date_value(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise EdgarNormalizationError(
            f"payload field filings.recent.{field} must be an ISO date"
        ) from error
