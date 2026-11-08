# Work item

## Purpose

Decide, as a pure function, what happens next to a piece of work as steps finish, people decide and the pull request changes.

## Requirements

### Requirement: Work follows the course of its entry point

The system SHALL run a piece of work through the phases of its course in order, asking a person at gates and at the pull request, and ending when the pull request is merged or closed.

#### Scenario: From a need to a merge

- **WHEN** work starts from a need and every step succeeds and every gate is approved
- **THEN** it runs intake, spec review, design, design review, plan, implementation, checks and code review, opens a pull request, and ends as merged when the pull request is merged

#### Scenario: Reviewing an existing pull request

- **WHEN** work starts from an existing pull request
- **THEN** it starts at code review and does not publish a pull request

### Requirement: Reviewers and checks send work back, within a limit

The system SHALL send work back to the phase that redoes it, with the issues found, when a reviewer asks for changes or the checks fail, and SHALL ask a person once the number of rounds reaches the policy limit.

#### Scenario: Changes requested

- **WHEN** a reviewer asks for changes with issues
- **THEN** the producing phase runs again with those issues as feedback and one more round counted

#### Scenario: The limit is reached

- **WHEN** a reviewer asks for changes after the policy's maximum number of rounds
- **THEN** the work waits for a person and says the limit was reached

#### Scenario: The budget is shared by the loops

- **WHEN** work goes from code review back through implementation and checks to code review
- **THEN** the rounds already used are kept, so the loops together stay within the limit

### Requirement: People decide with a closed list of commands

The system SHALL accept from people only approve, changes, resume, reject and abort, and SHALL ignore a decision that does not apply to the state the work is in.

#### Scenario: Approving a gate

- **WHEN** a person approves the spec gate
- **THEN** the work goes on to the next phase

#### Scenario: Changes at a gate

- **WHEN** a person asks for changes at a gate with a note
- **THEN** the producing phase runs again with the note as feedback

#### Scenario: A decision that does not apply

- **WHEN** a person approves a failed step
- **THEN** nothing changes

### Requirement: A failing step asks a person instead of ending the work

The system SHALL ask a person when a step fails for good or returns a result of the wrong kind, and SHALL let them resume the step.

#### Scenario: Resuming a failed step

- **WHEN** a person resumes a failed step with a note
- **THEN** the step runs again with the note as feedback

### Requirement: Finished work stays finished

The system SHALL ignore every event once the work is finished, and SHALL cancel the running step when the work is aborted, rejected or its pull request is closed.

#### Scenario: Aborting a running step

- **WHEN** a person aborts while a step runs
- **THEN** the step is cancelled and the work ends as aborted
