<!-- Title: Conventional Commits, e.g. "feat(api): accept a time zone". The title becomes the commit on main. -->
<!-- The path every change follows: docs/EVOLVING.md -->

## Summary

<!-- What changes and why, in a few lines. -->

## Decision and spec

<!-- ADR added, or "none needed" (docs/adr/). Spec requirement added or changed (openspec/specs/...), or "no behaviour change" with the reason (then add the `no-spec` label: a reviewer reads that reason). -->

## Verified

<!-- What was run: uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest, a real run of the feature. State what was NOT verified. -->

## Checklist (docs/EVOLVING.md)

- [ ] ADR when the shape of the system changes
- [ ] Spec updated first when behaviour changes
- [ ] Tests with the code; `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest` passes
- [ ] Docs updated (README, `docs/ENGINEERING.md`, roadmap) where the change makes them stale
- [ ] Commits and PR title follow Conventional Commits
