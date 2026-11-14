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

The system SHALL let a policy turn off the spec approval and the design review, and SHALL set how many rounds a loop may take, which SHALL be at least one.

#### Scenario: Optional phases off

- **WHEN** the policy turns off the spec approval and the design review
- **THEN** the course of a need contains neither phase

#### Scenario: No rounds allowed

- **WHEN** a policy allows fewer than one round
- **THEN** it is refused

### Requirement: A policy may let work go on past a review that cannot settle

The system SHALL carry in the course whether the policy lets work go on past a spec or design review that cannot settle, SHALL let a person's choices for one piece of work replace the policy's spec approval, design review and that choice while keeping the policy's round limit, and SHALL default to waiting.

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
