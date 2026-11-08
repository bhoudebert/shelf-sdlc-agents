You name pull requests the way this repository names them.

Write the title of the pull request for this work. Follow the repository's own convention, which you must find, not guess:
read `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` and any release or commit configuration (commitlint, release-please,
changelog rules), look for a pull request title check under `.github/workflows/` and in the pull request template, and
read the style of the recent history with `git log --oneline -30` on the base branch. If the repository uses
Conventional Commits, choose the right type and scope from what this work actually does (read the documents of the work
and `git diff <base>...HEAD`). The title becomes the squash commit on the base branch, so it must pass every check.

Answer with the title alone, on the last line, with no quotes and no explanation. Keep it under 72 characters unless the
repository allows more.
