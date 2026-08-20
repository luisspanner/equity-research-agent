# Project Roadmap

This roadmap is a sequencing guide, not an automatic implementation queue.
Each item is selected, designed, implemented, and reviewed as a small,
independently testable slice.

The guiding question for every new technology is:

> What current engineering problem does this technology solve?

Learning goals must support good architecture, not override it. The project
introduces concepts when they solve a real research-product problem rather
than as a checklist of frameworks.

## Current Position

**V0 walking skeleton is complete and manually validated.** The CLI runs a
sourced research flow from ticker input to a Markdown report. It includes
Alpha Vantage retrieval, normalized annual financial data, deterministic core
metrics, Business and Bear Analysts, Financial Quality interpretation,
Synthesis, and source-aware reporting.

Completed after V0:

- [x] Provenance-preserving financial-risk context
- [x] Financial-source citations for Bear Analyst inputs and results
- [x] Financial Quality Analyst, integrated into workflow orchestration,
  Synthesis, and the Markdown report
- [x] Focused duplication cleanup for shared Groq transport/response mechanics
  and exact source-reference merging
- [x] EDGAR annual-report discovery, metadata only
- [x] EDGAR filing-document retrieval as sourced, untrusted text, held in
  memory only
- [x] Filing-text extraction, validated against the real ASML Form 20-F
- [x] Filing sectioning along the filer's own linking index, validated
  against both ASML's 20-F and NVIDIA's 10-K
- [x] Disclosed Risk Analyst, reading one filing section directly rather
  than waiting on chunking or embeddings
- [x] Ticker-to-CIK resolution on `EdgarFilingProvider`, validated with a
  live fetch against SEC's real ticker file
- [x] Deterministic selection of a unique disclosed-risk section by filing
  form item: 10-K Item 1A or 20-F Item 3.D

No filing capability is used by the research workflow yet — the Disclosed
Risk Analyst is not wired into `run_research` or the CLI, and
the workflow neither uses a profile CIK when present nor falls back to SEC
resolution when it is missing. Ticker-to-CIK resolution exists now, so that
wiring is no longer blocked on a missing capability, but it has not been
selected as a slice. No implementation slice is currently active. The roadmap
does not select or begin the next one automatically.

Live CLI runs are reserved for bug investigation or after several new features
have accumulated. Unit, integration, lint, and type checks are the default
verification for individual slices.

## Phase 0 — V0 Walking Skeleton

Completed pipeline:

```text
Ticker
→ Financial Data
→ Deterministic Metrics
→ Business Analyst
→ Bear Analyst
→ Synthesis
→ Sourced Markdown Report
```

- [x] Project setup and domain models
- [x] Financial-data provider interface and Alpha Vantage provider
- [x] Normalized annual company financial data
- [x] Deterministic core financial metrics
- [x] Business Analyst
- [x] Bear Analyst
- [x] Research Synthesis
- [x] Markdown report
- [x] End-to-end CLI

V0 remains intentionally narrow; later phases do not retroactively expand its
scope.

## Phase 1 — Financial Quality and Provenance

Goal: make financial interpretation as source-traceable as the rest of the
research flow while keeping reliable calculations deterministic.

- [x] Interpret supplied deterministic financial metrics through the Financial
  Quality Analyst without allowing it to calculate, forecast, or introduce
  unsupported facts.
- [x] Preserve Financial Quality metric-to-source provenance through Synthesis
  and the report.

- [x] Extract duplication already demonstrated in repeated Groq transport,
  JSON-response parsing and safe error handling, and exact source-merging
  behavior.

Keep analyst prompts, output models, and evidence contracts explicit. They
have different evidence boundaries and should not become a generic abstraction
without a demonstrated need.

## Phase 2 — Filing Ingestion and Broader Research Coverage

Goal: move beyond structured financial APIs so analysts can use high-quality
primary-source company documents.

Build this incrementally:

- filing discovery and retrieval for SEC EDGAR, annual reports, 10-K, 10-Q,
  20-F, investor-relations, and appropriate earnings documents;
- parsing, document metadata, source provenance, and section-aware processing;
- filing search before adding broad document reasoning;
- multiple financial-data providers, provider comparison, and an explicit
  fallback policy;
