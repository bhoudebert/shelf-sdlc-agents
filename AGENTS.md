# Working in this repository

Read this before changing anything. It applies to people and to coding agents
(Claude Code, Codex, Gemini CLI, GitHub Copilot, others) alike: this file is the
single source of the rules, and `CLAUDE.md`, `GEMINI.md` and
`.github/copilot-instructions.md` only point here.

## What this is

Shelf SDLC Agents: A shelf of agents covering the software development lifecycle.

`README.md` explains the product, `CONTRIBUTING.md` how to contribute,
`docs/ENGINEERING.md` how it is built, `docs/EVOLVING.md` the path every change
follows from idea to release, and `docs/adr/` why it is shaped this way.
Behaviour is specified in `openspec/specs/<capability>/spec.md`
(requirements with scenarios); `openspec/README.md` explains how to change a spec.

## Rules

1. **Branch, then pull request.** Never commit to `main`. Branch names:
   `feat/...`, `fix/...`, `docs/...`, `build/...`, `ci/...`, `chore/...`.
2. **Conventional Commits, strictly.** `<type>(<scope>): <subject>` with the
   types `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`,
   `chore`, `style`, `revert`; kebab-case scope; imperative subject; header at
   most 100 characters, body lines at most 120; one concern per commit. The
   commit-msg hook and CI reject anything else (`CONTRIBUTING.md`, "Commits").
3. **Spec first when behaviour changes.** Update or add the requirement in
   `openspec/specs/...` in the same pull request, committed before the code. CI
   fails a pull request that changes code without touching the spec of what it
   changes; the `no-spec` label (or a `No-Spec: <reason>` line in a commit, read
   by the local hook only) is for changes with no behaviour change. **Deciding,
   for an agent:** would a user or the operator notice (a number, a message, a
   rule, an answer, a setting)? Did a test need a new case or a new expected
   value? If either, behaviour changed: update the requirement, do not use
   `no-spec`. When unsure, update the spec.
4. **Tests with the code.** Deterministic logic gets unit tests; tests never call
   a paid or external service for real.
5. **Quality gate before pushing:** `npm run quality` must pass.
6. **Docs with the change.** The README when the overview changes,
   `docs/ENGINEERING.md` when the architecture changes, `ROADMAP.md` when an
   idea is done or added, a decision record in `docs/adr/` for a significant
   architectural choice (a record is superseded, never rewritten).
7. **Pull request** with the template: summary, decision and spec, what was
   verified, what was not. The maintainer reviews and merges.
8. **No attribution trailers** or generated-by footers in commits, pull request
   descriptions or comments.

## Starting and delivering a change

Before the first edit of any task, **including running a tool that writes files** (a generator, a formatter, an upgrade
command), look at where you are:

1. Run `git branch --show-current`.
2. **On `main`**: do not edit there. Update it (`git pull --ff-only`), create a branch from it named
   `<type>/<short-topic>` (`feat/`, `fix/`, `docs/`, `chore/`, ...), tell the user its name, and go on. Do not ask first:
   starting a branch is part of the task. Uncommitted changes you find come along to the new branch; say so.
3. **On another branch**: ask once, "You are on `<branch>`: is this the right place for this change, or should I start a new
   branch from `main`?", and keep the answer for the whole task. Do not ask when the user already said where to
   work, or when the change plainly continues the pull request of this branch.

When the work is done and the gate passes: commit (one concern per commit), push **the branch**, never `main`, open the pull
request with the template (`gh pr create`), report its URL, and stop. Never merge it.
**Stage only the files of your task**: `git add <paths>`, never `git add -A` or `git commit -a`. Anything else in the working
tree is not yours: leave it, and mention it to the user.
The `project-foundation` skill is committed in this repository (`.agents/skills/`, `.claude/skills/`, `skills-lock.json`), so
every contributor and agent has the same rules and tools. `npx skills update` changes those files: that is a change of its own,
on its own branch (`chore/update-project-foundation`) and pull request, never mixed into another one.

Git refuses a commit on `main` and a push to it (`ALLOW_DEFAULT_BRANCH=1` for the rare exception), but that is a backstop: by
then the edit is already done. The check above comes first.

## How an agent works here

- **Smallest change that solves the request.** Do not refactor, rename or
  "improve" what was not asked. Say what you noticed and let the owner decide.
- **Verify, then claim.** Run the gate and the relevant tests; report what
  passed, what failed and what you did not run, with the output. Never write
  "done" for something unverified.
- **Ask before anything hard to reverse or visible to others**: pushing to
  `main`, force-pushing, merging, deleting, publishing, spending money, changing
  settings. Pushing your own branch and opening its pull request is part of the
  task (see above), not something to ask about. Approval for one action is not
  approval for the next.
- **Secrets stay secret.** Never read, print, log or commit `.env`, keys or
  tokens. Tests run without real credentials.
- **Hooks and CI are the rules, not obstacles.** Never skip a hook
  (`--no-verify`) or weaken a check to get green; fix the cause, or say why a
  rule should change and propose that in its own pull request.
- **Do not merge your own pull request**, and do not rewrite shared history.
- **Leave a trail.** When a choice was non-obvious, put the reason in the
  commit body or a decision record, not only in a chat.

## Code conventions

<!-- Fill in the conventions that are not obvious from the code: layering, error handling,
     naming, where things live, what must never be done. Keep it to what a newcomer would get wrong. -->

- Language and tools: Node.js / TypeScript. Code under `src/`, tests under `test/`.

## Useful commands

```
npm install      # set up the project
npm run quality    # the gate
npm test       # tests only
npm run lint       # lint
npm run format     # format
sh scripts/setup-hooks.sh   # install the git hooks (once per clone)
nix develop              # the toolchains of every component (or direnv allow)
```
```
node scripts/spec-review.ts --base origin/main --head HEAD   # check your change against the specs
node scripts/spec-review.ts --audit                                       # check the whole repository
```
