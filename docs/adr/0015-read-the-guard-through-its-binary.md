# 0015. Read the guard through its binary

- Status: proposed
- Date: 2026-11-14

## Context

Warden (decision 0014) writes a hash-chained audit log of every decision about every agent. Operators need to see what it
saw without opening a shell in the worker: how many calls, how many it would have stopped, whether the log was tampered
with. The admin page and `shelf-diagnose` are the two places that would show it.

The Python side could read the log files itself: they are JSON lines in a volume. It would then have to know the record
format, the hash that chains the lines, the rule that a decision audit mode let through counts as "would have stopped", and
the layout of the daily files. Every change to any of these would be a change in two components, in two languages, that
are released separately.

## Decision

`src/` reads the guard only by running the `warden` binary: `warden report --json` for the counts and `warden audit
verify` for the chain, behind a `GuardReader` port with one adapter. The web service mounts the state volume read-only,
so the page can report on the log and cannot change it. The report is a stable, small JSON object (`records`, `calls`,
`would_stop`, `by_category`, `by_decision`, `redactions`); the binary owns what a number means.

A page that cannot reach the guard says so in one sentence and still loads: a missing guard is information, not an error.

## Consequences

- The record format, the chain and the counting rules stay in Rust, with their tests.
- The web service needs the binary in its image (it is in the same image as the worker) and the volume mounted read-only.
- Each page load runs two short processes (about ten milliseconds each). If the admin page were polled, a cache would be
  needed; it is not.
- A version of the binary whose `report --json` changes shape makes the section say it does not understand the guard, not
  break the page.

## Alternatives considered

- **Parse the JSON lines in Python.** Fewer processes, but two parsers of one format and two implementations of "would have
  stopped".
- **Warden serves HTTP.** A second long-running service to deploy, secure and keep up, for a number read a few times a day.
