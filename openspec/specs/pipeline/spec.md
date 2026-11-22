# Pipeline

## Purpose

Describe the software-development pipeline as data and say where a piece of work can enter it.

## Requirements

### Requirement: The pipeline is an ordered list of phases

The system SHALL define the pipeline as a fixed, ordered list of phases from intake to pull request.

#### Scenario: Reading the pipeline

- **WHEN** the pipeline is read
- **THEN** it starts at intake, ends at the pull request, and lists every phase once

### Requirement: Every entry point joins the pipeline at one phase

The system SHALL map each entry point (need, spec, design, plan, implement, pull-request review, work on a pull request) to the single phase at which the work joins the pipeline.

#### Scenario: Starting from a need

- **WHEN** work starts from a need
- **THEN** it goes through every phase of the pipeline

#### Scenario: Reviewing a pull request

- **WHEN** work starts from an existing pull request to be reviewed
- **THEN** it skips every phase before code review

#### Scenario: Working on a pull request

- **WHEN** work starts from an existing pull request to be changed
- **THEN** it joins at implementation and goes through the checks, the code review and the merge

### Requirement: Work started late runs the rest of the pipeline

The system SHALL run, for work started at any entry point, exactly the phases from its first phase to the pull request, in order.

#### Scenario: Starting from a plan

- **WHEN** work starts from a plan
- **THEN** it runs the plan, implementation, verification, code review and pull-request phases, in that order

### Requirement: Every phase has a kind and a place to go back to

The system SHALL give each phase a kind (produce, review, verify, gate or merge) and SHALL name, for each phase that can ask for changes, the phase that redoes the work.

#### Scenario: Code review asks for changes

- **WHEN** code review asks for changes
- **THEN** the work goes back to implementation

### Requirement: A policy shapes the course

The system SHALL let a policy turn off the spec approval and the design review, and SHALL set how many rounds a loop may take, which SHALL be at least one, and how deep the spec review and the design review look (each `quick`, `standard` or `thorough`; `quick` and `standard` by default), which shapes what the reviewers are told and never the course.

#### Scenario: Optional phases off

- **WHEN** the policy turns off the spec approval and the design review
- **THEN** the course of a need contains neither phase

#### Scenario: No rounds allowed

- **WHEN** a policy allows fewer than one round
- **THEN** it is refused

### Requirement: A policy may let work go on past a review that cannot settle

The system SHALL carry in the course whether the policy lets work go on past a spec or design review that cannot settle, SHALL let a person's choices for one piece of work replace the policy's spec approval, design review, that choice and the depth of each review (when the person made one) while keeping the policy's round limit, and SHALL default to waiting.

#### Scenario: The default

- **WHEN** a course is built from a policy that says nothing about it
- **THEN** the course waits at a deadlock

#### Scenario: A person's choices replace three of the policy

- **WHEN** a person chose no spec approval, no design review and going on past a deadlock for a repository allowing five rounds
- **THEN** the course has none of those two phases, goes on past a deadlock and allows five rounds

### Requirement: A policy names the stops it removes

The system SHALL name, for a policy, the stops it removes from the course, in the order `spec`, `design`, `deadlock`: the spec approval when it is off, the design review when it is off, and the wait at a deadlock when work goes on past it.

#### Scenario: Two stops removed

- **WHEN** a policy turns off the spec approval and the design review
- **THEN** it names `spec` and `design`

### Requirement: Only work without a pull request publishes one

The system SHALL publish a pull request for work that arrives without one, and SHALL NOT for work that starts from an existing pull request, whether to review it or to change it.

#### Scenario: Starting from a plan

- **WHEN** work starts from a plan
- **THEN** the course publishes a pull request

### Requirement: A course carries the protocol its work started with

The system SHALL build the course of a piece of work with the protocol version it starts under, defaulting to the original behaviour for work that has none recorded, and SHALL say whether that protocol opens the pull request early and whether its checks wait for the repository's CI (protocol 4 and later).

#### Scenario: Original work

- **WHEN** a course is built for work with no recorded protocol
- **THEN** it has protocol 1 and does not open the pull request early

#### Scenario: New work

- **WHEN** a course is built for new work
- **THEN** it has the current protocol and opens the pull request early

#### Scenario: Reviewing a pull request that is not ours

- **WHEN** a course is built for a review of an existing pull request under the current protocol
- **THEN** it hands the reviewer's findings to a person, while the same course under protocol 2 or earlier does not

#### Scenario: Waiting for the CI by protocol

- **WHEN** courses are built under protocols 3 and 4
- **THEN** only the one under protocol 4 waits for the repository's CI


