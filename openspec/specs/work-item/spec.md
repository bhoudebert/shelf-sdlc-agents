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

### Requirement: A review of someone else's pull request ends with a person, not with new code

The system SHALL, when work started from an existing pull request has its review find problems, wait for a person with the findings instead of sending the work to the implementer, and SHALL send the work to the implementer only when a person asks for changes, handing over the reviewer's findings when the person wrote no note. Work that publishes its own pull request keeps the automatic loop, and work started before this rule keeps its original behaviour.

#### Scenario: The review finds problems

- **WHEN** the review of an existing pull request asks for changes
- **THEN** the work waits for a person, who may approve, ask for changes, reject or abort

#### Scenario: The person asks for changes

- **WHEN** the person asks for changes without a note
- **THEN** the implementer starts with the reviewer's findings as its instructions

#### Scenario: Our own pull request

- **WHEN** the review of a pull request the work published asks for changes
- **THEN** the work goes back to the implementer without asking, within the round limit

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

### Requirement: The pull request is published after the first step and readied at the merge

The system SHALL order the pull request to be published once the first step of work that carries its own pull request is done, SHALL order it marked ready when the work reaches the merge, and SHALL order it back to draft when changes are asked there.

#### Scenario: The first step

- **WHEN** the first step finishes
- **THEN** publishing is ordered before the next step runs

#### Scenario: A pull request of someone else's

- **WHEN** work reviews an existing pull request
- **THEN** the system never orders it published or readied

### Requirement: Checks that find the CI still running look again without losing a round

The system SHALL, on a checks result that says the repository's CI has not finished, run the checks again in the same round, and SHALL send the work back like a failed check when the result is a failure. Work started before this behaviour (protocol 3 or earlier) SHALL treat such a result as passed.

#### Scenario: Waiting

- **WHEN** the checks report that the CI is still running
- **THEN** the checks run again with the same round number

#### Scenario: Work on an older protocol

- **WHEN** work on protocol 3 receives a waiting result
- **THEN** it goes on to the code review

### Requirement: Behaviour changes are gated on a protocol

The system SHALL derive from the work's protocol whether the pull request opens early, is readied at the merge and is labelled, so that work on the original protocol decides exactly as before.

#### Scenario: The original protocol

- **WHEN** work on protocol 1 finishes its first step
- **THEN** no publication is ordered until the merge
