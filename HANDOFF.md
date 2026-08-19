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

## Latest Completed Slice

Commit `0f37ef7` completed the focused duplication cleanup:

- shared, order-preserving source-reference merging with conflict detection;
- shared Groq settings, request, transport, response extraction, and JSON
  parsing mechanics;
- direct tests for the shared provenance and Groq behavior.

Analyst prompts, output schemas, error types, and evidence contracts remain
explicit and analyst-specific.

## Current / Next Slice

No implementation slice is currently active. The next action is to select and
review one bounded Phase 2 filing-ingestion slice before changing code.

### Goal

Choose the smallest independently testable step toward discovering and
retrieving approved primary-source company filings while retaining document
metadata and provenance.

### Explicitly Out of Scope

- implementing several filing sources or a complete ingestion pipeline at once;
- RAG, embeddings, pgvector, PostgreSQL, FastAPI, or Docker;
- adding a new analyst before it has a distinct responsibility and evidence
  boundary;
- valuation, persistence, web UI, or other later roadmap phases;
- unrelated application refactoring.

## Relevant Files

- `AGENTS.md` — development and collaboration contract
- `README.md` — product purpose and high-level architecture
- `ROADMAP.md` — sequencing and Phase 2 direction
- `src/equity_research_agent/data/providers/` — current provider boundary and
  Alpha Vantage implementation
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
- Add a dedicated analyst only when its responsibility, evidence boundary, or
  evaluation criteria are meaningfully distinct.
- Extract shared infrastructure only after duplication is demonstrated. Keep
  analyst-specific prompts, output models, and evidence contracts explicit
  where they encode different semantics.
- Provider-specific adapters sit behind protocols where useful. Do not design a
  hypothetical universal provider layer before a real second implementation
  demonstrates what is shared.

## Verification Status

Freshly verified locally on 2026-08-19 against the current worktree:

- `uv run pytest`: 311 passed
- `uv run ruff check`: passed
- `uv run mypy`: passed for configured `src`
- `git diff --check`: passed

No live provider or model calls were made. A fresh agent should rerun checks
relevant to any new change. V0 was manually CLI-validated before the recent
Financial Quality and refactor slices. Live CLI runs are deliberately reserved
for bug investigation or for validating several accumulated features because
provider test runs are limited.

## Known Limitations

- Alpha Vantage is the only financial-data provider currently implemented.
- Groq is the only LLM provider currently implemented. The workflow protocols,
  prompts, schemas, and provenance rules are largely provider-neutral, but a
  second provider still requires explicit adapters.
- The system uses annual structured financial data; it has no filing discovery,
  document parsing, filing search, or RAG capability yet.
- Valuation, persistence, an API, observability, and a web product remain future
  roadmap work.
- `asml-report.md` is an untracked local report and should not be changed or
  committed without explicit direction.

## Open Questions

- Which primary filing source and document type should define the first bounded
  ingestion slice?
- Should that first slice establish only domain/provenance models, or also one
  minimal discovery/retrieval adapter? Decide during review before implementation.

## Next Expected Steps

1. Review Phase 2 and select one bounded filing-ingestion slice.
2. Inspect only the provider, provenance, and tests relevant to that selection.
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
