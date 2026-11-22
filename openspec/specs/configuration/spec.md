# Configuration

## Purpose

Let the operator configure an instance and each repository configure itself, in TOML files that are checked strictly.

## Requirements

### Requirement: The operator's file is read again when it changes

The system SHALL read `shelf.toml` strictly at start, so that a mistake stops the program, and again whenever its inode, modification time or size changes, taking the new access list only when the file is valid; the mode is read at start only.

#### Scenario: A valid edit

- **WHEN** the file changes to a valid list of users
- **THEN** the next access decision uses the new list

#### Scenario: An invalid edit

- **WHEN** the file changes to something that cannot be parsed
- **THEN** the previous configuration is kept and the error is logged

### Requirement: The operator file sets the mode and the access list

The system SHALL read `mode` (local or server) and the `[access]` lists of organisations, users and administrators from the operator's file, treating an empty file as a local instance that nobody may sign in to.

#### Scenario: An empty file

- **WHEN** the operator file is empty
- **THEN** the instance is closed (nobody may sign in) and in local mode

#### Scenario: A restricted server

- **WHEN** the file sets server mode and lists organisations, users and administrators
- **THEN** those lists become the access rules and the mode is server

### Requirement: A repository configures itself

The system SHALL read from a repository's `.shelf/config.toml` the enabled entry points, base branch, checks, the loop policy and the roles, using defaults for what is missing.

#### Scenario: Defaults

- **WHEN** a repository has no file
- **THEN** every entry point is enabled, three rounds are allowed, the spec approval and the design review are on, work waits at a deadlock and no role restricts anyone

#### Scenario: Roles and policy

- **WHEN** the file lists roles and turns the design review off
- **THEN** the policy has no design review and the roles hold the listed logins

#### Scenario: Proceeding on deadlock

- **WHEN** the file sets `proceed_on_deadlock = true` in its policy
- **THEN** the policy lets work go on past a spec or design review that cannot settle, and without the key it does not

### Requirement: A repository says in its file where the results of a run go

The system SHALL read from a `[results]` section of a repository's `.shelf/config.toml` the folder of the specs (`specs`), the folder of the decision records (`decisions`), which results a run writes into them (`write`: `spec`, `adr`, both or none) and how a conflict between decision records is treated (`conflicts`: `block`, `warn` or `off`), using `openspec/specs`, `docs/adr`, both and `block` for what is missing, and SHALL refuse a value it does not understand like any other mistake in the file.

#### Scenario: A repository that keeps its decisions elsewhere

- **WHEN** `[results]` sets `decisions = "docs/decisions"`
- **THEN** the architect numbers and writes its record there and reads the earlier ones there

#### Scenario: A repository that wants no decision records from the factory

- **WHEN** `[results]` sets `write = ["spec"]`
- **THEN** no decision record is written and the review does not ask for one

#### Scenario: A value that is not understood

- **WHEN** `conflicts` is `maybe`
- **THEN** the run does not start and the message names the file and the key

### Requirement: A repository chooses how deep the spec review and the design review look

The system SHALL read `spec_review_depth` and `design_review_depth` from the `[policy]` section of a repository's `.shelf/config.toml`, each one of `quick`, `standard` or `thorough`, using `quick` for the spec review and `standard` for the design review when missing, and SHALL refuse any other value like any other mistake in the file.

#### Scenario: The default

- **WHEN** a repository has neither key
- **THEN** its spec review is quick and its design review is standard

#### Scenario: A value that is not understood

- **WHEN** the file sets `spec_review_depth = "deep"`
- **THEN** it is refused, naming the key and saying the choices are quick, standard and thorough

#### Scenario: The two reviews differ

- **WHEN** the file sets `spec_review_depth = "quick"` and `design_review_depth = "thorough"`
- **THEN** the spec review is quick and the design review is thorough

### Requirement: Mistakes in configuration are reported, not ignored

The system SHALL refuse a configuration file that is not valid TOML, has unknown keys or sections, names an unknown mode, entry point or role, gives a role no one (an empty list, which would leave its gate to administrators alone), or sets fewer than one round, and SHALL say why.

#### Scenario: A misspelt section

- **WHEN** a file contains an unknown section
- **THEN** it is refused naming the unknown key

