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
annual report on SEC EDGAR, retrieve its primary document as untrusted text,
extract that document into readable plain text, and divide it into labelled,
possibly overlapping sections along the filer's own linking index. A Disclosed
Risk Analyst can turn one such section into a source-validated LLM analysis,
the first analyst in the project that reads raw filing prose rather than
already-normalized data. None of these capabilities is wired into the
research workflow.

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

Filing sectioning, along the filer's own index — validated against ASML's
20-F and NVIDIA's 10-K.

- `FilingSection` (label, anchor id, text) and `SectionedFiling` (filing,
  sections, sources) are new domain models. `SectionedFiling.sections` allows
  more than one section per anchor, since the mapping measured on ASML's
  filing is many-to-many.
- `extract_filing_sections` in a new `filings/sections.py` consumes
  `RetrievedFiling` directly, not `FilingText`: every boundary signal
  extraction discards is exactly what sectioning needs.
- The index is any `<tr>` linking to an in-document anchor, not a
  filer-specific search. A row's label is built from the row's own text
  (page numbers excluded), because ASML links only its page-number cell while
  NVIDIA links every cell in a row — using only the linked cell's text would
  have lost ASML's caption.
- A section's span runs from its anchor's raw-text offset to whichever cited
  anchor's offset comes next; an id present in the document but never cited
  by the index does not bound a section, only cited targets do.
- Adds no source, matching the precedent `FilingText` set: sectioning is a
  transformation of an already-retrieved document, not a new retrieval.
- Tested with the established dual-fixture convention: synthetic cases isolate
  overlap, dangling targets, multi-target rows, and non-table links; the two
  recorded real fixtures validate the mechanism against real structure,
  including the exact label wording each filer's own markup produces.

Disclosed Risk Analyst — reads one filing section, not the filer's whole
document, and not another analyst's interpretation.

- `DisclosedRiskAnalysis` (`disclosed_risks`, `limitations`, `sources`) is a
  new output model, structurally parallel to `BearAnalysis` but a distinct
  responsibility: it extracts risks the filer itself names, not risks
  inferred from business and financial context. Reuses the same
  `validate_risk_sources` pattern.
- `build_disclosed_risk_analysis_prompt` and `GroqDisclosedRiskAnalyst`
  follow the established two-file split (`agents/disclosed_risk.py`,
  `agents/disclosed_risk_groq.py`) every other analyst uses.
- `FilingSection` carries no source of its own, so `filing_section_source`
  derives one: `source_id` is `"{accession_number}:{anchor_id}"`, `url` is
  the document URL with `#{anchor_id}` appended — a real, dereferenceable
  in-document anchor, not a synthetic identifier. `captured_on` reuses
  `filing.filed_on`, since no separate retrieval timestamp reaches a
  `FilingSection`. This cites at section granularity, not document
  granularity: two different claims from two different sections of the same
  filing get two different, individually verifiable source IDs.
- The prompt is the first place in the project that states the untrusted-text
  rule to a model directly, not only in code comments: it tells the model the
  filing text is untrusted third-party content to read and quote, never
  instructions, even if it appears to contain any.
- Not wired into `run_research` or the CLI. That needs ticker-to-CIK
  resolution, which does not exist; see Known Limitations.
- Tested against the recorded NVIDIA fixture's real Risk Factors section text,
  not only synthetic sections.

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

## Measured Section-Boundary Findings

A second live fetch on 2026-08-20 answered the open section-boundary question.
Same filing (accession `0001628280-26-011378`, filed 2026-02-25, 24,864,615
bytes, extracting to 1,331,662 characters across 37,760 lines, reproducing the
scale figures above exactly).

- **The filer supplies the sectioning scheme, and it is legally operative.**
  "Appendix – Reference table 20-F" maps each SEC 20-F item to a named location
  in the document, a page number, and a link. The filing then states that only
  the information referenced in that table, the table itself, the
  forward-looking-statements section, and the exhibits "shall be deemed to be
  filed with the Securities and Exchange Commission". The table is not
  navigation furniture; it defines which parts of a 350-page annual report are
  the 20-F.
- **The table is machine-readable.** Its columns are `Item`, `Form 20-F
  caption`, `Location in this document`, `Page`. It sits in the last 1% of the
  source (offsets 23.96–24.19 MB), repeats its header across four pages, and
  holds 117 rows, 59 of which carry an in-document link. Rows take six shapes:
  part divider, item whose location is `Not applicable`, item header whose
  sub-items follow, sub-item with a location, continuation row adding a further
  location to the sub-item above it, and running page furniture that is not
  data.
- **Anchors are empty positioned marker divs.** All 50 link targets are
  `<div id="…" style="position:absolute;top:…pt"></div>` carrying zero text.
  Section content lives in the following siblings, never inside the marker.
  Every target resolves; none dangle.
