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

The system SHALL accept a GitHub webhook only with a valid HMAC signature, signal a closed pull request to its work, and turn a `/shelf` comment into a decision only when its author is on the operator's access list (a listed user or administrator, or a member of a listed organisation that owns the repository).

#### Scenario: A bad signature

- **WHEN** a webhook arrives with a wrong signature
- **THEN** it is refused

#### Scenario: A comment from someone not on the access list

- **WHEN** a `/shelf approve` comment is written by a person the access list does not name
- **THEN** it is acknowledged but no decision reaches the work, and the webhook log records it as refused

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

### Requirement: The credentials page hands over the private key as a file

The system SHALL show the credentials after registration with the private key kept out of the environment lines, and SHALL offer the key as a file to download, so that nothing has to be pasted or escaped.

#### Scenario: After registering

- **WHEN** the credentials are shown
- **THEN** the environment block lists the five values without the key, and a download offers the key as `github-app.pem`

### Requirement: Administrators see every run

The system SHALL show administrators the work of every repository on the board and let them open any piece of work; other people see only what is on repositories they can open.

#### Scenario: An ordinary person

- **WHEN** an ordinary person asks for work on a repository they cannot open
- **THEN** it is not found

### Requirement: Temporal's interface is served to administrators behind the sign-in

The system SHALL serve Temporal's own interface under `/temporal`, only to signed-in administrators, read-only unless the operator allows writes, always allowing workflow queries, refusing a change from another origin, never forwarding the session cookie or any credential upstream, and linking each work page to its workflow for administrators.

#### Scenario: An administrator reads

- **WHEN** an administrator opens a path under `/temporal`
- **THEN** Temporal's answer is returned, not cached, and nothing of the session is sent upstream

#### Scenario: Anyone else

- **WHEN** an ordinary person or a visitor asks for `/temporal`
- **THEN** the person is refused and the visitor is sent to sign in

#### Scenario: Changing a workflow

- **WHEN** an administrator tries to terminate or signal a workflow from there
- **THEN** it is refused unless the operator turned writing on, while a query always passes

#### Scenario: Temporal is down

- **WHEN** Temporal's interface does not answer
- **THEN** the proxy answers with a gateway error, not a crash

### Requirement: The interface warns when agents cannot reach a model

The system SHALL show a prominent warning on the board and the start page while no model credential is set, telling an administrator what to set and where and telling anyone else to ask the administrator.

#### Scenario: No credential

- **WHEN** the instance has no model credential and a person opens the board
- **THEN** the warning explains that agent steps will fail with "Not logged in"

#### Scenario: A credential is set

- **WHEN** a model credential is set
- **THEN** no warning is shown

### Requirement: A live board does not hammer GitHub

The system SHALL reuse for a minute what GitHub said about a person's repositories and identity, so that open boards refreshing every few seconds cost one lookup a minute per person, never sharing an answer between two people.

#### Scenario: A board left open

- **WHEN** a board refreshes many times within a minute
- **THEN** GitHub is asked once

#### Scenario: Two people

- **WHEN** two people open the board
- **THEN** each gets their own lookup

### Requirement: The documents of a piece of work are shown on its page

The system SHALL show on the work page the request, the spec, the design and the plan as the agents write them, rendered for reading, with the one the work is at open and the others folded, never turning anything the documents contain into active content, and answering a document it cannot load with a message and a retry.

#### Scenario: At the spec approval

- **WHEN** the work waits at the spec approval
- **THEN** the spec is open on the page beside the decision buttons

#### Scenario: Hostile content

- **WHEN** a document contains a script tag or a javascript link
- **THEN** it is shown as text and nothing runs

### Requirement: Refreshing never gets in the way of using the page

The system SHALL refresh the work panel and the documents without redrawing them when nothing changed, answering such a refresh with no content, SHALL not refresh them while the pointer is over them, focus or a text selection is in them, and SHALL hold a board update while the pointer is over the list and apply it when the pointer leaves, and SHALL never hold back a decision.

#### Scenario: Nothing changed

- **WHEN** the panel refreshes and the work is unchanged
- **THEN** the answer has no content and the page is not redrawn

#### Scenario: About to click

- **WHEN** the pointer is over the decision buttons
- **THEN** the panel does not refresh under it

### Requirement: Links that leave the application open in a new tab

The system SHALL open every link to GitHub or to another site in a new tab without giving it access to the page, so that the interface stays where it is; only the sign-in, which returns to the same tab, stays in it.

#### Scenario: The pull request

- **WHEN** a person follows the pull request link
- **THEN** it opens in a new tab and the work page remains open

### Requirement: Administrators are told whether GitHub's webhooks arrive and what became of them

The system SHALL remember the most recent webhook deliveries and show administrators, on the board, whether any has arrived since it started, whether the last one was refused for a wrong signature, whether a command on a pull request could not be applied and why, or that the last one was applied, and SHALL include the last delivery in the health check; ordinary people see none of it.

#### Scenario: Nothing has arrived

- **WHEN** no webhook has reached the instance
- **THEN** the board tells the administrator that commands are only noticed by the periodic check and what to look at on the App

#### Scenario: A wrong secret

- **WHEN** a webhook arrives signed with another secret
- **THEN** the board says the signature does not match the configured secret and what to do

#### Scenario: A command that could not be applied

- **WHEN** a command from a pull request names work this instance does not know
- **THEN** the board says it was not applied and why, instead of nothing happening
