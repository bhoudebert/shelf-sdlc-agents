# Specifications

`specs/<capability>/spec.md` describes what the system does today, as requirements with scenarios. A spec is the
contract: the code follows it, and a change to the behaviour changes the spec first.

## Which way to change a spec

**Default: edit `specs/` directly**, in the same pull request as the code. The spec commit comes first
(`docs(spec): ...`), then the code and the tests. One pull request, reviewed together, nothing left to fold in later. CI
validates the specs and asks for a spec change with any change under `src/shelf/` (ADR 0004).

**A change proposal (`changes/<id>/`)** only when one of these holds:

- the feature spans several pull requests, so `specs/` must not describe it until it is all on `main`;
- the design should be agreed before any code: a first pull request holds only the proposal.

A proposal holds `proposal.md` (why and what), `tasks.md` (the steps), optionally `design.md`, and delta specs under
`changes/<id>/specs/<capability>/spec.md` (`## ADDED`, `## MODIFIED`, `## REMOVED` or `## RENAMED Requirements`).
Archive it in the last pull request of the feature, not in one of its own: `openspec archive <id>`.

`openspec validate --all` checks the specs and any open proposal; CI runs it.

## Writing a requirement

Copy `spec-template.md`. A requirement states one thing the system SHALL do, and has at least one scenario:

```
### Requirement: A short name

The system SHALL warn the rider when the crosswind is above 50 km/h.

#### Scenario: Strong wind

- **WHEN** the forecast crosswind is 60 km/h
- **THEN** the itinerary carries a wind warning
```

## The code map

`code-map.json` ties code and test files to capabilities, so a change to a file is checked against the requirements it
concerns. Add a source file there when you add one; the review warns about a file that is in no entry and about a pattern
that matches nothing. Specs name behaviour, never source files.

## What is checked, and how

- **Pull request (CI):** the specs validate; a change under `src/shelf/` comes with a change to the spec of what it touches,
  or the `no-spec` label (a person's claim that the behaviour did not change). Deterministic, no model, no secret.
- **Push (local hook):** the same checks, and optionally a review by a local model (`SPEC_REVIEW_MODEL`, see
  `.env.example`) whose every finding must quote the spec and the code. It never edits anything and never blocks on its
  own failure.
- **A whole-repository audit:** `node scripts/spec-review.ts --audit` finds stale references and a stale code map.

## Capabilities

| Capability | Covers |
| ---------- | ------ |
| <!-- name --> | <!-- what it covers --> |
