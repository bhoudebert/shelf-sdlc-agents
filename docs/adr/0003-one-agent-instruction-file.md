# 0003. One agent instruction file for every agent

- Status: accepted
- Date: 2026-11-08

## Context

Coding agents read different files: Codex and GitHub Copilot's agents read `AGENTS.md`, Claude Code reads `CLAUDE.md`,
Gemini CLI reads `GEMINI.md`, and Copilot's code review and chat read `.github/copilot-instructions.md`. Four copies of the
rules drift apart, and an agent that follows a stale copy breaks the workflow.

## Decision

`AGENTS.md` is the single source of the working rules. `CLAUDE.md` imports it (`@AGENTS.md`), `GEMINI.md` imports it
(`@./AGENTS.md`), and `.github/copilot-instructions.md` is a short digest that points to it, because Copilot does not
expand file references. Anything specific to one tool goes below the import in that tool's file. The rules that must hold are
enforced by git hooks and CI, which no agent can opt out of, never by an agent-specific setting alone.

## Consequences

One place to edit. A rule change touches `AGENTS.md` and, when it is one of the short rules, the Copilot digest. Keep
`AGENTS.md` small (Codex stops reading project instructions at 32 KiB by default) and keep the Copilot file under about
4,000 characters (code review reads only the start).

## Alternatives considered

Symlinks between the files: break on Windows and in some archives. Copies kept in sync by hand: drift. A generator: more
machinery than one import line per tool.
