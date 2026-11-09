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

### Requirement: Work on a pull request starts only on one that can be changed

The system SHALL, before starting work on an existing pull request, refuse a pull request that is closed, one that comes from a fork (whose branch the App cannot push to), and a request that says nothing to do, each with a message that says why.

#### Scenario: A fork

- **WHEN** a person asks to work on a pull request from a fork
- **THEN** nothing starts and the message says the App cannot push to its branch

#### Scenario: A closed pull request

- **WHEN** the pull request is closed
- **THEN** nothing starts and the message says it is closed

#### Scenario: Nothing to do

- **WHEN** the instruction is empty
- **THEN** nothing starts

### Requirement: A review starts only on a pull request the repository has

The system SHALL, before starting a review of a pull request, ask GitHub as the person whether the chosen repository has that pull request, and SHALL refuse the start with a message naming the repository and the number when it does not, so that a work is never started on the wrong repository and left to fail at its first step.

#### Scenario: A number the repository does not have

- **WHEN** a person asks to review pull request 2 of a repository that has none
- **THEN** nothing starts and the message says that repository has no pull request #2 and to check the repository

#### Scenario: An existing pull request

- **WHEN** the repository has the pull request
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

#### Scenario: A work with times

- **WHEN** a work has acted
- **THEN** its view carries when it last did anything and when it last did something at each phase

#### Scenario: A work with a line

- **WHEN** a work was started with a request
- **THEN** its view carries the request's first line

