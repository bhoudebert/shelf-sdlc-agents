# Engineering

How Shelf SDLC Agents is built. Keep this page true: update it in the same pull request as an architectural change.

## Overview

<!-- One paragraph and one diagram: what the parts are and how a request flows through them. -->

## Layout

```
src/    the code
test/   the tests
docs/       this page, the workflow (EVOLVING.md) and the decision records (adr/)
```

## Key decisions

The reasons live in [`docs/adr/`](adr/README.md). The ones that shape everything else:

- [0001](adr/0001-record-architecture-decisions.md) Record architecture decisions
- [0002](adr/0002-conventional-commits-and-automated-releases.md) Conventional Commits and automated releases
- [0003](adr/0003-one-agent-instruction-file.md) One agent instruction file for every agent

## Rules the code enforces

<!-- The rules that must always hold, and where each is enforced. A rule enforced only in a prompt or a document is a wish. -->

## Quality gate

`npm run quality` runs everything CI runs. The pull request checks are required on `main`.

## External services

<!-- Each service the software calls, how it is rate-limited, cached and what happens when it fails. -->
