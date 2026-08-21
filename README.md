# AI Equity Research Analyst

AI-assisted equity research system that combines **deterministic financial analysis** with **LLM-based qualitative research**.

The goal is to build a transparent and extensible research workflow for analyzing publicly traded companies without relying on an LLM for calculations that can be performed reliably in code.

## Project Goal

Given a company ticker such as:

```text
ASML
```

the system should eventually produce a structured equity research report covering areas such as:

- Business model
- Revenue structure
- Financial quality
- Growth drivers
- Competitive moat
- Risks and bear case
- Valuation
- Investment thesis
- Thesis killers
- Open research questions

## Core Design Principle

The system deliberately separates **deterministic computation** from **LLM reasoning**.

### Deterministic Layer

Python code will be responsible for financial calculations such as:

- Revenue CAGR
- EPS CAGR
- Free Cash Flow
- Gross Margin
- Operating Margin
- FCF Margin
- ROIC
- Net Debt
- Share Count Growth
- Valuation multiples

These calculations should be reproducible, testable, and independent of an LLM.

### LLM Analysis Layer

LLMs will be used for tasks that require interpretation and reasoning, including:

- Understanding the business model
- Identifying growth drivers
- Evaluating competitive advantages
- Analyzing risks
- Constructing a bear case
- Identifying thesis killers
- Synthesizing the final investment thesis

## V0 — Walking Skeleton

The first milestone is intentionally small.

```text
Ticker
  ↓
Company & Financial Data
  ↓
Deterministic Financial Metrics
  ↓
Business Analysis
  ↓
Bear Case
  ↓
LLM Synthesis
  ↓
Structured Markdown Report
```

The goal of V0 is not to build a complete investment platform.

It is to create one clean, understandable, end-to-end research workflow.

## Planned Architecture

```text
src/
├── models/
├── data/
│   └── providers/
├── analytics/
├── agents/
├── workflows/
└── reports/

tests/
```

The architecture will evolve incrementally as the project develops.

Abstractions and frameworks should only be introduced when they solve an actual problem.

## Development Principles

- Keep changes small and reviewable.
- Prefer simple implementations over premature abstractions.
- Financial calculations must be deterministic.
- Important calculations require unit tests.
- LLM outputs should use structured schemas where appropriate.
- Missing data must be handled explicitly.
- Facts, calculated values, assumptions, and LLM interpretations should remain distinguishable.
- Data sources should be traceable.
- Avoid unnecessary dependencies and framework complexity.
- Build the system incrementally rather than generating the entire application at once.

## Current Status

✅ **V0 walking skeleton complete**

The CLI retrieves Alpha Vantage company and annual financial data, calculates
deterministic metrics, runs the Business, Bear, and Financial Quality Analysts
plus final Synthesis through Groq, and prints a sourced Markdown research
report. Financial-risk and Financial Quality findings retain source provenance
through the workflow.

Filing ingestion is wired into that same workflow: for each ticker, the CLI
resolves a CIK (preferring one Alpha Vantage already supplied, falling back to
SEC EDGAR), fetches the issuer's latest 10-K or 20-F, sections it along the
filer's own linking index, selects the Risk Factors section, and runs the
Disclosed Risk Analyst on it. The report includes a "Disclosed Risks" section
sourced at the filing-section level; when any step in that chain is not
possible (no resolvable CIK, no annual report on file, or no uniquely
identified Risk Factors section), the report states the specific reason
instead of silently omitting the section or failing the whole run. When
available, the disclosed-risk analysis also feeds the final Research
Synthesis, so the investment thesis and risk summary can draw on
filing-disclosed risks alongside the Business, Bear, and Financial Quality
Analyses. See `HANDOFF.md` for current state.

## Running V0

Add the following keys to the local, git-ignored `.env` file:

```dotenv
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
GROQ_API_KEY=your_groq_key
EDGAR_CONTACT_USER_AGENT=Your Name your_email@example.com
```

`EDGAR_CONTACT_USER_AGENT` is the contact string SEC EDGAR requires on every
request; it is not a secret and can be your name and email address.

Load them into your shell, then provide one ticker:

```zsh
set -a
source .env
set +a
uv run equity-research-agent ASML
```

The Markdown report is printed to standard output. Redirect it from the shell if
you want to save it to a file.

## Long-Term Ideas

Possible later extensions include:

- Multiple financial data providers
- SEC EDGAR and investor-relations filing ingestion
- Dedicated moat, market, valuation, and risk agents
- DCF valuation
- Reverse DCF
- Bear / Base / Bull scenarios
- Historical valuation analysis
- MCP tools
- Research database
- Web interface
- Portfolio and watchlist analysis

These features are intentionally **out of scope for the initial V0**.

## Disclaimer

This project is intended for research, education, and software engineering purposes.

It does not provide financial advice or guarantee the accuracy of investment conclusions.