- **The item-to-location mapping is many-to-many.** Item 4.B cites six
  locations, and `At a glance` is cited by both 4.A and 4.B. Sections overlap,
  so a model that partitions the document into disjoint sections is wrong for
  this filing.
- **Anchors do not partition the document.** In document order their gaps run
  from 93 to 9,574,081 characters, median 234,858. The largest gap is the
  Sustainability statements block, which the reference table deliberately does
  not cite and which is therefore outside the 20-F.
- **What follows a marker varies in shape.** The `At a glance` marker is
  followed by five flat sibling blocks; the risk-factors marker is followed by
  one 49,265-character container. Reading forward in document order handles
  both; counting sibling nodes does not.
- **`Item` headings are still absent from the body, but the table names every
  item.** In extracted text `\bItem\b` occurs 13 times and only seven lines
  begin with `Item `. Six of those are AGM agenda items ("Item 1 Discussion of
  the Management Report…") and the seventh is the cover-page checkbox line
  "Item 17 ☐ Item 18 ☐". `Item 3.D` and `Item 4.B` still match zero times. A
  sectioner keying on `^Item \d` would match nothing but false positives. The
  reference table names items as bare cell values — `3`, `4`, `4A`, `16J` — not
  as `Item 3.D` strings.
- **No heading tags and no paragraph tags exist.** 78,027 `div`, 62,010 `span`,
  1,590 `table`, 0 `p`, 0 `h1`–`h6`. The `p` entry in the extractor's
  `_BLOCK_TAGS` never fires on this filer, and heading level cannot come from
  tag names. The string "Table of Contents" appears nowhere.
- **Extraction currently discards every boundary signal.** `FilingText` retains
  no element ids, no `href`s, and no anchor strings, and all 50 marker elements
  render to empty text. Sectioning cannot run on `FilingText` alone: it needs
  the HTML, or extraction must carry positions forward.
- **Loose ends.** Two anchor id namespaces appear (`i1edf02a2…` and
  `i99abb9ae…`), one target has an anomalous long suffix
  (`…_91809220939599`), and one marker lands on a running page header rather
  than the note body it names.

## Measured Second-Filer Findings (NVIDIA 10-K)

A live fetch on 2026-08-20 pulled NVIDIA's Form 10-K (accession
`0001045810-26-000021`, filed 2026-02-25, period end 2026-01-25, 1,967,816
bytes — a domestic 10-K, not a "10-F"; that form does not exist) to test
whether the ASML findings above are filer-specific or general. They are a mix
of both.

- **The low-level DOM mechanism is identical.** Zero `<h1>`–`<h6>` and zero
  `<p>` tags, same as ASML (0 of each, across 1,917 `div` and 4,230 `span`).
  Anchor ids follow the same `i<32-hex>_<n>` pattern (e.g.
  `i82ea215a7c1f4862b6518f1348ddc832_13`), and every anchor is again an empty
  positioned `<div id="…"></div>` with zero own text, real content in
  following siblings — confirmed by running the project's actual
  `_extract_html_text` on marker elements and their siblings, not by
  inspection alone. This is very likely a shared filing-agent artifact (the
  same iXBRL rendering tool, commonly Workiva), not something specific to
  ASML or to Form 20-F.
- **The sectioning semantics are not identical.** NVIDIA supplies a literal,
  conventional Table of Contents — the string "Table of Contents" occurs 81
  times, and the real TOC table holds 237 links resolving to 38 distinct
  targets. Unlike ASML's reference table, every target is cited under
  exactly one `Item` label: zero overlap, a genuine one-to-one, sequential
  partition. The three apparent "links per target" are the item-number,
  caption, and page-number cells of one row, not distinct citations.
