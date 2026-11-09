# Work requests

## Purpose

Let a signed-in person start work, decide for it and see it, on the repositories they can access.

## Requirements

### Requirement: Work starts only on a repository the person can see

The system SHALL start work only on a repository that the app is installed on and that the person can access, and SHALL answer "not found" for any other.

#### Scenario: A repository the person cannot see

- **WHEN** a person starts work on a repository outside their visible repositories
- **THEN** the request is refused as not found, revealing nothing about the repository

### Requirement: A start request must match the entry point

The system SHALL refuse a start request whose entry point the repository disabled, whose text is empty (except for a pull-request review), or that reviews a pull request without its number.

#### Scenario: An empty need

- **WHEN** a person submits a need that is empty
- **THEN** the request is refused as invalid

#### Scenario: Reviewing a pull request

- **WHEN** a person starts a pull-request review with a pull request number and no text
- **THEN** the work starts

### Requirement: Work on a pull request starts only on one that can be changed

The system SHALL, before starting work on an existing pull request, refuse a pull request that is closed, one that comes from a fork (whose branch the App cannot push to), and a request that says nothing to do, each with a message that says why.

#### Scenario: A fork

- **WHEN** a person asks to work on a pull request from a fork
- **THEN** nothing starts and the message says the App cannot push to its branch

#### Scenario: A closed pull request

- **WHEN** the pull request is closed
- **THEN** nothing starts and the message says it is closed

#### Scenario: Nothing to do

- **WHEN** the instruction is empty
- **THEN** nothing starts

### Requirement: Work may read other public repositories as reference

The system SHALL let a piece of work read up to three other public repositories as reference material, those a person lists on the start form (each as `owner/name`, with an optional `@` branch, tag or commit and an optional `:` folder, or as an address on GitHub) and those a request links to in its own text (a repository, a folder or a file of it, not an issue, a pull request or another kind of address), so that a request such as "implement the CI like https://github.com/foo/bar" needs nothing more. It SHALL refuse a listed repository that is missing or private with the reason, and SHALL leave out a linked one that cannot be read, since a link to a private repository is only a mention. It SHALL never read the repository the work is on this way, never read one twice, and SHALL show on the work's page which repositories it reads. A request that names none SHALL work exactly as before.

#### Scenario: A link in the request

- **WHEN** the request says to do something like a public repository and gives its address
- **THEN** the work reads that repository as reference without any other field being filled

#### Scenario: A private repository

- **WHEN** a listed repository is private
- **THEN** the start is refused saying so, while a private repository only linked in the text is left out

#### Scenario: More than three

- **WHEN** a person lists more than three
- **THEN** the start is refused

### Requirement: Work may start from existing material, always optionally

The system SHALL accept, with any start, an optional reference to existing material of the same repository: an issue or pull request (`#12` or its address) or a file (a path, or the address of a file), SHALL make what it says the request, said where it came from and followed by whatever the person typed, and SHALL work as before when no reference is given, so that material that does not exist never blocks a start. It SHALL use only what people with write access wrote, refuse an address that belongs to another repository, a path that climbs out of the repository, a folder, a file that is not text and one longer than 100 KB, each with a message that says why, and SHALL accept an empty text when a reference is given.

#### Scenario: A file and a note

- **WHEN** a person starts at the design with `docs/specs/loyalty.md` and a sentence of their own
- **THEN** the request is that file, headed by where it came from, followed by their sentence

#### Scenario: Nothing to point at

- **WHEN** a person gives no reference
- **THEN** the text they typed is the request, as before

#### Scenario: An outsider's issue

- **WHEN** the issue was written by someone without write access
- **THEN** the start is refused and says to paste the text they trust instead

#### Scenario: Another repository

- **WHEN** the address belongs to another repository
- **THEN** the start is refused and names both repositories

#### Scenario: A reference that is not one

- **WHEN** the reference is longer than five hundred characters, or an address that is not an issue, a pull request or a file of GitHub
- **THEN** it is refused at once, without being matched against any pattern that a crafted text could slow down

### Requirement: A review starts only on a pull request the repository has

The system SHALL, before starting a review of a pull request, ask GitHub as the person whether the chosen repository has that pull request, and SHALL refuse the start with a message naming the repository and the number when it does not, so that a work is never started on the wrong repository and left to fail at its first step.

#### Scenario: A number the repository does not have

- **WHEN** a person asks to review pull request 2 of a repository that has none
- **THEN** nothing starts and the message says that repository has no pull request #2 and to check the repository

#### Scenario: An existing pull request

- **WHEN** the repository has the pull request
- **THEN** the work starts

### Requirement: Decisions are checked against the person's role

The system SHALL deliver a decision to the work only if the person may decide at the phase the work waits at, and SHALL refuse it otherwise without changing the work.

#### Scenario: A person without the role

- **WHEN** a person without the required role approves a gate
- **THEN** the decision is refused and the work is unchanged

### Requirement: The board shows what the person can see

The system SHALL list the work of the repositories the person can see, and no other.

#### Scenario: Two repositories

- **WHEN** work exists on a visible and on an invisible repository
- **THEN** the board lists only the work on the visible one

### Requirement: Administrators see the work of every repository

The system SHALL list the work of every repository for an administrator, and only the work of repositories they can see for anyone else.

#### Scenario: An administrator

- **WHEN** an administrator asks for the board
- **THEN** work on repositories they cannot open is listed too

### Requirement: The board's view of a work carries a line of its request

The system SHALL give the view of a piece of work, in addition to its repository, requester, entry and phase, a short line of its request (empty for work that has none), so that every list of work can say what each one is.

#### Scenario: A work with times

- **WHEN** a work has acted
- **THEN** its view carries when it last did anything and when it last did something at each phase

#### Scenario: A work with a line

- **WHEN** a work was started with a request
- **THEN** its view carries the request's first line

