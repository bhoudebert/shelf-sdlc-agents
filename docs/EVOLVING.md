# How Shelf SDLC Agents evolves

Every change goes through the same path, whoever makes it, a person or a coding agent. The path exists so that each change
is designed before it is coded, specified before it is tested, and explained before it is released.

```
idea ─▶ decision ─▶ spec ─▶ code + tests ─▶ docs ─▶ PR ─▶ release
        (ADR)      (openspec)                     (review) (automatic)
```

## 1. Idea

Ideas live in `ROADMAP.md` or an issue. Before building, talk it through: who is it for, when is it used, what does the
user do, what does the system do. A feature that cannot be described in those terms is not ready.

## 2. Decision: an ADR when the shape of the system changes

A new data store, a new execution path, a new dependency or service, a rule that cuts across features, a choice between real
alternatives: write a record in `docs/adr/` from `template.md`, with the alternatives that lost. Small changes inside an
existing shape need no record. Read the existing records before changing what they cover; an accepted record is
superseded by a new one, never rewritten.

## 3. Spec: what the system shall do

Update or add `openspec/specs/<capability>/spec.md`: requirements written as SHALL statements, each with at least one
scenario (WHEN / THEN). A new capability gets its own folder and a line in `openspec/README.md`. The spec is written first
and reviewed with the code in the same pull request.

CI checks it: the specs must validate, and a pull request that changes code must also change the spec of what it touches.
**A change to the docs does not count as a spec change, nor does an edit that only moves whitespace.** A change with no
behaviour change says so: the `no-spec` label on the pull request (the only justification CI reads), or a
`No-Spec: <reason>` line in a commit (read by the local hook only, because whoever writes a commit can write that line).

Deciding: would a user notice? Did a test need a new case? Then the behaviour changed and the spec changes with it. When
unsure, update the spec. `docs/adr/0004-...` and the spec-review section below explain the checks.

### Checking a change against the specs

```bash
node scripts/spec-review.ts --base origin/main --head HEAD   # deterministic checks, no model
node scripts/spec-review.ts --audit                                        # the whole repository, to clean up
```

It writes `.spec-review/report.json` and `report.md` and changes nothing else. The deterministic checks decide and are what
CI runs, with no model and no secret. An optional local model (Ollama, or any OpenAI-compatible server) can add a review
whose every finding must quote the spec and the code: the program looks for each quote in the file and drops the finding
when it is not there. A model never edits anything and never blocks on its own failure.

## 4. Code and tests

- **One implementation, every entry point.** Logic lives in plain modules; command lines, servers and agents are thin entry
  points over it.
- **Rules in code.** Anything that must always hold is enforced in the code, never only in a prompt or a document.
- **Tests with the code.** Deterministic logic gets unit tests. Tests never call a paid or external service for real.
  `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest` must pass.
- **Verify for real** where it matters, and say what was and was not verified.

## 5. Docs

The README when the overview changes; `docs/ENGINEERING.md` when the architecture changes; `AGENTS.md` or
`CONTRIBUTING.md` when the way of working changes; `ROADMAP.md`: remove what is done, add what was learnt.

## 6. Pull request

Conventional Commits, one concern per commit, in the order of this path (`docs(adr)`, `docs(spec)`, `feat`, `test`,
`docs`). The pull request title is a Conventional Commit too: it becomes the commit on `main`. The template's checklist
mirrors this document. The maintainer reviews and merges.

## 7. Release

Nothing to do by hand. release-please turns `feat` and `fix` commits on `main` into a release pull request with the version
and the changelog; merging it tags the release and publishes the notes.
