# Alpha Vantage ASML provider contract

## Decision

**GO for V0**, with explicit limitations for market-based metrics.

Alpha Vantage provides enough ASML data for the company profile, five aligned annual
financial periods, and the deterministic non-market metrics in the V0 plan. The
fundamentals are reported in EUR while the Nasdaq ADR trades in USD. V0 must therefore
mark cross-currency valuation metrics as unavailable rather than combine them.

## Spike scope

- Capture date: 2026-08-17
- Requested security: `ASML`
- Raw response fixtures: `tests/fixtures/providers/alpha_vantage/asml/`
- Endpoints checked: `SYMBOL_SEARCH`, `OVERVIEW`, `INCOME_STATEMENT`,
  `BALANCE_SHEET`, `CASH_FLOW`, `EARNINGS`, and `TIME_SERIES_DAILY`
- Daily-series parameters: compact output, which returned 100 observations

The fixtures preserve the response content. Only JSON indentation and a final newline
were added. They contain no request credentials.

The exact retrieval time was not recorded; only the capture date is known. This is a
reproducibility limitation of the spike and must not be represented later as an exact
`retrieved_at` timestamp.

### Non-sensitive request shapes

The credential parameter is intentionally omitted from these query shapes:

| Fixture | Query shape |
| --- | --- |
| `symbol_search.json` | `function=SYMBOL_SEARCH&keywords=ASML` |
| `overview.json` | `function=OVERVIEW&symbol=ASML` |
| `income_statement.json` | `function=INCOME_STATEMENT&symbol=ASML` |
| `balance_sheet.json` | `function=BALANCE_SHEET&symbol=ASML` |
| `cash_flow.json` | `function=CASH_FLOW&symbol=ASML` |
| `earnings.json` | `function=EARNINGS&symbol=ASML` |
| `time_series_daily.json` | `function=TIME_SERIES_DAILY&symbol=ASML&outputsize=compact` |

### Formatted fixture hashes

These SHA-256 values identify the pretty-printed fixture files committed to the
repository. They are **formatted fixture hashes**, not hashes of the original HTTP
response bodies.

| Fixture | SHA-256 |
| --- | --- |
| `balance_sheet.json` | `633d252dbb0e1dcd26e2890fead9c7ac747e144162102befe24f689e7f3611d0` |
| `cash_flow.json` | `dada803ce4332be85350d2fd56c08d90792fabe8a9343b01c50ee3650d3f48ee` |
| `earnings.json` | `b27058cb4044862173fbbe2102c5f9b35033eef100ef4268052cb220f20cfb4e` |
| `income_statement.json` | `d551156e7c7ad08d0d0fff6b56f3bf89174dc250846f1911dab973e4accb4dca` |
| `overview.json` | `4720495f704f4308dc036bbd36427ed1b2fd89757fe34ec3490ce37ef4494182` |
| `symbol_search.json` | `134bb4d2e9d0be5914e84daffbc7d7eb757a795af0d756f0179581663f15ca1c` |
| `time_series_daily.json` | `d97a3137e23804bee62cb338cd0a26061bebc7e44bf672e59134cc40733b35fb` |

Official references:

