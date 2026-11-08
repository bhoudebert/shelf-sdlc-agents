# 0005. License the project under Apache-2.0

- Status: accepted
- Date: 2026-11-08

## Context

The project is meant to be open source, self-hosted by others and extended by outside contributors. It will sit beside
tools that carry patents (agent runtimes, workflow engines), and companies will want to run it without a legal review.

## Decision

The project is licensed under Apache-2.0. The repository is built from concepts and written fresh: no code is copied
from another project.

## Consequences

- Companies can use, modify and host it, with an explicit patent grant.
- Contributions come in under the same licence (stated in `CONTRIBUTING.md`).
- Copyleft is not available as a protection against closed forks; we accept that.

## Alternatives considered

- **MIT**: simpler, but no patent grant.
- **AGPL-3.0**: protects against closed hosted forks, but discourages the companies and teams we want to reach.
