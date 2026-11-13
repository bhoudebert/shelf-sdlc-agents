# Architecture decision records

Why the system is shaped the way it is. Behaviour is specified in `openspec/specs/`; these records hold the reasons. New records use
`template.md` and the next free number; an accepted record is superseded, not rewritten.

| #                                                                | Decision                                                  | Status   |
| ---------------------------------------------------------------- | --------------------------------------------------------- | -------- |
| [0001](0001-record-architecture-decisions.md)                    | Record architecture decisions                             | accepted |
| [0002](0002-conventional-commits-and-automated-releases.md)      | Conventional Commits, squash merges, automated releases   | accepted |
| [0003](0003-one-agent-instruction-file.md)                       | One agent instruction file for every agent                | accepted |
| [0004](0004-specs-are-checked-in-ci.md)                          | Specs are checked in CI, drift by code first, a model second | accepted |
| [0012](0012-run-each-agent-step-in-its-own-container.md)         | Run each agent step in its own container                  | proposed |