- [Alpha Vantage API documentation](https://www.alphavantage.co/documentation/)
- [Fundamental data normalization notes](https://documentation.alphavantage.co/FundamentalDataDocs/index.html)
- [Alpha Vantage usage limits](https://www.alphavantage.co/support/)

## Observed identity and currencies

| Concern | Observed evidence | Contract result |
| --- | --- | --- |
| Exact symbol | Symbol search returns `ASML` with match score `1.0000` | Pass |
| Instrument | Overview identifies `ASML Holding NV ADR`, common stock, on Nasdaq | Pass |
| Identifier | Overview contains CIK `937966` | Pass |
| Listing currency | Symbol search and overview both report USD | Pass |
| Reporting currency | All inspected annual statements report EUR | Pass |
| Fiscal year end | Overview reports December; statement periods end on December 31 | Pass |
| Security distinction | Search also returns `ASML.AMS` in EUR and other listings | Pass; ticker resolution must preserve listing identity |

`ASML` is the US-listed ADR. Its USD listing currency must not be treated as the EUR
reporting currency of ASML Holding N.V.

## Period coverage

| Payload | Annual records | Quarterly records | Five completed aligned periods |
| --- | ---: | ---: | --- |
| Income statement | 20 | 81 | 2025-12-31 through 2021-12-31 |
| Balance sheet | 20 | 81 | 2025-12-31 through 2021-12-31 |
| Cash flow | 20 | 81 | 2025-12-31 through 2021-12-31 |
| Earnings | 31 | 108 | 2025-12-31 through 2021-12-31 |

The income, balance-sheet, cash-flow, and EPS period sets match exactly for the latest
five completed fiscal years.

The first `annualEarnings` item is dated `2026-06-30`, even though it is not a completed
December fiscal year. A future adapter must join records by `fiscalDateEnding` and
select periods shared with the annual statements. It must not assume that the first
`annualEarnings` item is the latest completed year.

## Field contract

"Available for five years" means the field is present and is neither empty nor the
provider sentinel string `"None"` in each period from 2025 through 2021.

| Domain input | Alpha Vantage field | Available for five years | Notes |
| --- | --- | --- | --- |
| Revenue | `totalRevenue` | Yes | EUR |
| Gross profit | `grossProfit` | Yes | EUR |
| Operating income | `operatingIncome` | Yes | EUR |
| Pretax income | `incomeBeforeTax` | Yes | EUR |
| Income tax | `incomeTaxExpense` | Yes | EUR |
| Net income | `netIncome` | Yes | EUR |
| D&A for EBITDA | `depreciationAndAmortization` | Yes | `ebitda` is also present, but V0 should calculate rather than trust a provider-derived metric |
| Cash | `cashAndCashEquivalentsAtCarryingValue` | Yes | EUR |
| Total debt candidate | `shortLongTermDebtTotal` | Yes | EUR; documented by Alpha Vantage as combined short- and long-term debt |
| Shareholder equity | `totalShareholderEquity` | Yes | EUR |
| Period-end shares | `commonStockSharesOutstanding` | Yes | Raw share count |
| Operating cash flow | `operatingCashflow` | Yes | EUR |
| Capital expenditure | `capitalExpenditures` | Yes | Positive cash-outflow amount in the provider taxonomy |
| Annual EPS | `reportedEPS` | Yes | Endpoint has no currency field; periods align with EUR statements |

Several optional fields contain the literal string `"None"`. In particular,
`currentDebt` and `longTermDebtNoncurrent` are missing in all five periods, and
`shortTermDebt` is missing for 2025. The combined `shortLongTermDebtTotal` field is
present in all five periods. A future adapter must convert `"None"` to an explicit
missing value and must not convert it to zero.

Overview normalization must be allowlist-only. The V0 allowlist is `Symbol`,
`AssetType`, `Name`, `Description`, `CIK`, `Exchange`, `Currency`, `Country`, `Sector`,
`Industry`, `FiscalYearEnd`, `LatestQuarter`, `MarketCapitalization`, and
`SharesOutstanding`. No uncontracted overview field may pass through the provider
boundary. This is required because the captured payload reports `SharesFloat` as
`21331634000` while `SharesOutstanding` is `384100000`, an implausible relationship.
`SharesFloat` must not be normalized or used in V0.

## V0 metric coverage

| Metric | Contract result | Source fields or reason |
| --- | --- | --- |
| Revenue CAGR | Available | `totalRevenue` |
| EPS CAGR | Available with documented currency caveat | `reportedEPS`, aligned to EUR fiscal periods |
| Free cash flow | Available | `operatingCashflow`, `capitalExpenditures` |
| FCF margin | Available | FCF and `totalRevenue`, both EUR |
| Operating margin | Available | `operatingIncome`, `totalRevenue` |
| Gross margin | Available | `grossProfit`, `totalRevenue` |
| ROIC | Available | Operating income, tax, cash, combined debt, and equity |
| Net debt | Available | Combined debt and cash, both EUR |
| Net debt / EBITDA | Available | Net debt and deterministic EBITDA inputs, all EUR |
| Share count CAGR | Available | `commonStockSharesOutstanding` |
| FCF yield | Unavailable in V0 for ASML | EUR FCF and USD market capitalization; no V0 FX conversion |
| P/E | Unavailable in V0 for ASML | EUR earnings and USD market capitalization; provider P/E must not replace the deterministic calculation |
| EV / EBITDA | Unavailable in V0 for ASML | USD equity value cannot be added to EUR net debt without FX conversion |

## Market snapshot findings

The compact daily response is for `ASML`, uses the `US/Eastern` timezone, and contains
100 observations. Its latest completed observation is `2026-08-14`, with a close of
`1844.0800`.

Overview reports:

- `MarketCapitalization`: `708311122000`
- `SharesOutstanding`: `384100000`

Dividing those values implies a price of approximately `1844.08`, matching the latest
daily close to rounding. This is evidence that the overview market capitalization was
calculated from the same price snapshot. However, `OVERVIEW` supplies no explicit
market-cap timestamp. V0 may preserve it as a provider fact with its retrieval time,
but must not claim an exact `as_of` supplied by Alpha Vantage.

## Provider decision and guardrails

Alpha Vantage remains the V0 provider because the critical company and historical
fundamental inputs are present for ASML and the free-tier call volume is sufficient for
the walking skeleton. The limitations do not block the V0 definition of done, which
allows incompatible market-based metrics to be explicitly unavailable.

A future adapter must enforce these rules:

1. Reject an HTTP-200 response before normalization when its top level contains
   `Information`, `Note`, `Error`, or `Error Message`.
2. Resolve and preserve the exact ADR identity before loading data.
3. Select annual data by shared `fiscalDateEnding`, not array position.
4. Keep statement EUR separate from listing USD.
5. Treat `"None"` as missing, never as zero.
6. Normalize Overview using only the explicit V0 allowlist; never pass through other fields.
7. Use `shortLongTermDebtTotal` for the V0 total-debt candidate and retain source-field traceability.
8. Normalize CapEx as a positive outflow before calculating FCF.
9. Do not use provider-supplied ratios as deterministic project calculations.
10. Mark FCF yield, P/E, and EV/EBITDA unavailable when currency compatibility cannot be proven.
11. Record retrieval time for future overview facts and the explicit last-refreshed date for daily prices.

The spike does not validate Alpha Vantage for arbitrary international listings. Its
decision applies only to the V0 ASML ADR walking-skeleton path.
