# 0006. Python, with a pure functional core in hexagonal layers

- Status: accepted
- Date: 2026-11-08

## Context

The factory is a long-running orchestration of agents, GitHub and people. Its workflow logic (which phase comes next,
what a gate accepts, when a loop gives up) is the part that matters most and the part that must be correct. The
workflow engine (Temporal) requires workflow code to be deterministic. Contributors must be able to understand and test
each part alone.

## Decision

- Python 3.13, `uv`, `ruff` (all rules), `pyright` in strict mode, `pytest` and `hypothesis`.
- The domain is a pure functional core: immutable data (`frozen`, `slots`), sum types, `match`, and decision functions
  `decide(state, event) -> (state, commands)` with no I/O. It imports the standard library only.
- Hexagonal layers, from the inside out: `domain`, `ports` (protocols), `application` (use cases as functions over
  ports), `adapters` (Temporal, GitHub, Claude, web, storage), `entrypoints` (composition roots). `import-linter`
  enforces in CI that dependencies point inwards, that the domain stays standard-library only, and that adapters do not
  know each other.
- Dependencies are passed as arguments (partial application or small closures): no DI framework, no globals.
- Pydantic stays at the edges (HTTP, configuration, external payloads), never in the domain.
- Tests in layers: pure property tests on the domain, use cases against in-memory fake ports, contract tests that both
  the fake and the real adapter pass, and workflow tests on Temporal's time-skipping server plus replay of recorded
  histories.

## Consequences

- The workflow is a thin interpreter of the pure `decide`: determinism comes from the design, and the pipeline can be
  tested exhaustively without Temporal, GitHub or a model.
- More files and indirection than a script; the layering rules are checked, so they do not erode.

## Alternatives considered

- **Logic inside Temporal workflows**: less code, but testable only through the engine and coupled to its SDK.
- **An effect-system library everywhere**: maximum purity, a steep learning curve for contributors, little gain here.