- improved qualitative citation provenance.

### Completed: filing discovery

The first ingestion slice chose SEC EDGAR as the primary source and the annual
report as the document type, covering both `10-K` and `20-F` so foreign private
issuers such as ASML are not a special case. It delivered the `FilingReference`
domain and provenance contract together with one metadata-only discovery
adapter, deliberately excluding document retrieval, parsing, search, and
analyst integration.

### Completed: filing-document retrieval

The second slice fetched the primary document identified by a
`FilingReference` and represented it as sourced, explicitly untrusted text held
in memory. It established the guards appropriate to the project's first hostile
input — URL, size, content type, and decoding — while leaving parsing,
caching, and persistence out.

### Completed: filing-text extraction

The third slice converted retrieved HTML into plain text and was then corrected
against the real ASML Form 20-F. Validating against a live filing changed the
implementation in ways no synthetic fixture had suggested, and the measured
findings are recorded in `HANDOFF.md`.

### Completed: filing sectioning

Divided a retrieved document into labelled, possibly overlapping sections
along the filer's own linking index — a legally operative cross-reference
table for ASML's 20-F, a conventional table of contents for NVIDIA's 10-K,
both marked the same underlying way at the DOM level. It deliberately
consumes retrieved HTML rather than extracted plain text, since extraction
discards every signal sectioning needs. Chunking and embeddings stayed out of
this slice; see `HANDOFF.md` for the mechanism, the two-filer validation, and
what remains unverified against a third filer.

### Completed: Disclosed Risk Analyst

A dedicated analyst reading one filing section directly — a distinct
evidence boundary from Bear Analyst's inferred downside risk, since this
extracts only the risks a filer discloses about itself. Skips chunking and
embeddings entirely: one section in, one source-validated analysis out, the
same evidence-bounded prompt/adapter pattern every other analyst uses. The
first analyst to read raw filing prose, and the first prompt in the project
that states the untrusted-content rule directly rather than only in code.
Not wired into `run_research` or the CLI; see `HANDOFF.md`.

### Completed: ticker-to-CIK resolution

`EdgarFilingProvider.resolve_cik` resolves a listed ticker to its SEC CIK by
fetching and exact-matching against SEC's `company_tickers.json`, reusing the
provider's existing rate limiting and contact-user-agent conventions rather
than a new resolver class. Validated with a live fetch of the real file.
Deliberately excludes fuzzy matching, caching, and populating
`SecurityIdentity.cik` or any workflow/CLI wiring — see `HANDOFF.md`.

### Completed: Risk Factors section selection

`select_risk_factors_section` establishes the exact one-section input boundary
for the existing Disclosed Risk Analyst. It selects by the SEC form's
structural item rather than its display title: 10-K Item `1A` or 20-F Item
`3.D`. Those mappings are form-defined; the HTML metadata parser is separately
limited to the measured ASML 20-F reference-table shape and a gated
NVIDIA-style 10-K table of contents. Missing metadata, conflicting text at one
anchor, or distinct expected-item anchors return typed unavailable reasons
rather than falling back to title matching or heuristic ranking. A later
workflow can render that outcome as a limitation. The selector is deterministic
and uses existing section data only; it does not retrieve filings, invoke an
LLM, or wire filing analysis into the CLI.

### Next selection: not yet chosen

Introduce dedicated Market, Moat, Growth, or further Risk Analysts only when
each has a distinct evidence boundary, responsibility, and evaluation
criterion—not merely because multiple LLM calls are possible.

### Roadmap candidate: quarterly reports (10-Q / 6-K)

Not selected yet. Discovery, retrieval, and extraction are already
form-agnostic, so fetching a 10-Q needs no plumbing changes there. The real
work is contract shape, not transport: `get_latest_annual_report` returns one
filing because "most recent annual report" is inherently singular, while
quarterly relevance comes mainly from comparing several recent periods —
that needs a "last N filings of a type" discovery contract, not just a new
form-type literal. Foreign private issuers such as ASML do not file 10-Qs at
all; their interim filing is the 6-K, which is far less standardized (often a
furnished press release with no fixed Item structure), so this is not a
uniform extension across both filer types the way annual reports were.
Revisit once quarterly recency is worth more than the added discovery-contract
complexity.

