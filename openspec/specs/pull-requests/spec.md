# Pull requests

## Purpose

Make the pull request the home of a piece of work: where it is published, what it waits for is announced, and where people answer with a closed list of commands.

## Requirements

### Requirement: Work is published as a draft pull request

The system SHALL open a draft pull request from the work's branch, titled with the first line of the need and carrying the requester's login.

#### Scenario: Publishing

- **WHEN** work from a need reaches the pull-request phase
- **THEN** a draft pull request is opened with the work's branch, the base branch of the repository and a `Requested-by` line

### Requirement: Every wait is announced with how to answer

The system SHALL comment on the pull request whenever the work waits for a person, saying why and listing the commands that answer.

#### Scenario: A gate

- **WHEN** the work waits at a gate
- **THEN** a comment says it waits for approval and lists the `/shelf` commands

#### Scenario: Reviewing someone's pull request

- **WHEN** the work reviews an existing pull request
- **THEN** the comment goes on that pull request

### Requirement: People answer with a closed list of `/shelf` commands

The system SHALL read from a comment only a first line starting with `/shelf` and one of approve, changes, resume, reject or abort, with the rest as the note, and SHALL ignore everything else.

#### Scenario: A known command with a note

- **WHEN** a comment says `/shelf changes rename the endpoint`
- **THEN** it is the changes decision with that note

#### Scenario: Anything else

- **WHEN** a comment is chat or an unknown word
- **THEN** it is not a command

### Requirement: Only trusted people decide, and the factory ignores itself

The system SHALL accept commands only from people with write access to the repository, only if posted after the factory's latest announcement, and SHALL ignore the factory's own comments.

#### Scenario: An outsider

- **WHEN** a person without write access types `/shelf approve`
- **THEN** nothing happens

### Requirement: A merge or a close ends the work

The system SHALL report a closed pull request as merged or closed so that the work ends accordingly.

#### Scenario: Merged

- **WHEN** the pull request is closed with a merge
- **THEN** the work learns it was merged
