# Architecture decision records

Why the system is shaped the way it is. Behaviour is specified in `openspec/specs/`; these records hold the reasons. New records use
`template.md` and the next free number; an accepted record is superseded, not rewritten.

| #                                                                | Decision                                                  | Status   |
| ---------------------------------------------------------------- | --------------------------------------------------------- | -------- |
| [0001](0001-record-architecture-decisions.md)                    | Record architecture decisions                             | accepted |
| [0002](0002-conventional-commits-and-automated-releases.md)      | Conventional Commits, squash merges, automated releases   | accepted |
| [0003](0003-one-agent-instruction-file.md)                       | One agent instruction file for every agent                | accepted |
| [0004](0004-specs-are-checked-in-ci.md)                          | Specs are checked in CI, drift by code first, a model second | accepted |
| [0016](0016-results-land-where-the-repository-keeps-them.md)      | Let the results of a run land where the repository keeps them | proposed |
| [0017](0017-let-agents-read-the-web-and-keep-downloads-limited.md) | Let agents read the web, and keep downloads limited | proposed |