- **`Item` headings exist as real prose here, but are not uniquely
  locatable by text alone.** `Item 1A. Risk Factors` appears exactly once as
  a section heading (immediately after its marker) but six times overall in
  the 339,478-character extracted text: the other five are the filing's own
  inline cross-references ("Refer to 'Item 1A. Risk Factors' for a
  discussion…"). A sectioner keying on heading text without position
  information would need to disambiguate a heading from a citation of that
  heading — the same underlying problem as ASML, reached by a different
  route. It reinforces, rather than weakens, the finding that `FilingText`
  alone cannot carry sectioning.
- **Internal links have one source.** All 237 `<a href="#…">` anywhere in
  the document belong to the TOC; body prose never links to a section, it
  only names it. ASML's document had internal links inside the reference
  table only as well, but ASML's body separately used many `Item` names
  without any link — NVIDIA's cross-references are prose-only mentions, not
  a second, competing link structure.
- **Scale differs by an order of magnitude.** 1.97 MB of source HTML yields
  339,478 characters across 2,094 lines — a normal-sized 10-K, not inflated
  by anything resembling ASML's Sustainability appendix. `normalize_latest_annual_report`
  and `EdgarFilingProvider` needed no changes to retrieve or decode it: `10-K`
  was already a first-class `AnnualReportFormType`, and extraction is
  form-agnostic.
- **What is still unverified.** Two filings is not enough to know whether the
  marker-div mechanism is filing-agent-universal or a coincidence of two
  large filers happening to use the same agent. Other common SEC filing
  agents (e.g. Donnelley Financial Solutions, Toppan Merrill) may render
  real semantic heading tags instead. Nothing here should be read as "all
  10-Ks look like this."

## Current / Next Slice

No implementation slice is currently active. Filing sectioning and the
Disclosed Risk Analyst, described in "Completed Filing-Ingestion Slices"
above, are both implemented. Mechanism details are recorded there rather than
repeated here, to avoid drifting out of sync with the code as it evolves.

### Explicitly Out of Scope (carried out of the completed slices)

- chunking, embeddings, retrieval, RAG, pgvector, PostgreSQL, FastAPI, Docker;
- wiring the Disclosed Risk Analyst, or any filing capability, into
  `run_research` or the CLI — blocked on ticker-to-CIK resolution;
- a second filing-derived analyst, or generalizing "one section in, one
  analysis out" to many sections at once;
- caching or persisting retrieved documents, sections, or analyses;
- a second filing source, provider fallback, or a second LLM provider;
- generalizing the sectioning mechanism to a third, unexamined filing agent;
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
- `src/equity_research_agent/filings/sections.py` — filing sectioning along
  the filer's own linking index
- `src/equity_research_agent/models/disclosed_risk_analysis.py` — output
  contract for the Disclosed Risk Analyst
- `src/equity_research_agent/agents/disclosed_risk.py` — its prompt builder
  and section-level source derivation
- `src/equity_research_agent/agents/disclosed_risk_groq.py` — its Groq adapter
- `src/equity_research_agent/agents/bear.py` and `bear_groq.py` — the
  established prompt/adapter split this analyst follows
- `src/equity_research_agent/models/provenance.py` — source-reference model and
  merge behavior
- `src/equity_research_agent/__init__.py` — current workflow composition; does
  not yet call any filing-derived analyst
- `tests/` — executable behavior and established testing conventions
- `tests/test_filing_sectioning.py` — synthetic and real-fixture tests for
  `extract_filing_sections`
- `tests/test_disclosed_risk_analyst.py` — prompt-builder and output-model
  tests, including one against the real NVIDIA Risk Factors section
- `tests/test_disclosed_risk_groq.py` — Groq adapter tests with a fake opener
- `tests/fixtures/providers/sec_edgar/asml/asml_20f_excerpt.htm` — trimmed
  excerpt of the real filing; the header comment records its provenance
- `tests/fixtures/providers/sec_edgar/asml/inline_xbrl_excerpt.htm` — synthetic
  fixture that isolates individual extraction rules
- `tests/fixtures/providers/sec_edgar/asml/reference_table_excerpt.htm` —
  trimmed excerpt of the filer's 20-F reference table, three of the empty
  marker divs it links to, and the content following each; used by
  `test_filing_sectioning.py` to validate against real structure
- `tests/fixtures/providers/sec_edgar/asml/annual_report.htm` — synthetic
  document-retrieval fixture. Note that its `Item 3.D. Risk Factors` heading is
  a structure the real filing does not contain; it exercises retrieval, and
  sectioning must not be validated against it
- `tests/fixtures/providers/sec_edgar/nvda/toc_excerpt.htm` — trimmed excerpt
  of NVIDIA's real 10-K Table of Contents, two of the empty marker divs it
  links to, and the content following each; used by
  `test_filing_sectioning.py` as a second-filer comparison

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
  prompt outside an explicit evidence boundary. The Disclosed Risk Analyst is
  the first such boundary and states the rule directly in its prompt, not
  only in code comments — treat that instruction as a required part of any
  future prompt that includes filing text, not optional boilerplate.
- Citation granularity matches what a claim can actually be checked against.
  A `FilingSection` carries no source of its own; the Disclosed Risk Analyst
  derives one per section (`accession_number:anchor_id`) rather than citing
  at whole-document granularity, so two claims from two different sections of
  the same filing stay independently verifiable.
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

Freshly verified locally on 2026-08-20. Filing sectioning is committed at
`f7ed519`; the Disclosed Risk Analyst above it is uncommitted at time of
writing:

- `uv run pytest`: 501 passed
- `uv run ruff check`: passed
- `uv run mypy`: passed for configured `src` (45 files)
- `git diff --check`: passed

Automated checks make no live provider or model calls; EDGAR behavior is
verified against recorded submissions and document fixtures. A fresh agent
should rerun checks relevant to any new change.

The section-boundary findings above came from one live EDGAR fetch on
2026-08-20 (two requests, no API key, no quota consumed), made through
`EdgarFilingProvider` with a declared contact user agent. The measurements are
reproducible from `reference_table_excerpt.htm` without refetching.

The second-filer findings came from one further live EDGAR fetch the same
day (two more requests, same provider, same declared contact user agent) of
NVIDIA's 10-K. Reproducible from `toc_excerpt.htm` without refetching.

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
- Filing sections are produced but never chunked, embedded, or searched, and
  no RAG capability exists.
- The Disclosed Risk Analyst reads exactly one section per call. There is no
  batch entry point for many sections, and it is not wired into `run_research`
  or the CLI — both blocked on ticker-to-CIK resolution, not on the analyst
  itself.
- `filing_section_source`'s `captured_on` reuses `filing.filed_on`, not an
  actual retrieval timestamp, because `FilingSection` carries no provenance of
  its own to draw one from. Close enough for a filing (it does not change
  after filing), but not a measured retrieval time the way document-level
  sources are.
- Extraction discards element ids, links, and document positions, so
  `FilingText` alone cannot locate a section boundary. Measured, not assumed;
  it is why sectioning consumes `RetrievedFiling` HTML directly instead.
- Sectioning only recognizes table-row-based indices, and only rows that link
  to an anchor. A filer whose sectioning device is not a table, or an
  unrelated internal link inside an index-shaped `<tr>` (a footnote
  cross-reference, say), would be misread. Not observed in either filer
  sampled.
- A row's label drops any cell whose text is purely digits, on the
  assumption that a bare number is a page reference. A filer whose item
  number itself renders as a bare digit (not observed in either filer
  sampled) would lose that number from the label.
- Sectioning treats every internal link in a linked `<tr>` as belonging to
  the index; it does not try to detect or rank which container in a document
  is "the" index by link density. Matches both filers measured, where no
  other internal links compete, but is unverified against a filer with a
  second, unrelated internal-link structure.
- Extraction concatenates adjacent inline elements that carry no source
  whitespace, so absolutely-positioned columns can fuse. Accepted deliberately;
  the alternative introduced far more damage elsewhere.
- Extraction is validated against two filers' markup (ASML's 20-F, NVIDIA's
  10-K), both structurally identical at the DOM level (no heading or
  paragraph tags, same anchor-id scheme). A filer using a different filing
  agent may need different handling, and the cheap way to find out is one
  live fetch.
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
- ~~What marks a section boundary in a filing that has no `Item` headings?~~
  Measured: the filer's cross-reference table, which is also the filer's own
  statement of what is legally part of the 20-F. The competing candidates are
  ruled out for this document — no heading tags, no table of contents, no body
  `Item` headings.
