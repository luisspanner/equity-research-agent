# Project Handoff

Last updated: 2026-08-20

## Current State

The project has a working CLI research pipeline. Given a ticker, it retrieves a
company profile, normalized annual financial statements, and a market snapshot
from Alpha Vantage; calculates core financial metrics in deterministic Python;
runs source-bounded Business, Bear, and Financial Quality Analysts plus Research
Synthesis through Groq; and renders a sourced Markdown report.

The Bear Analyst receives a provenance-aware financial-risk context. The
Financial Quality Analyst is fully integrated into workflow orchestration,
Synthesis, and reporting, and its findings are validated against the exact
deterministic metrics and source IDs they cite.

Separately from that pipeline, the project can now discover an issuer's most
recent annual report on SEC EDGAR and retrieve its primary document as
untrusted text. Neither capability is wired into the research workflow.

## Completed Filing-Ingestion Slices

Commit `69ac4cc` — EDGAR annual-report discovery, metadata only.

- `FilingReference` records CIK, form type, accession number, period end,
  filing date, primary-document URL, and source provenance.
- Accepted form types are the Literal `10-K` and `20-F`; the normalizer's
  filter is derived from that Literal so the two cannot drift apart.
- `FilingProvider` is a separate protocol from `FinancialDataProvider`, because
  filings are documents keyed by issuer CIK rather than statement data keyed by
  a listed ticker.
- `edgar.py` normalizes the submissions index with no I/O; `edgar_provider.py`
  handles transport only, including EDGAR's required contact user agent and
  conservative request throttling.
- Selection is by latest filing date rather than payload order, and amendments
  such as `20-F/A` are excluded by exact form match.

Commit `9fd9589` — filing-document retrieval, in memory only.

- `RetrievedFiling` records its `FilingReference`, declared content type,
  retrieved payload size, document text, and provenance. The text field is
  named `untrusted_text` and is stored exactly as retrieved.
- The document becomes a citable source in its own right: `source_type`
  `annual_report_document`, `source_id` the accession number, carrying the
  filing's period end.
- Retrieval guards the first hostile input in the system: an archive-URL prefix
  check, a configurable size limit enforced by reading one byte past it, a text
  content-type allowlist, and decoding via the declared character set with an
  explicit error on failure.
- A payload-supplied primary-document name is interpolated into the archive
  URL, so only plain EDGAR file names are accepted. Pydantic resolves relative
  segments when the URL is built, so the archive-prefix check also catches
  escapes that bypass the normalizer. Both layers are pinned by tests.

## Current / Next Slice

No implementation slice is currently active.

The next step is filing-text extraction: convert one `RetrievedFiling`'s HTML
into plain text suitable for later sectioning, without interpreting it.
Sectioning, chunking, search, embeddings, and analyst integration each remain
separate later slices.

### Explicitly Out of Scope

- section detection, chunking, summarizing, or interpreting filing text;
- filing search, embeddings, RAG, pgvector, PostgreSQL, FastAPI, or Docker;
- exposing filing text to any analyst prompt;
- caching or persisting retrieved documents;
- ticker-to-CIK resolution, a second filing source, or provider fallback;
- valuation, persistence, web UI, or other later roadmap phases;
- unrelated application refactoring.

## Relevant Files

- `AGENTS.md` — development and collaboration contract
- `README.md` — product purpose and high-level architecture
- `ROADMAP.md` — sequencing and Phase 2 direction
- `src/equity_research_agent/models/filings.py` — discovered- and
  retrieved-filing contracts
- `src/equity_research_agent/data/providers/base.py` — provider protocols
- `src/equity_research_agent/data/providers/edgar.py` — submissions normalizer
- `src/equity_research_agent/data/providers/edgar_provider.py` — EDGAR transport
  and document retrieval
- `src/equity_research_agent/models/provenance.py` — source-reference model and
  merge behavior
- `src/equity_research_agent/__init__.py` — current workflow composition
- `tests/` — executable behavior and established testing conventions

## Important Architectural Decisions

- Financial calculations are deterministic, tested Python. LLMs interpret
  supplied evidence and must not recalculate reliable metrics or invent missing
  data.
- Facts, calculated values, assumptions, and LLM interpretations remain
  distinguishable. Incompatible periods, currencies, or units must not be
  silently combined.
