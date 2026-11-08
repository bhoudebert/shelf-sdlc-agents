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