- ~~Should sectioning consume HTML, or should extraction be extended to carry
  positions into `FilingText`?~~ Decided and implemented: `extract_filing_sections`
  consumes `RetrievedFiling.untrusted_text` directly. `FilingText`/extraction
  were left unchanged, so nothing that only needs plain text pays for
  sectioning's HTML parse.
- ~~How should overlapping sections be modelled?~~ Decided and implemented:
  `SectionedFiling.sections` is a tuple of `FilingSection`, and more than one
  section may share an `anchor_id` with identical `text`. NVIDIA's
  non-overlapping 10-K is just the case with zero repeats.
- Should sectioning be filer-specific? Still partially open. The mechanism
  implemented (any `<tr>` linking to an in-document anchor is an index row)
  generalized cleanly across both filers sampled without special-casing
  either one, which is more encouraging than the earlier "Workiva/ASML
  convention" framing suggested. But it is still only two filings, plausibly
  from the same filing agent. Unverified: a filer whose sectioning device is
  not table-row-based, or one with a competing internal-link structure.
- ~~Now that sections exist, what is the next real consumer?~~ Decided: a
  Disclosed Risk Analyst, reading one section directly rather than waiting on
  chunking/embeddings. Full RAG (Phase 2.5) remains for when one section at a
  time stops being enough.
- Now that a filing-derived analyst exists: does it get wired into
  `run_research` next, or does ticker-to-CIK resolution come first? The
  analyst itself does not need it to be useful standalone, but the CLI does.
  Not selected; the roadmap does not choose this automatically.
- Should other sections beyond Risk Factors get their own dedicated analyst
  (e.g. a Business-Description-from-filing reader), or should one analyst
  generalize across section labels? Not yet needed with one section type
  proven; premature to decide with a sample of one.

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