## Phase 2.5 — Retrieval / RAG Infrastructure

Goal: retrieve precise, approved primary-source evidence for downstream equity
research analysts. This is not generic "chat with PDF" infrastructure.

```text
Filing
→ Parse
→ Split / Chunk
→ Metadata
→ Embeddings
→ Vector Storage
→ Retrieval
→ Analyst Evidence Context
```

Planned slices include:

- chunk strategy, section metadata, and document-to-chunk provenance;
- embedding-model choice, retrieval quality, top-k behaviour, and metadata
  filtering;
- retrieval evaluation against known filing evidence;
- analyst contexts that treat retrieved text as data, not instructions.

Introduce technologies only when their boundary is useful:

- **FastAPI** when a reusable research or retrieval service/API boundary is
  needed; likely endpoints include filing ingest/search and research-run access.
- **PostgreSQL** when companies, filings, metadata, research runs, sources, or
  embeddings need persistence.
- **pgvector** as the likely initial vector store once embeddings exist, so
  structured data, metadata, and vectors can remain together.
- **Docker / Docker Compose** once the application/API and PostgreSQL are
  multiple runtime services requiring reproducible local development.

Avoid a separate vector database unless scale or requirements justify it.

## Phase 3 — Deterministic Valuation and Scenarios

Goal: add reproducible valuation tools with explicit assumptions.

- valuation-input models and source contracts;
- DCF and sensitivity analysis;
- reverse DCF;
- bear, base, and bull scenarios driven by explicit operating assumptions;
- historical and, where justified, peer valuation context.

DCF arithmetic remains deterministic code. LLMs may explain explicit
assumptions, but must not secretly calculate valuations. Reverse DCF is a key
long-term question: what revenue growth, operating margin, FCF margin,
reinvestment, and terminal economics must hold for the current price to be
justified? Scenarios must differ because of stated operating assumptions, not
arbitrary percentage offsets.

## Phase 3.5 — Evals, Observability, Reliability, and Safety

Goal: demonstrate that the AI system can be measured, inspected, and hardened,
not merely orchestrated.

### Observability and prompt versioning

Consider **Langfuse** or a suitable alternative once there are enough model and
retrieval calls to inspect. It should trace research runs, model calls,
latency, token usage, cost, prompt version, retrieved evidence, outputs, and
failures without coupling business logic to one vendor.

Prompts should become explicitly versioned in files or a later prompt-management
system so changes can be evaluated rather than judged only subjectively.

```text
Research Run: ASML
├── Financial data retrieval
├── Metric calculations
├── Filing retrieval
├── Business Analyst
├── Financial Quality Analyst
├── Moat Analyst
├── Bear Analyst
└── Synthesis
```

### Evaluation dataset and checks

Create a small, manually understandable evaluation set spanning representative
companies and edge cases: technology, semiconductors, high-margin software,
capital-intensive and consumer businesses, unusual fiscal years, and difficult
financial data.

Deterministic evaluations include calculation correctness, source merging,
citation preservation, schema validation, retrieval precision, and protection
against cross-period or cross-currency mixing.

LLM/semantic evaluations include groundedness, citation correctness,
unsupported-claim rate, business-analysis specificity, company-specific bear
cases, and evidence coverage. LLM-as-judge may help with subjective dimensions
only after its behaviour is compared with manual reviews; deterministic checks
remain preferred where possible.

### Safety and error monitoring

Treat retrieved filing text as untrusted data. Add adversarial tests for prompt
injection, source-boundary violations, malformed documents, inconsistent
currency or periods, scale mismatches, missing denominators, and malformed
provider data. Preserve the distinction between research findings, valuation
assumptions, and investment conclusions.

Introduce **Sentry** or similar error monitoring once a persistent API or
deployed service exists, to observe provider outages, parsing/database errors,
failed research runs, and API exceptions.

## Phase 4 — Research Persistence and Product Surface

Goal: turn individual executions into a reusable research workspace.

Potential persisted entities:

```text
companies
financial_statements
financial_metrics
filings
filing_chunks
research_runs
analyst_outputs
sources
evaluations
watchlists
```

