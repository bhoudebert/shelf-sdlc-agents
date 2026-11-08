# 0010. Access is closed by default

- Status: accepted
- Date: 2026-11-08

## Context

An instance with an empty access list let any GitHub account sign in. Whoever signs in can start agent work, which spends
the operator's model account and writes to repositories the App is installed on. A fresh install, or a typo in
`shelf.toml`, therefore exposed the operator's quota to the world. `/shelf` commands on pull requests were also accepted
from anyone with write association, whether or not the operator had listed them.

## Decision

Nobody is let in unless named: a listed user, an administrator, or a member of a listed organisation. An empty list lets
nobody in, and says so in the sign-in refusal, in the logs and in the install script. The same rule gates `/shelf`
commands from GitHub, by webhook and by poll.

## Consequences

A new operator must name themselves in `deploy/shelf.toml` before first use, which the install script and the docs say.
There is no accidental open instance. Letting everyone in is no longer possible, on purpose.

## Alternatives considered

A warning only, keeping the open default: the failure is silent and costly, so it lost. An explicit `open = true` switch:
no case for it yet, and it can be added later by a new record.
