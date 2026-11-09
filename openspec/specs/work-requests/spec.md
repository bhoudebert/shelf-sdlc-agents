# Work requests

## Purpose

Let a signed-in person start work, decide for it and see it, on the repositories they can access.

## Requirements

### Requirement: Work starts only on a repository the person can see

The system SHALL start work only on a repository that the app is installed on and that the person can access, and SHALL answer "not found" for any other.

#### Scenario: A repository the person cannot see

- **WHEN** a person starts work on a repository outside their visible repositories
- **THEN** the request is refused as not found, revealing nothing about the repository

### Requirement: A start request must match the entry point

The system SHALL refuse a start request whose entry point the repository disabled, whose text is empty (except for a pull-request review), or that reviews a pull request without its number.

#### Scenario: An empty need

- **WHEN** a person submits a need that is empty
- **THEN** the request is refused as invalid

#### Scenario: Reviewing a pull request

- **WHEN** a person starts a pull-request review with a pull request number and no text
- **THEN** the work starts

### Requirement: Decisions are checked against the person's role

The system SHALL deliver a decision to the work only if the person may decide at the phase the work waits at, and SHALL refuse it otherwise without changing the work.

#### Scenario: A person without the role

- **WHEN** a person without the required role approves a gate
- **THEN** the decision is refused and the work is unchanged

### Requirement: The board shows what the person can see

The system SHALL list the work of the repositories the person can see, and no other.

#### Scenario: Two repositories

- **WHEN** work exists on a visible and on an invisible repository
- **THEN** the board lists only the work on the visible one

### Requirement: Administrators see the work of every repository

The system SHALL list the work of every repository for an administrator, and only the work of repositories they can see for anyone else.

#### Scenario: An administrator

- **WHEN** an administrator asks for the board
- **THEN** work on repositories they cannot open is listed too

### Requirement: The board's view of a work carries a line of its request

The system SHALL give the view of a piece of work, in addition to its repository, requester, entry and phase, a short line of its request (empty for work that has none), so that every list of work can say what each one is.

#### Scenario: A work with a line

- **WHEN** a work was started with a request
- **THEN** its view carries the request's first line