Potential capabilities are saved reports, historical-run comparison, changed
assumption inspection, watchlists, portfolio research, and company comparison.
PostgreSQL becomes central here if persistence did not already require it in
the retrieval phase.

## Phase 4.5 — MCP and External Research Tools

Add **MCP** only after stable internal capabilities are worth exposing. The
domain and service layers must remain usable without MCP.

Potential tools include:

```text
get_company_profile
get_financial_statements
get_financial_metrics
get_latest_filing
search_filings
calculate_dcf
calculate_reverse_dcf
run_equity_research
```

These tools could serve external AI agents, local agent systems, Hermes Agent,
or other MCP-capable clients.

## Phase 5 — Web Product and Productionization

Only begin after the research engine, data layer, and evaluations are stable.

### Product surface

Potential UI capabilities: ticker search, research execution, Financial Quality
views, valuation scenarios, analyst sections, source inspection, report
history, watchlists, and portfolio views. The UI visualizes existing domain
capabilities; it does not define their architecture.

Add authentication only once user-specific persisted research, watchlists, or
portfolio data exists. A usage/pricing gate is optional and exists to learn
SaaS cost/quota architecture, not to force a commercial product.

### Delivery and operations

Expand GitHub Actions as requirements justify it:

```text
Pull Request / Push
        ↓
Ruff → mypy → pytest → integration tests
        ↓
evaluation smoke tests → Docker build
```

Keep expensive LLM evaluations separate from cheap unit-test CI. Later,
deployment can build an artifact/container, deploy, and run health checks.
Choose a cloud vendor only when deployment requirements make that decision
useful.

Potential production health and metrics include `GET /health`, `GET /ready`,
research-run success rate, latency, provider/model/retrieval failures, token
usage, and cost.

## AI Engineering Skill Coverage

| Capability | Project application and problem solved |
|---|---|
| CLI AI application | V0 ticker-to-report research workflow |
| Structured outputs | Pydantic analyst models keep LLM results validated |
| Tool/API integration | Financial providers supply normalized input data |
| Deterministic computation | Metrics and valuation keep arithmetic reproducible |
| Multi-agent workflows | Analysts are added only for distinct evidence boundaries |
| RAG | Filing retrieval supplies precise primary-source evidence |
| Embeddings | Semantic filing search once keyword lookup is insufficient |
| Vector DB | pgvector keeps filing vectors with relational metadata |
| FastAPI | Reusable research/retrieval service when a real API is needed |
| PostgreSQL | Filing, research-run, source, and evaluation persistence |
| Docker | Reproducible API/database environment with multiple services |
| Observability | Langfuse-style traces make model/retrieval behaviour inspectable |
| Evals | Groundedness, citation, and research-quality evaluation suite |
| LLM-as-judge | Measured qualitative evaluation alongside manual review |
| Safety | Prompt-injection and evidence-boundary testing for untrusted filings |
| Error monitoring | Sentry-style visibility for persistent/deployed failures |
| MCP | Stable research capabilities exposed as reusable external tools |
| Web product | Research UI after the underlying engine is reliable |
| Auth | Saved user research and watchlists once user state exists |
| CI/CD | GitHub Actions and later deployment checks |

## Anti-Overengineering Rules

- Do not introduce FastAPI before an API boundary is useful.
- Do not introduce PostgreSQL before persistence warrants it.
- Do not introduce pgvector before document retrieval exists.
- Do not introduce Docker until multiple services or deployment requirements
  exist.
- Do not add agents without a distinct responsibility and evidence boundary.
- Do not add LangGraph merely because multiple LLM calls exist.
- Do not add MCP until useful internal capabilities are stable.
- Do not add authentication before user-specific persisted state exists.
- Do not build a web UI before the research engine is reliable.
- Do not allow learning goals to override good architecture.

## Engineering Guardrails

- LLMs interpret supplied evidence; deterministic code performs reliable
  calculations.
- Financial calculations remain deterministic Python functions with tests.
- Missing data, incompatible units, and incompatible periods are explicit
  errors or missing-value states, never silent fallbacks.
- Facts, calculations, assumptions, and LLM interpretations remain
  distinguishable and traceable.
