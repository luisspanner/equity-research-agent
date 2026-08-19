# Project Handoff

Last updated: 2026-08-19

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
recent annual report on SEC EDGAR and return its metadata. This capability is
not yet wired into the research workflow.

## Latest Completed Slice

Commit `69ac4cc` added the first Phase 2 filing-ingestion slice: EDGAR
annual-report discovery, metadata only.

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

Deliberate behaviors: selection is by latest filing date rather than payload
order; amendments such as `20-F/A` are excluded by exact form match; a missing
primary document is an explicit error rather than a silent fallback to an older
filing; the filing document itself is never downloaded.

## Current / Next Slice

No implementation slice is currently active.

The natural next step is filing-document retrieval: fetch the primary document
identified by an existing `FilingReference` and store it as sourced, explicitly
untrusted raw text. Parsing, sectioning, search, embeddings, and analyst
integration each remain separate later slices.

### Explicitly Out of Scope

- parsing, sectioning, chunking, or summarizing filing text;
- filing search, embeddings, RAG, pgvector, PostgreSQL, FastAPI, or Docker;
- exposing filing text to any analyst prompt;
- ticker-to-CIK resolution, a second filing source, or provider fallback;
- valuation, persistence, web UI, or other later roadmap phases;
- unrelated application refactoring.

## Relevant Files

- `AGENTS.md` — development and collaboration contract
- `README.md` — product purpose and high-level architecture
- `ROADMAP.md` — sequencing and Phase 2 direction
- `src/equity_research_agent/models/filings.py` — discovered-filing contract
- `src/equity_research_agent/data/providers/base.py` — provider protocols
- `src/equity_research_agent/data/providers/edgar.py` — submissions normalizer
- `src/equity_research_agent/data/providers/edgar_provider.py` — EDGAR transport
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
  sources record the submissions index that supplied its metadata, not the
  filing document, which has not been read.
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

Freshly verified locally on 2026-08-19 against commit `69ac4cc`:

- `uv run pytest`: 377 passed
- `uv run ruff check`: passed
- `uv run mypy`: passed for configured `src`
- `git diff --check`: passed

No live provider or model calls were made; EDGAR behavior is verified against a
recorded submissions fixture. A fresh agent should rerun checks relevant to any
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
- No filing document is retrieved, parsed, or searched, and no RAG capability
  exists.
- Valuation, persistence, an API, observability, and a web product remain future
  roadmap work.
- `asml-report.md` is an untracked local report and should not be changed or
  committed without explicit direction.

## Open Questions

- Should retrieved filing documents be stored on disk, held in memory, or both?
  This decides whether a storage boundary is needed before parsing.
- Where does ticker-to-CIK resolution belong once the workflow needs filings:
  the financial-data provider, a dedicated resolver, or the caller?
- What is the smallest useful representation of a retrieved document that keeps
  its untrusted nature explicit at the type level?

## Next Expected Steps

1. Select and review one bounded filing-retrieval slice.
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
