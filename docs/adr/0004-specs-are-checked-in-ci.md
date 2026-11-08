# 0004. Specs are checked in CI, and drift is checked by code first and a local model second

- Status: accepted
- Date: 2026-11-08

## Context

A spec that nobody checks drifts from the code, and a coding agent that trusts a stale spec, or ignores a fresh one, breaks
the contract silently. A reviewer cannot be expected to notice that a threshold changed in the code but not in the spec.

## Decision

Behaviour is specified in `openspec/specs/<capability>/spec.md`, as requirements with scenarios. CI runs two checks: the
specs validate, and a pull request that changes code also changes the spec of what it touches (a change to the docs does not
count, nor does a whitespace-only edit), or carries the `no-spec` label, which only a person sets. `openspec/code-map.json`
ties code and tests to capabilities. The checks that decide are deterministic: no model, no secret, no cost. A local model
may add advice: every finding must quote the spec and the code, the program drops a finding whose quotes it cannot find, and
a model that is unavailable never blocks anything. The model never edits a spec or the code.

## Consequences

A behaviour change cannot reach `main` without its spec being touched or its claim of "no behaviour change" being
read by a person. The code map needs upkeep; the review warns about a file in no entry. A local git hook is a convenience
that can be skipped; CI is the rule.

## Alternatives considered

A model as the judge in CI: needs a secret or a model download on every run, and its mistakes would block pull requests.
Checking only that a spec file changed: whitespace edits satisfy it, so they are excluded. No check, and review by eye:
what the drift would cost is paid later, by a person who does not know which of the code or the spec is right.
