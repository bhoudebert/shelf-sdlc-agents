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