#### Scenario: A role with no one in it

- **WHEN** a file sets `product_owner = []`
- **THEN** it is refused, saying to list the people or to leave the role out, because an empty role would lock its gate for everyone but an administrator

### Requirement: Waiting work looks at GitHub at a pace that suits the mode

The system SHALL poll GitHub often in local mode (from 30 seconds, slowing to at most 5 minutes) and less often in server mode (from 1 minute, slowing to at most 10 minutes), where webhooks wake the work but a missed webhook must still be noticed within minutes.

#### Scenario: Two modes

- **WHEN** the intervals of both modes are compared
- **THEN** the server mode starts later and ends later than the local mode

### Requirement: A repository's file is read from GitHub, and an invalid one is an error

The system SHALL read a repository's `.shelf/config.toml` from GitHub with the App's token, use the defaults when the file does not exist, and refuse to start or decide on a repository whose file is invalid, saying why, rather than silently using defaults.

#### Scenario: No file

- **WHEN** the repository has no configuration file
- **THEN** the defaults apply

#### Scenario: An invalid file

- **WHEN** the file has an unknown key
- **THEN** starting work on that repository is refused with the reason

### Requirement: Invalid configuration is one named error

The system SHALL raise a single, named error for any invalid configuration file, so callers can show the reason.

#### Scenario: Callers

- **WHEN** any configuration file is invalid
- **THEN** the same error type carries the reason

### Requirement: The time given to a repository's CI can be set

The system SHALL read from the environment how long one checks step looks at the CI (`SHELF_CI_WAIT`, seconds, half an hour by default) and how long a commit may show no run before the repository counts as having no CI (`SHELF_CI_GRACE`, seconds, two minutes by default).

#### Scenario: Defaults

- **WHEN** neither is set
- **THEN** a step looks for 1800 seconds and waits 120 for the first run to appear

### Requirement: The operator binds skill bundles to roles

The system SHALL read from `shelf.toml` a `[roles.<name>]` table for any agent role, whose `use` lists the names of catalog skill sources that role loads, refuse a table for a role that does not exist, and apply an edit of it without a restart.

#### Scenario: A binding

- **WHEN** the file has `[roles.implementer]` with `use = ["superpowers"]`
- **THEN** the implementer is bound to that source and the other roles to none

#### Scenario: A role that does not exist

- **WHEN** the file has `[roles.gardener]`
- **THEN** the file is refused and the error names the roles that exist

### Requirement: A repository file can say what happens at a disagreement

The system SHALL read `[policy] on_deadlock` of a repository's file as one of `ask`, `arbitrate-ask`, `arbitrate-go` and `go`, and refuse any other value with an error that lists them; SHALL, when the key is absent, read `proceed_on_deadlock` as `go` when true and `ask` when false; and SHALL let a person's choice on the start form take the place of the file's.

#### Scenario: The file names an answer

- **WHEN** the file has `on_deadlock = "arbitrate-go"`
- **THEN** its policy asks an arbitrator at a disagreement and goes on where the phase may be passed

#### Scenario: A value nobody knows

- **WHEN** the file has `on_deadlock = "sometimes"`
- **THEN** the file is refused and the error names the four answers

### Requirement: A repository that says nothing about its stops gets the autonomous flow

The system SHALL give a repository with no `.shelf/config.toml`, and a file that does not name a choice, the flow that goes on alone as far as it safely can: no wait for the spec approval, the design reviewed by an agent, and a disagreement settled by an arbitrator and, when it cannot, passed on with its open points (`arbitrate-go`); SHALL keep what a file does say (`spec_approval`, `design_review`, `on_deadlock`, or `proceed_on_deadlock` alone, which keeps its old meaning and so does not turn arbitration on); and SHALL still ask a person at the merge and for a failed step.

#### Scenario: No file

- **WHEN** a repository has no configuration file
- **THEN** its policy has no spec approval, a design review and the answer `arbitrate-go`

#### Scenario: A file that names a choice

- **WHEN** the file sets `spec_approval = true` and nothing else
- **THEN** the spec approval is asked, and the other choices are the autonomous ones

#### Scenario: A file with the old setting only

- **WHEN** the file sets `proceed_on_deadlock = false`
- **THEN** a disagreement asks a person, as it did
