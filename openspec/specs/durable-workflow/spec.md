# Durable workflow

## Purpose

Run a piece of work as a Temporal workflow that only interprets the pure state machine, so that it survives crashes, waits days for people, and stays deterministic.

## Requirements

### Requirement: The workflow executes the commands of the state machine

The system SHALL feed every event (end of a step, decision, pull-request change) to the pure state machine and execute exactly the commands it returns: run a step, announce a wait, publish the pull request, cancel the step, conclude.

#### Scenario: Reviewing a pull request

- **WHEN** work starts from an existing pull request and the code review approves
- **THEN** the work announces that it waits for the merge, publishes nothing, and ends as merged when the pull request is merged

#### Scenario: From a need

- **WHEN** work starts from a need
- **THEN** it stops at the spec gate until a person approves, then publishes the pull request and runs the rest of the pipeline in order

### Requirement: People can act while a step runs

The system SHALL accept a person's decision at any time, and SHALL cancel the running step when the person aborts.

#### Scenario: Abort

- **WHEN** a person aborts while a step is running
- **THEN** the step is cancelled and the work ends as aborted

### Requirement: A failing step waits for a person

The system SHALL turn a step that failed after its retries into a wait for a person, who can resume it.

#### Scenario: Resume

- **WHEN** a step fails and a person resumes it with a note
- **THEN** the step runs again with the note

### Requirement: Waiting work looks at the pull request on a slowing timer

The system SHALL look at the pull request on a durable timer while work waits for a person, doubling the interval up to a ceiling, and SHALL feed what it finds to the state machine.

#### Scenario: A merge nobody signalled

- **WHEN** the pull request is merged and no webhook arrives
- **THEN** the next look finds it and the work ends as merged

### Requirement: Recorded histories keep replaying

The system SHALL keep the workflow deterministic: a recorded history of a finished piece of work replays without error against the current code.

#### Scenario: Replay

- **WHEN** the history of a finished piece of work is replayed
- **THEN** the replay completes without a non-determinism error

### Requirement: Work is started and inspected through the workflow engine

The system SHALL start one workflow per piece of work with the policy of its repository and the poll pace of the instance's mode, deliver decisions to it as signals, and show its repository, requester, phase and wait on the board, listing only the repositories asked for.

#### Scenario: Starting and aborting

- **WHEN** work is started, appears waiting at the spec gate, and a person aborts it
- **THEN** the board shows it finished as aborted

#### Scenario: An unknown id

- **WHEN** the board is asked for work that does not exist
- **THEN** it has no view of it

### Requirement: A closed pull request can be signalled from outside

The system SHALL let a webhook tell a piece of work that its pull request was merged or closed, ending the work accordingly without waiting for the next look.

#### Scenario: A merge signalled by a webhook

- **WHEN** the work is told its pull request was merged
- **THEN** it ends as merged

### Requirement: The runner can list the work of every repository

The system SHALL list the work of every repository when no repository filter is given, for administrators.

#### Scenario: No filter

- **WHEN** the work is listed without a repository filter
- **THEN** all work is returned

### Requirement: Listing work is cheap with many viewers

The system SHALL look at the workflows concurrently, bounded, and share one listing between callers for a couple of seconds, so many open boards cost one set of workflow-engine calls.

#### Scenario: Several callers at once

- **WHEN** several callers list work within a moment
- **THEN** the workflow engine is asked to list once and each caller gets its own filtered view

### Requirement: The workflow keeps the pull request's stage and draft state in step

The system SHALL set the pull request's stage label whenever a step starts or a person is awaited and apply the ordered ready or draft state, and SHALL treat a failure of either as cosmetic, never as a reason to stop the work.

#### Scenario: A GitHub failure

- **WHEN** setting the label fails
- **THEN** the work continues

### Requirement: The workflow keeps the story for the progress comment

The system SHALL remember what each step and each decision meant at the phase it happened in and update the progress comment after every event, treating a failure to do so as cosmetic.

#### Scenario: A decision

- **WHEN** a person approves a gate
- **THEN** the progress comment shows their decision at that step

### Requirement: Work already running keeps the behaviour it started with

The system SHALL record, when a piece of work starts, the protocol version it behaves by, SHALL give work started before that record existed the original behaviour, and SHALL gate every change that would alter what a recorded history does on a newer protocol, so that an update never breaks work in progress.

#### Scenario: Work started by an older release

- **WHEN** a release is installed while older work is waiting for a person
- **THEN** the older work replays and continues exactly as it would have

#### Scenario: Recorded histories

- **WHEN** histories recorded by earlier releases are replayed with the current code
- **THEN** every one replays without a non-determinism error

### Requirement: Work that cannot be read is shown, not hidden

The system SHALL show a piece of work that exists but whose state cannot be read as failed, with the reason, instead of leaving it off the board.

#### Scenario: A failing workflow

- **WHEN** reading the state of a piece of work fails
- **THEN** the board shows it as failed and says it may have been started by an older release
