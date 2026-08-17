# Project principles

This is both a production-quality portfolio project and a learning project.

## Development rules

- Prefer simple implementations over abstractions.
- Do not introduce frameworks or dependencies unless required.
- Do not implement functionality outside the current task.
- Keep changes small and reviewable.
- Avoid files larger than ~300 lines when reasonable.
- Do not create abstractions for hypothetical future requirements.
- Financial calculations must be deterministic Python functions.
- LLMs must not perform arithmetic that can be performed in code.
- All financial calculations require unit tests.
- Use Pydantic models at system boundaries.
- Do not silently handle missing financial data.
- Do not refactor unrelated code during feature tasks.

## Agent behavior

Before implementing a non-trivial task:
1. inspect relevant code,
2. state the implementation approach,
3. list files that will change.

After implementing:
1. run tests,
2. summarize the diff,
3. explain any important design decisions,
4. mention remaining limitations.

If a requested task would require a significant architectural change,
stop and explain the tradeoff instead of implementing it automatically.