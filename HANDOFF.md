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

Separately from that pipeline, the project can discover an issuer's most recent
annual report on SEC EDGAR, retrieve its primary document as untrusted text, and
extract that document into readable plain text. None of these capabilities is
wired into the research workflow.

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

Commits `8eb93a3` and `f1acadf` — filing-text extraction, then its correction
against the real filing.

- `FilingText` carries extracted text with the filing and sources it came from.
  Extraction performs no retrieval, so it adds no source, and the field keeps
  the name `untrusted_text`: a more readable representation is not a more
  trustworthy one.
- A separate `filings` package holds post-retrieval processing, distinct from
  `data/providers`, which acquires data rather than transforming it.
- Extraction drops document metadata, scripts, styles, inline-XBRL headers, and
  hidden elements; treats block elements and line breaks as line boundaries;
  gives table cells an explicit space; and collapses whitespace including
  non-breaking spaces.
- Text nodes are joined with no separator, matching browser rendering. See the
  measured findings below for why the earlier space separator was removed.
- `beautifulsoup4` is the only dependency added, used with the standard-library
  parser backend.

## Measured Filing-Structure Findings

Carry these forward. They were measured against ASML's 2025 Form 20-F
(accession `0001628280-26-011378`, retrieved 2026-08-20), not assumed, and they
constrain the design of later slices.

- **The document has no `Item` headings.** `Item 3.D` and `Item 4.B` match zero
  times. This filer uses its own narrative structure with a cross-reference
  table. Sectioning cannot be built on SEC item-heading regexes and expect to
  work on the company the project tests with.
- **Line breaks do not mark sentences.** Each visual line is wrapped in its own
  absolutely-positioned `div`, so one sentence routinely spans five extracted
  lines. Chunking must not treat a line as a paragraph or a sentence.
- **A sentence's numbers live in sibling blocks, not in an ancestor.** Anything
  that walks up the DOM to find a passage's context will swallow the whole
  document.
- **Filer spacing is reliable; added spacing is not.** Joining text nodes with a
  space produced 1,115 spurious spaces before punctuation and split hundreds of
  words, while reducing fused tokens only from 47 to 46.
- **Columns can still fuse.** Cover-page columns laid out by absolute
  positioning carry no whitespace between inline elements, so they concatenate.
  `tests/test_filing_text_extraction.py` asserts this rather than hiding it.
- **Scale.** 24 MB of source HTML yields about 1.33 MB of text across roughly
  38,000 lines. There were no zero-width spaces or byte-order marks;
  normalizing `\xa0` was sufficient.

## Current / Next Slice

No implementation slice is currently active.

The next step is filing sectioning: divide one `FilingText` into labelled
sections that later chunking and retrieval can target. Because item headings do
not exist in this filer's document, the first design question is what a section
boundary actually is here — a heading style, a cross-reference table, a table of
contents, or explicit user-supplied anchors. Decide that before implementing.

### Explicitly Out of Scope

- chunking, embeddings, retrieval, RAG, pgvector, PostgreSQL, FastAPI, Docker;
- summarizing or interpreting filing text;
- exposing filing text to any analyst prompt;
- caching or persisting retrieved documents;
- ticker-to-CIK resolution, a second filing source, or provider fallback;
- valuation, persistence, web UI, or other later roadmap phases;
- unrelated application refactoring.

## Relevant Files

- `AGENTS.md` — development and collaboration contract
- `README.md` — product purpose and high-level architecture
- `ROADMAP.md` — sequencing and Phase 2 direction
- `src/equity_research_agent/models/filings.py` — discovered-, retrieved-, and
  extracted-filing contracts
- `src/equity_research_agent/data/providers/base.py` — provider protocols
- `src/equity_research_agent/data/providers/edgar.py` — submissions normalizer
- `src/equity_research_agent/data/providers/edgar_provider.py` — EDGAR transport
  and document retrieval
- `src/equity_research_agent/filings/text.py` — HTML-to-text extraction
- `src/equity_research_agent/models/provenance.py` — source-reference model and
  merge behavior
- `src/equity_research_agent/__init__.py` — current workflow composition
- `tests/` — executable behavior and established testing conventions
- `tests/fixtures/providers/sec_edgar/asml/asml_20f_excerpt.htm` — trimmed
  excerpt of the real filing; the header comment records its provenance
- `tests/fixtures/providers/sec_edgar/asml/inline_xbrl_excerpt.htm` — synthetic
  fixture that isolates individual extraction rules

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
- Filing processing lives in `filings/`, separate from `data/providers/`, which
  acquires data rather than transforming it.
- Extraction changes representation, never meaning. It adds no source and keeps
  the untrusted naming, so provenance and evidence boundaries survive it.
- Synthetic fixtures isolate single rules; recorded excerpts of real filings
  keep those rules honest. Both are kept deliberately.
- CIK zero-padding is an EDGAR request detail handled at the adapter boundary;
  the domain keeps the unpadded CIK already carried by `SecurityIdentity`.
- Add a dedicated analyst only when its responsibility, evidence boundary, or
  evaluation criteria are meaningfully distinct.
- Extract shared infrastructure only after duplication is demonstrated. Keep
  analyst-specific prompts, output models, and evidence contracts explicit
  where they encode different semantics.

## Verification Status

Freshly verified locally on 2026-08-20 against commit `f1acadf`:

- `uv run pytest`: 453 passed
- `uv run ruff check`: passed
- `uv run mypy`: passed for configured `src`
- `git diff --check`: passed

Automated checks make no live provider or model calls; EDGAR behavior is
verified against recorded submissions and document fixtures. A fresh agent
should rerun checks relevant to any new change.

Live runs differ in cost and should be treated differently. EDGAR needs no API
key and has no daily quota, so a live filing fetch costs two requests and is
worth doing whenever document handling changes; be polite with the declared
contact user agent and record what is learned as a fixture. Alpha Vantage has a
metered daily quota and Groq costs tokens, so full CLI runs stay reserved for
bug investigation or for validating several accumulated features.

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
- Filing documents are extracted to plain text but never sectioned or searched,
  and no RAG capability exists.
- Extraction concatenates adjacent inline elements that carry no source
  whitespace, so absolutely-positioned columns can fuse. Accepted deliberately;
  the alternative introduced far more damage elsewhere.
- Extraction is validated against one filer's markup. Another filer's HTML may
  need different handling, and the cheap way to find out is one live fetch.
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
- What marks a section boundary in a filing that has no `Item` headings? Options
  include heading styles, the filer's cross-reference table, the table of
  contents, or explicit caller-supplied anchors. This decides the next slice.
- Should sectioning be filer-specific? One document has been examined. A second
  filer, ideally a 10-K rather than a 20-F, would show which behavior is general
  and which is Workiva-specific.

## Next Expected Steps

1. Select and review one bounded filing-sectioning slice.
2. Inspect only the filing models, extraction, and tests relevant to it.
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
