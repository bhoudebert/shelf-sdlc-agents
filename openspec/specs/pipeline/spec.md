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

The system SHALL map each entry point (need, spec, design, plan, implement, pull-request review) to the single phase at which the work joins the pipeline.

#### Scenario: Starting from a need

- **WHEN** work starts from a need
- **THEN** it goes through every phase of the pipeline

#### Scenario: Reviewing a pull request

- **WHEN** work starts from an existing pull request
- **THEN** it skips every phase before code review

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

### Requirement: Only work without a pull request publishes one

The system SHALL publish a pull request for work that arrives without one, and SHALL NOT for work that starts from an existing pull request.

#### Scenario: Starting from a plan

- **WHEN** work starts from a plan
- **THEN** the course publishes a pull request
