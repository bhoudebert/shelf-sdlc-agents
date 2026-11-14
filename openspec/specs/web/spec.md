# Web

## Purpose

The product: a person signs in with GitHub, sees the work of their repositories, starts work at any step, and decides at gates, from a server-rendered interface that updates live.

## Requirements

### Requirement: People sign in with GitHub and only people on the list get in

The system SHALL send a visitor through GitHub's OAuth flow with a state value that comes back unchanged, SHALL refuse a callback that did not start here, and SHALL tell a person who is not on the access list so without opening a session.

#### Scenario: A listed person

- **WHEN** a person on the access list completes the sign-in
- **THEN** a session starts and they reach the board

#### Scenario: A member of a listed organisation

- **WHEN** a person who is not listed by name but belongs to a listed organisation signs in
- **THEN** they are let in, and a refusal for anyone else says that an organisation membership must be public or readable by the App

#### Scenario: A refusal when organisations are listed

- **WHEN** a person is refused on an instance whose access list names organisations
- **THEN** the page says how a membership becomes visible: public, or the App installed on the organisation by an owner (each with a link to GitHub that opens in a new tab: the People page of every listed organisation, and the App's installation page), or a listing by name by the operator

#### Scenario: A forged callback

- **WHEN** the callback carries a state that does not match the cookie
- **THEN** it is refused

### Requirement: The web service uses the access list in force now

The system SHALL decide who may sign in, who is an administrator and who may decide on a piece of work from the access list as it is when the question is asked, so that an edit of `shelf.toml` applies to the next sign-in and the next decision without a restart.

#### Scenario: A person added while the service runs

- **WHEN** an operator adds a person to the access list after the service started
- **THEN** that person can sign in on their next attempt

#### Scenario: An administrator removed

- **WHEN** an operator removes an administrator from the list
- **THEN** their next request to an administrator page is refused

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

#### Scenario: Adding another repository

- **WHEN** a person who already has repositories opens the board or the start form
- **THEN** a link to the App's installation page on GitHub, opening in a new tab, lets them add one more

### Requirement: The form offers to work on a pull request and says what that allows

The system SHALL offer on the start form, beside the read-only review, an entry that changes an existing pull request, asking for its number and for what to do to it, and SHALL say beside it that the agents change that branch as asked, wait for its CI and may force-push it when a rebase needs it, only if nobody pushed to it meanwhile.

#### Scenario: The preview follows the choice

- **WHEN** a person chooses to work on a pull request
- **THEN** the preview lists implementation, checks, code review and the merge as the steps the work goes through, and the earlier ones as skipped

#### Scenario: The two pull request entries

- **WHEN** the form is shown
- **THEN** it offers to review a pull request, read only, and to work on one, each asking for its number

### Requirement: The form lets a person pin other repositories to read, and says a link is enough

The system SHALL offer on the start form an optional field for other public repositories to read as reference, and SHALL say that it need not be filled in because a link in the request is read too, that the copies are plain read-only files, that nothing in them is run, and that at most three are read, and SHALL answer a listed repository that cannot be read with the form again and the reason.

#### Scenario: The field

- **WHEN** the form is shown
- **THEN** the field is there with a hint that a link in the request is enough

#### Scenario: A repository that cannot be read

- **WHEN** a listed repository is private
- **THEN** the form is shown again with that reason and nothing starts

### Requirement: The form offers existing material as an optional field

The system SHALL offer on the start form an optional field for existing material (an issue, a pull request or a file of the repository), SHALL say that nothing in it is required and that the text box may be used instead or as well, and SHALL answer a reference that cannot be used with the form again and the reason.

#### Scenario: Optional

- **WHEN** the form is shown
- **THEN** the field is there with a hint that it can be left empty

#### Scenario: A reference that cannot be used

- **WHEN** the reference names a file the repository does not have
- **THEN** the form is shown again with that message and nothing starts

### Requirement: A review of a pull request that is not there is refused on the form

The system SHALL answer a start form that asks to review a pull request the chosen repository does not have with the form again and a message naming the repository and the number, and SHALL NOT start anything.

#### Scenario: Wrong repository

- **WHEN** the form asks to review #2 of a repository that has no #2
- **THEN** the form is shown again with that message and no work exists

### Requirement: Work starts from a form at any entry point

The system SHALL let a person pick a visible repository, an entry point and the text or pull request number, start the work, and answer a bad request on the form with the reason.

#### Scenario: Starting from a need

- **WHEN** a person submits a need
- **THEN** the work starts and its page opens

#### Scenario: An invisible repository

- **WHEN** a person submits a repository they cannot see
- **THEN** it is answered as not found

### Requirement: The start form says how much the run may do without a person

The system SHALL show on the start form three choices (wait for approval of the spec, review the design, go on when a spec or design review cannot settle) preset from the chosen repository's policy, SHALL change the preset when another repository is chosen, SHALL say beside them that fewer stops mean more autonomy, less control and potentially less quality, and SHALL warn visibly when a choice removes a stop, and SHALL start the work with what the form shows, not with the repository's file.

#### Scenario: The repository's defaults

- **WHEN** a person opens the form for a repository whose policy turns the spec approval off
- **THEN** the spec approval choice is unchecked and the others show the repository's values

#### Scenario: Another repository

- **WHEN** the person picks another repository
- **THEN** the three choices take that repository's values

#### Scenario: A stop removed

- **WHEN** any choice removes a stop
- **THEN** a warning says what is no longer asked and that the code review, the checks and the merge remain

#### Scenario: Compact, grouped boxes

- **WHEN** the start form is shown at a phone, a tablet or a desktop width, in the light or the dark theme
- **THEN** the three choices are small checkboxes in one grouped list, each beside its label and its help text, never stretched to the width of the form, and a removed stop shows its warning at the width of the list

#### Scenario: What the form shows is what runs

- **WHEN** a person unchecks the spec approval and checks the deadlock choice, then starts
- **THEN** the work has no spec approval and goes on past a deadlock, whatever the repository's file says

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

### Requirement: An administrator can close work that can no longer be steered

The system SHALL let an administrator close a piece of work from its page without running its history, and SHALL answer a decision the engine cannot take with an explanation, never a server error.

#### Scenario: Work started by an older release

- **WHEN** an administrator closes work whose history can no longer be run
- **THEN** it ends at once and the board shows it as aborted, not as unreadable

#### Scenario: A decision on such work

- **WHEN** a person rejects or aborts work the engine cannot take a message for
- **THEN** the page says why and that an administrator can close it

#### Scenario: Not an administrator

- **WHEN** anyone else asks to close work
- **THEN** the request is refused and the button is not shown

### Requirement: The administrator's page checks the App on GitHub

The system SHALL show administrators, on the admin page, the findings about the GitHub App's own setup, each with what to change, or one finding saying why the App could not be checked, and SHALL show nothing when no inspector is configured.

#### Scenario: Something is wrong

- **WHEN** an administrator opens the page and the App is not subscribed to the events the system needs
- **THEN** a finding marked as to fix names the boxes to tick

#### Scenario: GitHub refuses

- **WHEN** GitHub cannot be asked about the App
- **THEN** one finding says the App could not be checked and why

#### Scenario: A second person cannot sign in

- **WHEN** the administrator opens the check
- **THEN** it says that a 404 on sign-in for a second person means the App is private, and that Make public on the App's Advanced tab fixes it

### Requirement: The setup page says what the App may do and what it may not

The system SHALL list on the setup page the permissions the App is given and say that Workflows is left off on purpose, and why.

#### Scenario: The setup page

- **WHEN** a person opens the setup page
- **THEN** the permissions are listed and a note says Workflows is off because changed workflows run with the repository's secrets

### Requirement: A repository whose configuration is invalid is reported on the page

The system SHALL answer a start or a decision on a repository with an invalid configuration file with the reason on the form or panel, not with a server error.

#### Scenario: A bad file

- **WHEN** a person starts work on a repository whose `.shelf/config.toml` has an unknown key
- **THEN** the start form shows the reason and nothing starts

### Requirement: A row of the board says what the work is

The system SHALL show on each row of the board and at the head of the work's page a line taken from the request to tell one piece of work from another (the first line of the request, shortened), with the repository, the pull request's number as a link to it when there is one, the entry and the requester; work started before the line was kept SHALL be shown under its repository as before.

#### Scenario: A titled row with a pull request

- **WHEN** work has a kept title and a pull request
- **THEN** its row shows the title, the repository, the pull request number linking to GitHub, the entry and the requester

#### Scenario: Older work

- **WHEN** work has no kept title
- **THEN** its row is headed by its repository

### Requirement: The board and the work page say when things happened

The system SHALL show on each row of the board how long ago the work last did anything, with the exact date and time in UTC as its tooltip, and on the work page's timeline when something last happened at each step, and SHALL show nothing for work that predates times.

#### Scenario: A running work

- **WHEN** the work's last action was twelve minutes ago
- **THEN** its row says 12 min ago and the exact time is in the tooltip

#### Scenario: A step of the timeline

- **WHEN** the design step last did something at 09:12 UTC on 8 November
- **THEN** the timeline shows that date and time under the step

### Requirement: The board puts what needs a person first

The system SHALL group the board by what is asked of the person (needs you, running, finished), show each piece of work's status with a word and a glyph and not by colour alone, and keep a chosen filter when the board updates live.

#### Scenario: Work waiting for a person

- **WHEN** one piece of work waits for a decision and another runs
- **THEN** the waiting one is listed first, under its own heading

### Requirement: The interface is dark unless the person chose light

The system SHALL show the interface, and the project's site, in the dark theme by default, whatever the system's colour preference, and in the light theme only after the person chose it with the toggle, which SHALL remember the choice in the browser.

#### Scenario: A first visit on a light system

- **WHEN** a person with no remembered choice opens a page on a system set to light
- **THEN** the page is dark

#### Scenario: A chosen light theme

- **WHEN** the person has chosen light with the toggle
- **THEN** the next page is light from the first paint

#### Scenario: Without script

- **WHEN** a page is opened with scripts turned off
- **THEN** it is dark

### Requirement: Decoration never competes with reading

The system SHALL keep its decoration (the star field, the orbits, the illustrations and the mascot that stands for the agents) behind or beside the content, never on top of text and hidden from assistive technology, with the words around it saying the same thing; SHALL keep every text and its background at a WCAG AA contrast in both themes, with the dark theme calm (body text between 10:1 and 14:1, no glow); and, where the board shows how far a piece of work has gone, each state of a phase SHALL differ by shape as well as colour.

#### Scenario: The mascot tells the state of a piece of work

- **WHEN** a piece of work is running, waits for a person, failed at a step, was merged, or was closed
- **THEN** its status shows the mascot at work, waving, puzzled, celebrating or asleep, next to the words that say the state

#### Scenario: The dark theme stays calm

- **WHEN** the person chose the dark theme
- **THEN** the body text stands at a moderate contrast on a grey-blue ground, without glow or nebula

#### Scenario: A stopped piece of work on the board

- **WHEN** a piece of work was aborted at the design phase
- **THEN** its row shows the earlier phases as filled nodes, the design phase as a diamond and the later phases as hollow nodes, next to the word for its phase

#### Scenario: Reduced motion

- **WHEN** the person's system asks for reduced motion
- **THEN** nothing on the page moves, the mascot included

### Requirement: The pipeline timeline is readable without colour

The system SHALL show every phase of the pipeline on the work page with a distinct glyph and word for done, in progress, waiting, stopped and not yet reached, and SHALL mark the current phase for assistive technology.

#### Scenario: A stopped piece of work

- **WHEN** work was aborted at the design phase
- **THEN** earlier phases show as done, the design phase as stopped and later phases as not reached

### Requirement: Saying what should change is comfortable

The system SHALL give the box where a person says what should change room to write: a tall box that grows with the text, a column wide enough for it, a line saying that the words are what the agents receive, a draft kept in the browser until the decision is sent, and Ctrl+Enter to send.

#### Scenario: A long note

- **WHEN** a person types a long note into the box
- **THEN** the box grows with it up to most of the screen's height instead of scrolling inside a few lines

#### Scenario: Leaving by accident

- **WHEN** a person has typed a note, then reloads the page or comes back later
- **THEN** the text is still in the box until the decision is sent

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

#### Scenario: Reading a stack trace

- **WHEN** an administrator asks for a workflow's stack trace, a query named in the path, while writing is off
- **THEN** it passes, and cancelling or terminating still does not

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

### Requirement: A changed stylesheet or script is never served from an old copy

The system SHALL address each static file of its pages with a fingerprint of the file's content, so that a browser fetches a file again as soon as it changes and never lays out a new page with an old stylesheet.

#### Scenario: A page's assets

- **WHEN** a page is served
- **THEN** its stylesheet and scripts are addressed with a fingerprint of their content

#### Scenario: The first-run page

- **WHEN** the setup page is served
- **THEN** its assets carry the same fingerprint and are served

### Requirement: The request is shown above the conversation

The system SHALL show, above the conversation on the work page and open by default, what was asked for: the request the pull request was opened with, without the marker and the `Requested-by` line that the system wrote around it, rendered for reading and never as active content; for a pull request this system did not open it SHALL show the pull request's own description under that name.

#### Scenario: Work this system opened

- **WHEN** the pull request was opened by this system from a request
- **THEN** the page shows "The request" with that text, and not the marker nor the requester line

#### Scenario: Someone else's pull request

- **WHEN** the work reviews or changes a pull request that this system did not open
- **THEN** the page shows "Pull request description" with the description as written

### Requirement: The conversation of the pull request is shown on the work page, read only

The system SHALL show on the work page, beside the documents, the comments of the work's pull request as a conversation that can be folded and is folded by default, newest first and limited to the latest thirty, each comment numbered by its place in the whole conversation (who spoke, whether an agent, a person or Shelf itself, what they said rendered for reading, and when, with a link to the comment on GitHub), an agent's comment folded behind a one-line summary (its number, who, when, and its verdict or else its first line) and a person's shown open, keeping what a person opened when the page refreshes, without the one progress comment that the timeline already tells, never turning anything a comment contains into active content, and SHALL say so when the pull request is not open yet or GitHub cannot be reached. The page SHALL NOT take comments: people reply on GitHub or decide with the buttons, and agents act only on the `/shelf` commands.

#### Scenario: A pull request with a conversation

- **WHEN** the pull request has an agent's report and a person's comment
- **THEN** both are listed with their speaker, their time in UTC and a link to the comment, and the progress table is not

#### Scenario: Newest first, folded

- **WHEN** the pull request has a spec writer's report, a reviewer's verdict and a person's comment
- **THEN** the person's comment comes first, and each agent's report is a folded line such as `1. Spec writer on 9 Nov 09:12 UTC — Verdict: escalate` that opens to its detail

#### Scenario: Hostile content

- **WHEN** a comment contains a script tag
- **THEN** it is shown as text and nothing runs

#### Scenario: Before the pull request opens

- **WHEN** the work has no pull request yet
- **THEN** the page says the conversation starts when the pull request opens

#### Scenario: Someone else's repository

- **WHEN** a person asks for the conversation of a work on a repository they cannot see
- **THEN** the answer is not found

### Requirement: The documents of a piece of work are shown on its page

The system SHALL show on the work page the request, the spec, the design and the plan as the agents write them, rendered for reading, with the one the work is at open and the others folded, never turning anything the documents contain into active content, and answering a document it cannot load with a message and a retry.

#### Scenario: At the spec approval

- **WHEN** the work waits at the spec approval
- **THEN** the spec is open on the page beside the decision buttons

#### Scenario: Work on an existing pull request

- **WHEN** the work happens on a pull request that already exists
- **THEN** the documents pane says that it writes no spec, design or plan, instead of promising them

#### Scenario: A wide window

- **WHEN** a document is open in a wide window
- **THEN** its text, lists, tables and code use the whole width of the panel (the page keeps its one principal column) instead of a narrow column inside it

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

### Requirement: An admin page shows what GitHub has sent and the instance's facts

The system SHALL give administrators, and only them, a page listing the recent webhook deliveries newest first (time, event, repository, what became of it, detail and GitHub's delivery id) beside the key facts of the instance (revision, address, mode, App, whether a model credential is set, access lists), never showing a secret, and SHALL say what to check when nothing has arrived.

#### Scenario: Deliveries

- **WHEN** an administrator opens the admin page after a refused and an ignored delivery
- **THEN** both are listed, the refusal marked, newest first

#### Scenario: Nothing has arrived

- **WHEN** no webhook has arrived
- **THEN** the page says to comment on a pull request and check the App's recent deliveries

#### Scenario: Not an administrator

- **WHEN** an ordinary person asks for the page
- **THEN** it is refused and the navigation does not offer it
