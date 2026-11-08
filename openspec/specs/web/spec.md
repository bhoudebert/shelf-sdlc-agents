# Web

## Purpose

The product: a person signs in with GitHub, sees the work of their repositories, starts work at any step, and decides at gates, from a server-rendered interface that updates live.

## Requirements

### Requirement: People sign in with GitHub and only people on the list get in

The system SHALL send a visitor through GitHub's OAuth flow with a state value that comes back unchanged, SHALL refuse a callback that did not start here, and SHALL tell a person who is not on the access list so without opening a session.

#### Scenario: A listed person

- **WHEN** a person on the access list completes the sign-in
- **THEN** a session starts and they reach the board

#### Scenario: A forged callback

- **WHEN** the callback carries a state that does not match the cookie
- **THEN** it is refused

### Requirement: Installing the App lands on the board

The system SHALL answer the address GitHub redirects to after the App is installed by sending the person to the board, which asks them to sign in first if they are not.

#### Scenario: Right after installing

- **WHEN** GitHub redirects a person to the setup address after installation
- **THEN** they arrive on the board, not on an error

### Requirement: The health check reports the build

The system SHALL answer the health check with its status and the git revision of the build.

#### Scenario: Health

- **WHEN** the health check is requested
- **THEN** it answers with the status and the revision

### Requirement: Sessions are signed cookies without a user table

The system SHALL identify a session by a random id in a signed, HttpOnly, SameSite=Lax cookie, keep the person's GitHub token only on the server, and expire the session when the token would.

#### Scenario: Expiry

- **WHEN** eight hours pass
- **THEN** the session is gone

#### Scenario: Signing out

- **WHEN** a person signs out
- **THEN** their session ends and protected pages redirect to sign-in

### Requirement: State-changing requests from other origins are refused

The system SHALL refuse a POST whose Origin header is not the instance's own.

#### Scenario: A cross-site form

- **WHEN** a form on another site posts to the start page
- **THEN** the request is refused

### Requirement: The board shows the person's repositories' work, live

The system SHALL show every piece of work of the repositories the person can see, with its phase and what it waits for, and SHALL push changes with server-sent events; a person with no repository SHALL be shown how to install the App.

#### Scenario: No repository

- **WHEN** the App is installed on none of the person's repositories
- **THEN** the board explains how to install it and links to GitHub

### Requirement: Work starts from a form at any entry point

The system SHALL let a person pick a visible repository, an entry point and the text or pull request number, start the work, and answer a bad request on the form with the reason.

#### Scenario: Starting from a need

- **WHEN** a person submits a need
- **THEN** the work starts and its page opens

#### Scenario: An invisible repository

- **WHEN** a person submits a repository they cannot see
- **THEN** it is answered as not found

### Requirement: The work page shows the timeline and takes decisions

The system SHALL show where the work stands in the pipeline and offer only the decisions that fit what it waits for, and SHALL refuse a decision from someone whose role does not allow it.

#### Scenario: A gate

- **WHEN** the work waits at the spec gate
- **THEN** the page offers approve, request changes, reject and abort

#### Scenario: Without the role

- **WHEN** a person without the required role decides
- **THEN** the decision is refused and the work is unchanged

### Requirement: Webhooks are verified and wake the right work

The system SHALL accept a GitHub webhook only with a valid HMAC signature, signal a closed pull request to its work, and turn a trusted person's `/shelf` comment into a decision.

#### Scenario: A bad signature

- **WHEN** a webhook arrives with a wrong signature
- **THEN** it is refused

#### Scenario: A merge

- **WHEN** the pull request of a piece of work is merged
- **THEN** the work is told it was merged

### Requirement: A repository whose configuration is invalid is reported on the page

The system SHALL answer a start or a decision on a repository with an invalid configuration file with the reason on the form or panel, not with a server error.

#### Scenario: A bad file

- **WHEN** a person starts work on a repository whose `.shelf/config.toml` has an unknown key
- **THEN** the start form shows the reason and nothing starts

### Requirement: The board puts what needs a person first

The system SHALL group the board by what is asked of the person (needs you, running, finished), show each piece of work's status with a word and a glyph and not by colour alone, and keep a chosen filter when the board updates live.

#### Scenario: Work waiting for a person

- **WHEN** one piece of work waits for a decision and another runs
- **THEN** the waiting one is listed first, under its own heading

### Requirement: The pipeline timeline is readable without colour

The system SHALL show every phase of the pipeline on the work page with a distinct glyph and word for done, in progress, waiting, stopped and not yet reached, and SHALL mark the current phase for assistive technology.

#### Scenario: A stopped piece of work

- **WHEN** work was aborted at the design phase
- **THEN** earlier phases show as done, the design phase as stopped and later phases as not reached

### Requirement: Destructive decisions are set apart and confirmed

The system SHALL show the primary decision alone and prominent, ask for a note only next to the request for changes, and set reject and abort apart behind a confirmation.

#### Scenario: Aborting

- **WHEN** a person chooses abort
- **THEN** they are asked to confirm before the decision is sent

### Requirement: The interface works without third-party requests or scripts

The system SHALL serve every script, style and font from the instance itself, make no request to another origin, and remain usable for reading when scripts do not run.

#### Scenario: Offline from the internet

- **WHEN** the instance has no outbound access
- **THEN** every page renders completely

### Requirement: Anything meant to be copied can be copied in one action

The system SHALL offer a button that copies a marked block of text to the clipboard and confirms it, and SHALL leave the text selectable when the clipboard is not available.

#### Scenario: Copying the credentials

- **WHEN** a person presses the copy button next to the credentials
- **THEN** the whole block is copied and the button says so briefly
