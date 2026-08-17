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

🚧 **V0 development starting**

Initial focus:

1. Project setup
2. Core domain models
3. Financial data provider abstraction
4. Deterministic financial metrics
5. Minimal LLM analysis workflow
6. End-to-end research report

## Long-Term Ideas

Possible later extensions include:

- Multiple financial data providers
- SEC EDGAR and investor-relations filing ingestion
- Dedicated moat, market, valuation, and risk agents
- DCF valuation
- Reverse DCF
- Bear / Base / Bull scenarios
- Historical valuation analysis
- Source provenance and citations
- MCP tools
- Research database
- Web interface
- Portfolio and watchlist analysis

These features are intentionally **out of scope for the initial V0**.

## Disclaimer

This project is intended for research, education, and software engineering purposes.

It does not provide financial advice or guarantee the accuracy of investment conclusions.