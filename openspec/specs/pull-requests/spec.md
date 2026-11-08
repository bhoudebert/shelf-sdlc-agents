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

### Requirement: A review can be posted on the pull request

The system SHALL post a given text as a comment on the pull request of a piece of work, so that a review is read where people already work.

#### Scenario: Posting a review

- **WHEN** a reviewer's verdict and issues are to be shown
- **THEN** they appear as a comment on the pull request

### Requirement: The pull request opens as a draft as soon as the first step is done

The system SHALL open the draft pull request right after the first step of the work, so that everything that follows is visible there, and SHALL return the pull request that already exists rather than open a second one.

#### Scenario: A need

- **WHEN** the first step of work started from a need finishes
- **THEN** a draft pull request exists on the work's branch

#### Scenario: Asked twice

- **WHEN** the system asks for the pull request again
- **THEN** the existing one is returned and nothing new is opened

### Requirement: The pull request is ready for review only when the code is reviewed

The system SHALL keep the pull request a draft while agents work, mark it ready for review when the code review approves and the work waits for the merge, and put it back to draft when changes are asked after that, leaving a submitted pull request of someone else's untouched.

#### Scenario: Approved code

- **WHEN** the code review approves
- **THEN** the pull request is marked ready for review

#### Scenario: Changes asked on the pull request

- **WHEN** a person asks for changes on a ready pull request
- **THEN** it goes back to draft while the agents rework it

### Requirement: The pull request carries one stage label

The system SHALL keep exactly one `shelf:` label on the pull request saying what is happening (a step running, a person needed and for what, or ready to merge), creating it when missing, replacing the previous one and never touching other labels.

#### Scenario: A step starts

- **WHEN** the implementation step starts
- **THEN** the pull request carries `shelf: implementing` and no other `shelf:` label

#### Scenario: A person is needed

- **WHEN** the work waits at the spec approval
- **THEN** the label says a person is needed and for what

### Requirement: Nothing is posted before the pull request exists

The system SHALL post, label and poll nothing for a pull request that is not open yet.

#### Scenario: Before the first step ends

- **WHEN** a comment or a label is asked for before the pull request exists
- **THEN** nothing is posted and nothing fails
