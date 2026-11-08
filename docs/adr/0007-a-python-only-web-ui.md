# 0007. Serve the web UI from Python, with HTMX and server-sent events

- Status: accepted
- Date: 2026-11-08

## Context

The UI is the product: sign in, pick a repository, start work at any step, follow a board, decide at gates. It must be
easy to self-host and easy for contributors to change. A second language and a build chain for a board and some forms
would double the surface to maintain.

## Decision

The web adapter is FastAPI with server-rendered Jinja templates, HTMX for interaction and server-sent events for live
updates. There is no Node toolchain in the project's runtime, build or development shell. Tools that happen to be
written in JavaScript may run in CI only (OpenSpec validation).

## Consequences

- One language, one build, one image.
- Rich client-side interaction is harder; the board and forms do not need it.

## Alternatives considered

- **A single-page application**: more freedom, a second language, a build chain and a second thing to secure and ship.