- Qualitative analysts operate within explicit evidence boundaries. Source
  provenance must survive workflow transformations, and source-bounded claims
  must not introduce unsupported facts.
- Provenance describes where data actually came from. A `FilingReference`'s
  sources record the submissions index that supplied its metadata; the filing
  document becomes its own source only once it has actually been retrieved.
- Retrieved filing text is untrusted third-party prose: evidence to be quoted
  and cited, never instructions to be followed. It must not reach a model
  prompt outside an explicit evidence boundary.
- Provider adapters separate pure normalization from transport. Normalizers are
  I/O-free and independently testable against recorded payloads.
- CIK zero-padding is an EDGAR request detail handled at the adapter boundary;
  the domain keeps the unpadded CIK already carried by `SecurityIdentity`.
- Add a dedicated analyst only when its responsibility, evidence boundary, or
  evaluation criteria are meaningfully distinct.
- Extract shared infrastructure only after duplication is demonstrated. Keep
  analyst-specific prompts, output models, and evidence contracts explicit
  where they encode different semantics.

## Verification Status

Freshly verified locally on 2026-08-20 against commit `9fd9589`:

- `uv run pytest`: 421 passed
- `uv run ruff check`: passed
- `uv run mypy`: passed for configured `src`
- `git diff --check`: passed

No live provider or model calls were made; EDGAR behavior is verified against
recorded submissions and document fixtures. A fresh agent should rerun checks
relevant to any
new change. Live CLI runs are deliberately reserved for bug investigation or for
validating several accumulated features because provider test runs are limited.

## Known Limitations

- Filing discovery reads only the `filings.recent` block of the EDGAR
  submissions index. An issuer whose latest annual report has aged out of that
  block raises rather than returning an older filing.
- Filing discovery takes a CIK. There is no ticker-to-CIK resolution, and
  nothing in the research workflow calls `EdgarFilingProvider` yet.
- Alpha Vantage is the only financial-data provider and EDGAR the only filing
  source currently implemented.
- Groq is the only LLM provider currently implemented. The workflow protocols,
  prompts, schemas, and provenance rules are largely provider-neutral, but a
  second provider still requires explicit adapters.
- Retrieved documents are held in memory only. Nothing is cached or persisted,
  so a second run refetches the same immutable filing.
- Filing documents are fetched and decoded but never parsed or searched, and no
  RAG capability exists.
- Document retrieval rejects an undeclared or non-text `Content-Type` and any
  text it cannot decode with the declared character set. Redirects are followed
  without re-checking the final URL against the archive-prefix guard.
- `get_latest_annual_report` still reads the submissions response without a
  size bound, unlike document retrieval. Known, deliberately left untouched.
- Valuation, persistence, an API, observability, and a web product remain future
  roadmap work.
- `asml-report.md` is an untracked local report and should not be changed or
  committed without explicit direction.

## Open Questions

- Storage was deliberately deferred: documents are in memory only. A
  filesystem cache keyed by accession number becomes worthwhile once repeated
  parser iteration makes refetching painful. Filings are immutable, so such a
  cache needs no invalidation. PostgreSQL and pgvector belong to Phase 2.5,
  when chunks and embeddings exist to query, not to raw document storage.
- Where does ticker-to-CIK resolution belong once the workflow needs filings:
  the financial-data provider, a dedicated resolver, or the caller?
- Does text extraction need its own dependency, and if so which one? EDGAR
  documents are inline XBRL HTML; the standard library's `html.parser` may be
  sufficient for a first extraction slice.

## Next Expected Steps

1. Select and review one bounded filing-text-extraction slice.
2. Inspect only the filing models, EDGAR adapter, and tests relevant to it.
3. Propose the implementation approach and affected files under `AGENTS.md`.
4. Wait for approval if the request is planning or review-first, then implement
   and verify only the selected slice.

## Cross-Agent Handoff

At a clean slice boundary: finish the slice, run verification, review the diff,
commit completed work, update this file, and update `ROADMAP.md` only if project
state or trajectory changed. Commit those handoff, roadmap, or other shared
documentation updates before starting the fresh agent so the version-controlled
source of truth is durable. A fresh Codex, Claude Code, or other agent then
re-orients from the repository, `git status`, and `git log --oneline -10` before
working. Agent conversations are disposable; repository state is durable.
