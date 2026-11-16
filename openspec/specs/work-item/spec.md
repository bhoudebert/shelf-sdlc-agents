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

### Requirement: Work may go on past a review that cannot settle, when its policy says so

The system SHALL, when the policy of a piece of work says to proceed on deadlock, go on to the next phase instead of waiting for a person when the spec review or the design review answers that it cannot decide or sends work back after the maximum number of rounds, SHALL post the issues that stayed open on the pull request, and SHALL NOT do so for the code review or the checks. Without that policy, and for work that began before it existed, a person is asked as before.

#### Scenario: The spec review deadlocks

- **WHEN** the policy proceeds on deadlock and the spec review asks for changes after the maximum number of rounds
- **THEN** the design starts (or the spec approval gate, when it is on) and a comment on the pull request lists the open issues

#### Scenario: The design review cannot decide

- **WHEN** the policy proceeds on deadlock and the design review answers escalate
- **THEN** the plan starts and the open issues are posted

#### Scenario: A red check still waits

- **WHEN** the policy proceeds on deadlock and the checks fail after the maximum number of rounds
- **THEN** the work waits for a person

#### Scenario: The code review still waits

- **WHEN** the policy proceeds on deadlock and the code review answers escalate
- **THEN** the work waits for a person

#### Scenario: Not asked for

- **WHEN** the policy does not proceed on deadlock and the spec review reaches the round limit
- **THEN** the work waits for a person and says the limit was reached

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

#### Scenario: Accepting an escalated review also approves the gate after it

- **WHEN** a person accepts a spec review that escalated, on work of protocol 6 or later
- **THEN** the spec approval gate is not asked again and the design starts

#### Scenario: Earlier work asks twice

- **WHEN** work on protocol 5 or earlier has its escalated spec review accepted
- **THEN** the work waits at the spec approval gate, as before

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

### Requirement: Work on an existing pull request changes that pull request

The system SHALL, for work started on a pull request that already exists to be changed (protocol 5 and later), run implementation, checks, code review and the merge in that order on the pull request's own branch, SHALL NOT open or retitle a pull request, SHALL send a reviewer's requested changes back to the developer by itself like work of its own, SHALL mark the pull request ready for review when the work asks for the merge, and SHALL put it back to draft when a person asks for changes at the merge.

#### Scenario: A rebase and verify

- **WHEN** work on a pull request is started with the instruction to rebase it
- **THEN** the developer runs first, the checks wait for the CI of what was pushed, the reviewer reviews, and a person is asked at the merge, and no pull request is opened

#### Scenario: Changes asked at the merge

- **WHEN** a person asks for changes while the work waits at the merge
- **THEN** the pull request goes back to draft and the developer runs again with their note

### Requirement: A read-only review never starts a developer

The system SHALL answer a person who asks for changes after a review of a pull request that agents do not change (protocol 5 and later) with another review that takes their note into account, and SHALL NOT start a developer on a branch of its own that has nothing to do with that pull request. Work started earlier SHALL keep sending the reviewer's findings to the developer on request.

#### Scenario: Changes asked after a read-only review

- **WHEN** a person asks for changes with a note after the review
- **THEN** the review runs again with the note

#### Scenario: Older work

- **WHEN** work on protocol 4 receives the same request
- **THEN** the developer runs with the findings, as before

### Requirement: Behaviour changes are gated on a protocol

The system SHALL derive from the work's protocol whether the pull request opens early, is readied at the merge and is labelled, so that work on the original protocol decides exactly as before.

#### Scenario: The original protocol

- **WHEN** work on protocol 1 finishes its first step
- **THEN** no publication is ordered until the merge

### Requirement: A step's result can carry what the agent used

The system SHALL let the result of a producing or reviewing step carry what its agent used (tokens, cost, turns, time), without that changing what the result means: two results that differ only in what they used SHALL lead to the same decision, and a result with no usage SHALL behave as it always did.

#### Scenario: A verdict with usage

- **WHEN** a reviewer's result approves and carries what it used
- **THEN** the work moves on exactly as it does for the same verdict with no usage

#### Scenario: A result with no usage

- **WHEN** a step's result carries no usage
- **THEN** the work behaves as before

### Requirement: A step can carry the session of the agent that ran it, and be told the one to continue

The system SHALL let the command to run a step carry the session the agent should continue, and the result of a producing or reviewing step carry the session the agent ran in, without that changing what the result means: two results that differ only in the session SHALL lead to the same decision.

#### Scenario: A verdict with a session

- **WHEN** a reviewer's result approves and carries its session
- **THEN** the work moves on exactly as it does for the same verdict with no session

#### Scenario: A step with no session to continue

- **WHEN** a step is run with no session
- **THEN** it behaves as it always did

### Requirement: A review loop ends when it repeats itself or when only minor points are left, not only on a count

The system SHALL, for work that begins after this requirement, read two lines of a reviewer's answer: `REPEATED: <n>`, how many points it raised in an earlier round that are still unaddressed (none when absent), and `BLOCKING: yes|no`, whether any open point must be fixed before the work can merge (yes when absent); SHALL stop sending the work back and treat the review as unable to settle as soon as a reviewer reports a repeated point, since the author and the reviewer then disagree; SHALL allow twice the policy's rounds while each round brings only points that are new; and SHALL let a code review that cannot settle go on to the merge gate, with its open points posted on the pull request, when its last answer said no point is blocking. Work already running keeps the count-only limit.

#### Scenario: Each round finds something new

- **WHEN** the reviewer asks for changes after the policy's maximum number of rounds, and reports no repeated point
- **THEN** the work goes back to the author again, up to twice the maximum

#### Scenario: The same point comes back

- **WHEN** the reviewer asks for changes and reports that a point it raised before is still open
- **THEN** the work does not go back to the author: a person is asked, or the open points are posted when the policy lets the work go on

#### Scenario: Only minor points remain

- **WHEN** the code review cannot settle and its last answer reported no blocking point
- **THEN** the work goes on to the merge gate and the open points are posted on the pull request

#### Scenario: Work that began before

- **WHEN** work that began under an earlier protocol gets a verdict
- **THEN** it is judged by the count of rounds alone, as before

### Requirement: The merge is asked only after the CI of the ready pull request is seen

The system SHALL, for work under protocol 11 and later that readies a pull request, enter the merge phase as a step (the CI look) and ask a person for the merge only when that step finds the CI green or absent; while the CI runs it looks again in the same round, and when the CI is red it puts the pull request back to draft and sends the work to the implementer with the failing runs, counted as a round.

#### Scenario: Red after ready

- **WHEN** the pull request was marked ready and the CI look finds a red run
- **THEN** the pull request is a draft again and the implementer is sent the failing runs, and nobody is asked to merge