#### Scenario: One approval for a review and its gate by protocol

- **WHEN** courses are built under protocols 5 and 6
- **THEN** only the one under protocol 6 counts a person's acceptance of an escalated review as the approval of the gate right after it

### Requirement: A course says whether a person's decisions are recorded in the repository

The system SHALL say, from the protocol a piece of work started under, whether the decisions a person makes on it are recorded in the repository (from the protocol that introduced it on, never for work that started under an earlier one).

#### Scenario: New work

- **WHEN** a course is built under the current protocol
- **THEN** it records decisions

#### Scenario: Work that started earlier

- **WHEN** a course is built for work that started under the previous protocol
- **THEN** it does not record decisions

### Requirement: A course says whether ending the work closes its pull request

The system SHALL say, from the protocol a piece of work started under, whether a person ending the work also closes the pull request it opened (from the protocol that introduced it on, never for work that started under an earlier one).

#### Scenario: New work

- **WHEN** a course is built under the current protocol
- **THEN** it closes its pull request when a person ends the work

#### Scenario: Work that started earlier

- **WHEN** a course is built for work that started under the previous protocol
- **THEN** it leaves the pull request

### Requirement: A course says whether agents continue their sessions

The system SHALL say, from the protocol a piece of work started under, whether an agent that runs again on it continues its earlier session (from the protocol that introduced it on, never for work that started under an earlier one).

#### Scenario: New work

- **WHEN** a course is built under the current protocol
- **THEN** its agents continue their sessions

#### Scenario: Work that started earlier

- **WHEN** a course is built for work that started under the previous protocol
- **THEN** its agents start fresh each time

### Requirement: New work judges its review loops by repetition and minor points

The system SHALL start new work under a protocol version in which a review loop ends when a reviewer reports a repeated point, allows twice the policy's rounds while each round brings only new points, and lets a code review with only minor points left go to the merge gate; and SHALL keep the count-only limit for work that began under an earlier protocol.

#### Scenario: Work from before

- **WHEN** work that began under protocol 9 gets a repeated point
- **THEN** it is sent back to the author until its rounds run out, as before

### Requirement: New work looks at the CI once the pull request is ready, before it asks for the merge

The system SHALL start new work under a protocol version in which, after the pull request is marked ready for review, the work looks at the repository's CI again before it asks a person to merge: it waits while the CI runs, goes to the merge gate when it is green or absent, and puts the pull request back to draft and sends the work back to the implementer with the failing runs when it is red; and SHALL keep going straight to the merge gate for work that began under an earlier protocol.

#### Scenario: A run started by marking the pull request ready fails

- **WHEN** the pull request has been marked ready and a workflow that this started ends red
- **THEN** the pull request goes back to draft and the implementer is sent the failing runs, instead of a person being asked to merge

#### Scenario: The CI is still running

- **WHEN** the CI has not finished when the work looks at it
- **THEN** the work looks again in the same round, and a person is asked only when it is green

#### Scenario: Work from before

- **WHEN** work that began under protocol 10 reaches the merge gate
- **THEN** a person is asked at once, as before

### Requirement: New work judges its checks loop by repetition, not by a count of rounds

The system SHALL start new work under a protocol version (12) in which a failing check goes back to the implementer while its failure changes and a person is asked when the same failure comes back three times in a row, or at ten times the policy's rounds, and SHALL keep work that began under an earlier protocol on the count of rounds alone.

#### Scenario: Work from before

- **WHEN** work that began under protocol 11 has its checks fail more often than the policy's rounds
- **THEN** a person is asked when the rounds run out, as before

#### Scenario: New work

- **WHEN** a course is built for new work
- **THEN** it has protocol 12 and its checks loop is judged by the repetition of its failure

### Requirement: The course carries the answer to a disagreement, and protocol 13 arbitrates

The system SHALL give a course the answer to a disagreement of its policy (`ask`, `arbitrate-ask`, `arbitrate-go` or `go`), SHALL let the course go on past a deadlock of a document review when the answer is `arbitrate-go` or `go`, and SHALL name `deadlock` among the stops a policy removes only for those two. A course started with protocol 13, the current one, arbitrates a deadlock when its answer says so; a course of an earlier protocol does not.

#### Scenario: A new course

- **WHEN** a course is built for new work whose policy answers `arbitrate-ask`
- **THEN** it has protocol 13, it arbitrates a deadlock, and its removed stops do not name `deadlock`

#### Scenario: An old course

- **WHEN** a course of protocol 12 has the answer `arbitrate-ask`
- **THEN** it does not arbitrate
