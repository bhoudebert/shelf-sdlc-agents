# 0002. Conventional Commits, squash merges, automated releases

- Status: accepted
- Date: 2026-11-08

## Context

Changes arrive through pull requests from people and coding agents. Versions and changelogs should follow from the
history without manual work.

## Decision

Commit messages and pull request titles follow Conventional Commits with a fixed type list, enforced by a commit-msg hook,
a script in CI and a pull request title check. Pull requests are squash-merged, so the title becomes the commit on
`main`. release-please reads `main` and maintains a release pull request with the version bump and the
changelog; merging it tags the release. `main` is protected: a pull request and green required checks, linear history, no force
push.

## Consequences

A release costs one merge. A non-conventional title or message is rejected early. Contributors must learn the convention;
`CONTRIBUTING.md` and `AGENTS.md` document it. The hooks are tool-neutral shell scripts, so they behave the same for every
coding agent and editor.

## Alternatives considered

Manual tagging and changelog: forgotten in practice. Merge commits: noisier history, and release automation reads branch
commits inconsistently. A commit linter that needs a language runtime: not available in every stack of the repository.
