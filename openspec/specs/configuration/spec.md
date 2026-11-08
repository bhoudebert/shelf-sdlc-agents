# Configuration

## Purpose

Let the operator configure an instance and each repository configure itself, in TOML files that are checked strictly.

## Requirements

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
- **THEN** every entry point is enabled, three rounds are allowed and no role restricts anyone

#### Scenario: Roles and policy

- **WHEN** the file lists roles and turns the design review off
- **THEN** the policy has no design review and the roles hold the listed logins

### Requirement: Mistakes in configuration are reported, not ignored

The system SHALL refuse a configuration file that is not valid TOML, has unknown keys or sections, names an unknown mode, entry point or role, or sets fewer than one round, and SHALL say why.

#### Scenario: A misspelt section

- **WHEN** a file contains an unknown section
- **THEN** it is refused naming the unknown key

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
