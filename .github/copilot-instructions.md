# Copilot instructions for Shelf SDLC Agents

The full rules are in `AGENTS.md` (read it). This is the short form, for tools that
read only this file, such as code review; it must stay under about 4,000 characters.

- Stack: Python. Code in `src/shelf/`, tests in `tests/`. Gate: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest`.
- Never commit to `main`. Before the first edit run `git branch --show-current`: on `main`, create a branch (`feat/`, `fix/`, `docs/`, `chore/`) first without asking; on another branch, ask once if it is the right place. Then commit, push the branch, open a pull request, never merge it.
- Commits and pull request titles follow Conventional Commits: `type(scope): subject`, types `feat fix perf refactor docs test build ci chore style revert`, imperative subject, header at most 100 characters, one concern per commit.
- Behaviour changes update the spec first (`openspec/specs/<capability>/spec.md`). The `no-spec` label is only for changes with no behaviour change: a test needing a new case or a changed number or message means the behaviour changed.
- Stage only the files of your task (`git add <paths>`), never `git add -A` or `git commit -a`.
- Tests go with the code; they never call a paid or external service for real.
- Update the docs the change makes stale (README, `docs/ENGINEERING.md`, `ROADMAP.md`).
- Do not read, print or commit secrets or `.env`. Do not skip hooks or weaken checks.
- Review: flag a behaviour change with no test or spec, a skipped check, a secret, an unrelated refactor, a missing decision record for an architectural choice.
- No attribution trailers or generated-by footers in commits or pull request text.
- Say what was verified and what was not.
