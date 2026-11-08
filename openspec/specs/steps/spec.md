# Steps

## Purpose

Carry out one step of the pipeline: a fresh clone, the agent role of the phase (or the project's own checks), and a result the state machine can use.

## Requirements

### Requirement: Every step runs in a fresh clone that is removed afterwards

The system SHALL clone the repository anew for each step, continue the work's branch if an earlier step pushed it, and remove the clone when the step ends, whatever its outcome.

#### Scenario: A later step

- **WHEN** a second step starts after a first one pushed
- **THEN** the clone contains what the first step pushed

#### Scenario: Cleanup

- **WHEN** a step ends
- **THEN** its clone no longer exists

### Requirement: Each role is limited to its own tools and budget

The system SHALL give each agent only the tools of its role, with reviewers read-only and only the implementer able to run commands, run inside the sandbox, and bounded in turns and money.

#### Scenario: A reviewer

- **WHEN** a code review runs
- **THEN** the agent may only read and search the clone

### Requirement: Producers leave their work on the work's branch

The system SHALL commit and push what a producing step wrote, to the work's branch, as the App's bot identity, and SHALL push nothing when nothing changed.

#### Scenario: A document

- **WHEN** the intake step writes the spec
- **THEN** the spec is committed and pushed to the work's branch

### Requirement: A reviewer's verdict is read from its last verdict line

The system SHALL take the last `VERDICT:` line of a reviewer's answer as its verdict and the text before it as the issues, and SHALL send the work to a person when there is no verdict.

#### Scenario: Changes requested

- **WHEN** a reviewer ends with `VERDICT: CHANGES`
- **THEN** the issues go back as feedback

#### Scenario: No verdict

- **WHEN** a reviewer gives no verdict line
- **THEN** it is never treated as approval

### Requirement: Checks run the repository's own commands

The system SHALL run each command the repository lists as a check in the clone and report every failure, with the end of its output, to the implementer.

#### Scenario: One command fails

- **WHEN** one of two checks exits non-zero
- **THEN** the report names that command and its exit code, and the step is not passed

### Requirement: A pull request under review receives the review

The system SHALL post the code review as a comment on a pull request that was submitted for review, and read that pull request's head without being able to push to it.

#### Scenario: Review my pull request

- **WHEN** the code review of a submitted pull request ends
- **THEN** its verdict and issues are posted on that pull request

### Requirement: Secrets never appear in errors

The system SHALL NOT include the installation token in an error raised by a failed git command.

#### Scenario: A failed clone

- **WHEN** a clone fails
- **THEN** the error text does not contain the token

### Requirement: The agents' sandbox works inside a container when asked

The system SHALL run the agents' sandbox in its weaker nested mode only when the operator turns it on, which a container deployment does for the worker, and SHALL keep the sandbox on in both cases.

#### Scenario: Default

- **WHEN** the nested sandbox is not turned on
- **THEN** the sandbox is on in its normal mode

#### Scenario: In Docker

- **WHEN** the operator turns the nested sandbox on
- **THEN** the sandbox is on in its nested mode

### Requirement: A failed login tells the operator where the credential goes

The system SHALL, when an agent fails because it is not logged in, say that the credential belongs in the worker's environment (a Claude token or an API key in the environment file), not in the host's own login.

#### Scenario: Not logged in

- **WHEN** an agent step fails with a login error
- **THEN** the failure names the environment variables to set and where

### Requirement: The submitted text is recorded in the repository

The system SHALL write the text a person submitted into the work's document folder in the file its entry point implies (the request, the spec, the design or the plan), once, and never overwrite it, so that every agent and reviewer reads the same document from the repository.

#### Scenario: A submitted spec

- **WHEN** work starts from a spec
- **THEN** the spec is recorded as the spec the reviewers read, and committed

### Requirement: Every step says what it did on the pull request

The system SHALL post on the pull request, after each step, the producer's summary with the file it wrote, the reviewer's verdict with its issues, or the checks' result.

#### Scenario: A review

- **WHEN** a reviewer finishes
- **THEN** its verdict and issues appear as a comment on the pull request
