# 0016. Let the results of a run land where the repository keeps them

- Status: proposed
- Date: 2026-11-15

## Context

A run records its request, spec, design and plan in `docs/shelf/<work-id>/`. They are a log of the run. The lasting result,
a changed requirement or an architectural choice, does not reach the repository's own `openspec/specs/` or `docs/adr/`: the
architect is told to write a record "if the repository keeps them", and nothing mentions specs. A repository run by the
factory therefore loses its own source of truth, while a repository that follows the same conventions by hand (agentRide)
keeps it. Repositories also differ: some keep decisions elsewhere, some have no specs, some want no records.

## Decision

- The run's own files move to `.shelf/<work-id>/` and stay after the merge. `docs/shelf/<work-id>/` of earlier runs is still read.
- What lasts is written where the repository keeps it: requirements in its specs folder, decisions in its decisions folder.
- A repository may set the two folders, which results a run writes, and the strictness of the conflict check in a new
  `[results]` section of its existing `.shelf/config.toml` (`specs`, `decisions`, `write`, `conflicts`). The defaults are
  `openspec/specs`, `docs/adr`, both, `block`. The file's reader already refuses unknown keys and values.
- A missing folder is created, in the repository's own convention or the standard one, never skipped.
- The design reviewer compares a new record with every accepted one and refuses a contradiction that the request or the
  new record does not state. A superseded record changes only its status.

## Consequences

- A repository keeps its specs and decisions up to date as a by-product of the factory, which makes the spec-drift check pass.
- One more file a repository may carry, and one more thing the reviewers read. The conflict check costs tokens on a long
  decision history, and a model can miss a conflict: it is a review, not a guarantee.
- `documents_dir` changes, so a run in flight when this ships must keep the folder it started with (the path is decided once,
  at the start of the run, and kept with the work).
- `.shelf-context` (the read-only copies of other repositories) is a different folder and stays as it is.

## Alternatives considered

- Keep `docs/shelf/` and leave the lasting result to the agents' judgment: it is what happens now, and it does not happen.
- Delete the run's folder after the merge: the spec and the record hold what matters, but the run's history is lost, and the
  folder is cheap to keep.
- Hard-code the layout of `openspec/` and `docs/adr/`: simpler, wrong for every repository that differs.
