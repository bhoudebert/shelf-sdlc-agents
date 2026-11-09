# Pull requests

## Purpose

Make the pull request the home of a piece of work: where it is published, what it waits for is announced, and where people answer with a closed list of commands.

## Requirements

### Requirement: The request is read back out of the pull request's description

The system SHALL read the request back from the description of the pull request it opened, taking what follows its marker and leaving out the `Requested-by` line, and SHALL return any other description as written, saying that it is not its own.

#### Scenario: A description this system wrote

- **WHEN** a description starts with the system's marker and ends with a `Requested-by` line
- **THEN** the request is what lies between them, and the description is reported as the system's own

#### Scenario: Any other description

- **WHEN** a pull request's description does not start with the marker
- **THEN** it is returned as it is, and reported as not the system's own

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

### Requirement: The documents are read from the work's branch

The system SHALL read the request, spec, design and plan of a piece of work from its branch with the App's token, skipping the ones not written yet.

#### Scenario: Only a spec so far

- **WHEN** only the request and the spec exist
- **THEN** those two are returned

### Requirement: Agents speak on the pull request as the team members they stand in for

The system SHALL post each agent's contribution as a comment headed with its role as a person's title (spec writer, spec reviewer, architect, design reviewer, planner, developer, code reviewer, checks), marked so that it can be read back as that speaker, and SHALL read any other comment back as a person's.

#### Scenario: A reviewer

- **WHEN** the spec reviewer finishes
- **THEN** a comment headed "Spec reviewer" carries its verdict and issues

#### Scenario: A person on GitHub

- **WHEN** a person writes a comment on the pull request
- **THEN** it is read back as that person speaking

### Requirement: One progress comment tells the whole story at a glance

The system SHALL keep exactly one progress comment, edited in place after every step, with a row per step of the course saying what happened there (written, approved, asked for changes, passed, failed, waiting for CI, with rounds), where the work is now, and how it ended.

#### Scenario: A loop

- **WHEN** the spec reviewer asked for changes once and then approved
- **THEN** its row shows both, in order

#### Scenario: A person is needed

- **WHEN** the work waits at the spec approval
- **THEN** the progress comment says it waits for a person and for what

#### Scenario: Every step says when

- **WHEN** a step has finished
- **THEN** its entry in the progress comment carries the date and time it happened in UTC, and the foot of the comment says when the work last did anything; entries recorded before times were kept are shown without one

#### Scenario: The CI is still running

- **WHEN** the checks report that the repository's CI has not finished
- **THEN** the progress comment's row for the checks says it is waiting for CI, with a waiting symbol

### Requirement: The pull request stays a straight line when the flow circles back

The system SHALL, when a step starts, mark as outdated the announcements of waits that are over, and when it starts again because the flow circled back to its phase (a reviewer or a failed check sent the work back, or a person asked for changes), also mark as outdated what the agents said from that phase on, including its own earlier comment, while what the agents said before that phase still holds. It SHALL NOT touch the progress comment or anything a person wrote, SHALL NOT hide a comment of another work, and SHALL NOT change anything when a step only looks at the CI again. It SHALL leave the comments in place and readable, so that the interface still shows the whole conversation, and a failure to mark a comment SHALL NOT stop the work.

#### Scenario: The reviewer sent the work back

- **WHEN** the code review asked for changes and the developer starts again
- **THEN** the developer's, the checks' and the reviewer's earlier comments are outdated, and the spec, design and plan comments are not

#### Scenario: A wait that is over

- **WHEN** a person answered a wait and the next step starts
- **THEN** the announcement of that wait is outdated

#### Scenario: Another look at the CI

- **WHEN** a step starts only to look at the CI again
- **THEN** nothing is marked

#### Scenario: GitHub refuses

- **WHEN** marking a comment fails
- **THEN** the step runs anyway

### Requirement: A gate announcement links what to judge

The system SHALL link, in the announcement of a wait, the document the person is asked to judge.

#### Scenario: The spec approval

- **WHEN** the work waits at the spec approval
- **THEN** the announcement links the spec file on the work's branch

#### Scenario: Work on an existing pull request

- **WHEN** work on a pull request that already exists waits at the merge
- **THEN** the announcement links no document, because that work writes no spec, design or plan

### Requirement: The title is set at the first step and refreshed when the work reaches the merge

The system SHALL give the pull request the title it is given when opening it, and retitle the existing one when asked to publish again with another, so that the title reflects what the work actually did.

#### Scenario: Retitling

- **WHEN** the work reaches the merge with a different proposed title
- **THEN** the pull request is retitled
