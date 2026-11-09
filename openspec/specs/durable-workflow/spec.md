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

### Requirement: A review shows the pull request it started from

The system SHALL link, on the board and on the work page, the pull request a review of an existing pull request started from, even though that work publishes nothing of its own.

#### Scenario: A review

- **WHEN** work starts at the review of pull request 7
- **THEN** its view links pull request 7 of that repository

### Requirement: The workflow keeps a line of the request for the board

The system SHALL keep, with the workflow's memo and not in its history, the first line of the request shortened, so the board can tell pieces of work apart without opening each, and SHALL read work whose memo has none as untitled.

#### Scenario: A started work

- **WHEN** work is started with a multi-line request
- **THEN** the board's view of it carries the request's first line

### Requirement: Work that cannot be read is shown, not hidden

The system SHALL show a piece of work that exists but whose state cannot be read as failed, with the reason, instead of leaving it off the board.

#### Scenario: A failing workflow

- **WHEN** reading the state of a piece of work fails
- **THEN** the board shows it as failed and says it may have been started by an older release

#### Scenario: Closing it

- **WHEN** an administrator closes such a piece of work
- **THEN** the workflow is terminated without running its code, and a terminated workflow that cannot be read is shown as aborted

#### Scenario: A message the engine refuses

- **WHEN** a decision is sent to work that is finished or cannot be run
- **THEN** the runner reports it as unreachable instead of failing with an engine error

### Requirement: Publishing names the pull request and may take as long as an agent

The system SHALL have the publish activity ask for the pull request's title from the step runner and give it to the pull request, allowing it the time a short agent run takes, without changing what a recorded history does.

#### Scenario: Publishing

- **WHEN** the workflow orders the pull request published
- **THEN** the activity asks for a title, opens or retitles the pull request with it, and returns its address

### Requirement: The safety net looks often enough that a missed webhook costs about a minute

The system SHALL look at a waiting work's pull request every minute at first in server mode, growing no further than ten minutes, and every thirty seconds growing to five minutes in local mode.

#### Scenario: A webhook that never arrives

- **WHEN** a command is typed on a pull request and no webhook is delivered
- **THEN** the next look finds it within about a minute

### Requirement: A step result can say the CI has not finished

The system SHALL carry, in the result of a step as recorded in the workflow's history, whether the checks are waiting for the repository's CI, and SHALL read a result recorded without that field as not waiting, so that histories recorded before it replay unchanged.

#### Scenario: An older result

- **WHEN** a recorded checks result has no waiting field
- **THEN** it is read as a result that is not waiting

#### Scenario: A waiting result

- **WHEN** the checks report that the CI is running
- **THEN** the recorded result says waiting, and the workflow runs the checks again in the same round

### Requirement: A running step heartbeats on its own

The system SHALL heartbeat from the activity that runs a step, on a timer independent of what the step does, at an interval well inside the heartbeat timeout the workflow sets, so that a step that is silent (a build, an agent thinking, a wait for the CI) is not timed out while it works, and a step that really died still is.

#### Scenario: A long silent step

- **WHEN** a step runs for several heartbeat timeouts without output
- **THEN** it is not timed out

#### Scenario: A dead worker

- **WHEN** the worker stops
- **THEN** the heartbeats stop and Temporal retries the step

