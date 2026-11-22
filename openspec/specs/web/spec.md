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

The system SHALL show on the start form three choices, each worded so that checked means a person is asked or a review is kept (wait for approval of the spec, review the design, stop and ask when a spec or design review cannot settle), preset from the chosen repository's policy, SHALL change the preset when another repository is chosen, SHALL say beside them that fewer stops mean more autonomy, less control and potentially less quality, and SHALL warn visibly when any of them is unchecked, and SHALL start the work with what the form shows, not with the repository's file.

#### Scenario: The repository's defaults

- **WHEN** a person opens the form for a repository whose policy turns the spec approval off
- **THEN** the spec approval choice is unchecked and the others show the repository's values

#### Scenario: Another repository

- **WHEN** the person picks another repository
- **THEN** the three choices take that repository's values, the deadlock choice checked unless the policy goes on past a deadlock

#### Scenario: A stop removed

- **WHEN** any of the three choices is unchecked
- **THEN** a warning says what is no longer asked and that the code review, the checks and the merge remain

#### Scenario: Compact, grouped boxes

- **WHEN** the start form is shown at a phone, a tablet or a desktop width, in the light or the dark theme
- **THEN** the three choices are small checkboxes in one grouped list, each beside its label and its help text, never stretched to the width of the form, and a removed stop shows its warning at the width of the list

#### Scenario: What the form shows is what runs

- **WHEN** a person unchecks the spec approval and the stop at a deadlock, then starts
- **THEN** the work has no spec approval and goes on past a deadlock, whatever the repository's file says

#### Scenario: All checked is fully attended

- **WHEN** a person leaves the three choices checked
- **THEN** the work waits at the spec approval, has its design reviewed and waits at a deadlock


### Requirement: The start form lets a person choose how deep the reviews look for this work

The system SHALL show on the start form two choices, one for the spec review and one for the design review, each of how deep it looks (quick, standard or thorough) with a line on what each means, preset from the chosen repository's `spec_review_depth` and `design_review_depth`, SHALL change the preset when another repository is chosen, and SHALL start the work with what the form shows.

#### Scenario: The repository's default

- **WHEN** a person opens the form for a repository that sets `design_review_depth = "thorough"`
- **THEN** thorough is selected for the design review and the spec review shows the repository's own value

#### Scenario: A choice for this work

- **WHEN** the person selects quick for the design review and starts the work
- **THEN** the work's design review is quick whatever the repository's file says, and its spec review is what the form showed for it

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

### Requirement: The board and the work page say which stops a run does without

The system SHALL keep, when work starts, which stops its run does without a person (the spec approval, the design review, the wait at a deadlock), and SHALL show them in words on the work's row of the board and on its page, as `Unattended: spec, design`, for work that removes any; work that keeps every stop, and work started before this was kept, SHALL show nothing.

#### Scenario: A run that skips two stops

- **WHEN** work was started with the spec approval and the design review removed
- **THEN** its row on the board and its page say `Unattended: spec, design`

#### Scenario: A run that keeps every stop

- **WHEN** work was started with every stop kept
- **THEN** nothing about it is said

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

### Requirement: The admin page shows what the guard has seen

The system SHALL show administrators, on the admin page, a section "Guard" with the number of recorded agent calls, how many the guard stopped or would have stopped, the redactions it made, whether the audit log's chain is intact, and the risk categories that were found most often. The section SHALL say so plainly when the guard is not installed or its log cannot be read, and SHALL NOT stop the rest of the page from showing.

#### Scenario: The guard has recorded calls

- **WHEN** an administrator opens the admin page and the guard reports twelve calls, three of which it would have stopped
- **THEN** the Guard section shows twelve calls and three stopped, and the categories found

#### Scenario: The chain is broken

- **WHEN** the guard reports that the audit log's chain is broken
- **THEN** the section says so as a fault to fix

#### Scenario: No guard

- **WHEN** the guard is not installed or cannot be read
- **THEN** the Guard section says it is not available and the rest of the page is unchanged


### Requirement: The admin page lists what the guard stopped and what the agents read, and suggests a rule

The system SHALL show administrators, in the Guard section, the calls the guard stopped or would have stopped (when, which agent, what, the risks found and the reason), newest first and at most 30, and the hosts the agents fetched with how many times; and SHALL offer, for a stopped call that no rule can free, none, and for the others, a rule for the operator's policy file that would allow it (an exact match of the command) and, for a host, a line that would deny it, shown as text to copy and never applied by the page.

#### Scenario: A stopped call

- **WHEN** the guard reports that it denied a command for `exfil`
- **THEN** the section lists it with its reason, and offers a rule the administrator can copy into the operator's policy file

#### Scenario: A call that is always refused

- **WHEN** the stopped call was a blocked domain or a tamper attempt
- **THEN** the section lists it and offers no rule, saying that no rule can allow it

#### Scenario: Hosts read

- **WHEN** the agents fetched `docs.rs` three times
- **THEN** the section lists `docs.rs` with 3 and offers the line that would deny it

#### Scenario: Nothing is changed by the page

- **WHEN** an administrator reads a suggested rule
- **THEN** no file or policy has changed

### Requirement: An administrator can allow a stopped command or deny a host from the admin page

The system SHALL let an administrator, from the Guard section of the admin page, allow a command the guard stopped (an exact match of the command) and deny a host the agents read, and SHALL record each in the overlay policy file the guard reads, with who did it and when, in a log of the changes that is only ever added to; SHALL accept only a command that appears among the stopped calls the page lists and that no rule is known to be unable to free, and only a host that appears among the hosts the page lists; SHALL list the rules added this way with a way to remove each, and say that a change applies from the next call an agent makes; SHALL refuse the request of anyone who is not an administrator and a request that does not come from the site itself; and SHALL not offer these buttons, and say why, when the instance has no place to keep the overlay.

#### Scenario: Allow a command

- **WHEN** an administrator allows a stopped command from the page
- **THEN** the overlay holds a rule that allows exactly that command, the change log says who and when, and the page lists the rule with a way to remove it

#### Scenario: Deny a host

- **WHEN** an administrator denies `example.org`, which the agents fetched
- **THEN** the overlay lists it under `deny_domains` and the page lists it with a way to remove it

#### Scenario: A command the page did not list

- **WHEN** a request allows a command that is not among the stopped calls on the page
- **THEN** it is refused and nothing is written

#### Scenario: A call that is always refused

- **WHEN** a request allows a command whose call was refused as a blocked domain
- **THEN** it is refused and nothing is written

#### Scenario: Not an administrator

- **WHEN** a signed-in person who is not an administrator sends the request
- **THEN** it is refused and nothing is written

#### Scenario: Removing a rule

- **WHEN** an administrator removes a rule added from the page
- **THEN** the overlay no longer holds it and the change log says who removed it and when

#### Scenario: No place for the overlay

- **WHEN** the instance has no overlay location
- **THEN** the page shows the text to copy as before and says that applying it from here is not set up

### Requirement: Closing a work from its page also closes the pull request it opened

The system SHALL, when an administrator closes a work from its page, also close the pull request that work opened (with a comment saying who closed it), unless the work was a review of, or work on, a pull request someone else opened; and SHALL log and ignore a failure to close the pull request, so that the work is still closed.

#### Scenario: A stuck work is closed

- **WHEN** an administrator closes a work whose draft pull request is open
- **THEN** the work is closed and its pull request is closed with a comment

#### Scenario: GitHub refuses

- **WHEN** closing the pull request fails
- **THEN** the work is still closed and the page goes back to the board

### Requirement: The work page shows what the agents used

The system SHALL show on the page of a piece of work a table of what each agent step used (agent, round, turns, time, tokens read and written, cache, cost), the totals of each agent with its number of rounds, and the total of the work, and SHALL say plainly when nothing was reported, as for work that predates it, without hiding the rest of the page.

#### Scenario: A work with rounds

- **WHEN** a person opens the page of a work whose spec writer ran three rounds
- **THEN** the table lists each of its steps with its round and the spec writer's total shows three rounds and what they cost together

#### Scenario: Older work

- **WHEN** the work predates usage
- **THEN** the section says that nothing was recorded for it and the rest of the page is unchanged

### Requirement: The work page shows who decided what with the work's documents

The system SHALL show on the page of a piece of work, after its other documents and with the same care (rendered as text, never as markup), the log of the decisions people made on it (who, what, when and in which role), so that a reviewer sees who approved what without leaving the page; and SHALL show nothing for work that has no decisions yet or predates the log.

#### Scenario: A work with decisions

- **WHEN** a person opens the page of a work whose branch holds a decision log
- **THEN** a Decisions document lists each decision with who made it and when, after the plan

#### Scenario: A work without

- **WHEN** the work has no decision log
- **THEN** the page lists no Decisions document and the others are unchanged

#### Scenario: Markup in a note

- **WHEN** a person's note in the log contains HTML
- **THEN** the page shows it as text


### Requirement: Rejecting or aborting from the work page closes the pull request, whatever release the work started under

The system SHALL, when a person rejects or aborts a piece of work from its page and the decision is accepted, also close the pull request that work opened (with a comment saying who ended it and how), whichever release the work started under, so that work started before the workflow closed pull requests is closed too; SHALL leave alone a pull request the work did not open, and one that is already closed or merged, so that doing it twice (the workflow also closes it for newer work) changes nothing the second time; and SHALL log and ignore a failure to close, so that the decision still takes effect.

#### Scenario: Work from before

- **WHEN** a person rejects, from the page, a work that started before the workflow closed pull requests
- **THEN** its draft pull request is closed with a comment saying who rejected it

#### Scenario: Newer work

- **WHEN** a person aborts newer work, whose workflow also closes its pull request
- **THEN** the pull request is closed once and the second attempt changes nothing

#### Scenario: A pull request that is not the work's

- **WHEN** a person aborts a review of someone else's pull request
- **THEN** that pull request stays open

#### Scenario: GitHub refuses

- **WHEN** closing the pull request fails
- **THEN** the decision still takes effect and a warning is logged

#### Scenario: A decision that is not an ending

- **WHEN** a person approves or asks for changes
- **THEN** no pull request is closed

### Requirement: The work page shows who used the most tokens, as a pie

The system SHALL show on the page of a piece of work, with its usage, a pie chart of the tokens each agent used over the whole work, with a legend that names each agent with its tokens and its share of the total (so that nothing is told by colour alone), in colours that read in the light and the dark theme; SHALL show a single agent as a whole disc; and SHALL show no chart when no tokens were recorded.

#### Scenario: Several agents

- **WHEN** a person opens the page of a work in which the developer used most of the tokens
- **THEN** the pie shows the developer's slice as the largest and the legend lists each agent with its tokens and its percentage

#### Scenario: One agent

- **WHEN** only one agent has run
- **THEN** the pie is one whole disc with that agent in the legend at 100%

#### Scenario: Nothing recorded

- **WHEN** no step reported tokens
- **THEN** no pie is shown and the rest of the usage section is unchanged

### Requirement: The work page says how hard each review looks

The system SHALL record, when a work starts, how hard its spec reviewer and its design reviewer look (quick, standard or thorough, as chosen for the work or taken from the repository's file), and SHALL show it on the page of the work next to what it does without a person, naming the design review as off when the design is not reviewed; and SHALL show nothing for work that started before it was kept.

#### Scenario: A work with a thorough design review

- **WHEN** a work was started with the design review on at thorough
- **THEN** its page says that the spec review looks quick and the design review thorough

#### Scenario: A work without a design review

- **WHEN** a work was started with the design review off
- **THEN** its page says the design review is off, not a depth

#### Scenario: Older work

- **WHEN** the work started before the depths were kept
- **THEN** the page says nothing about them and is otherwise unchanged

### Requirement: The guard table says what happened to each call

The system SHALL say, for each call in the Guard section's list, whether it was stopped or only recorded: when the decision was to allow but the policy meant to deny (the guard was only watching), the page says "Not stopped: the guard only recorded it" and, for a call no rule could free, that the policy would refuse it once the guard is enforcing, not that it always refuses; and SHALL say above the list, when any listed call was only recorded, that the guard is only watching and nothing is being stopped.

#### Scenario: A call recorded in the watching profile

- **WHEN** a call has the decision allow and the policy meant deny
- **THEN** the row says it was not stopped, and does not say that the guard always refuses it

#### Scenario: A call that was stopped

- **WHEN** a call has the decision deny
- **THEN** the row says it was stopped, and for a risk no rule can free, that no rule can allow it

### Requirement: An administrator allows or removes a site that agents' commands may reach, from the admin page

The system SHALL let an administrator, in the Guard section of the admin page and when the instance keeps rules from the page, type a site (a host name, optionally `*.` followed by a domain) that the commands agents run in their sandbox may reach, add it, see the sites added with who added them and when, and remove one; SHALL refuse what is not a plain public host name (an address, a name without a dot, a wildcard over a whole top-level domain, a path, a scheme or a port); SHALL keep the sites in the same store as the other rules added from the page; and SHALL apply a change from the next step an agent starts, without a restart.

#### Scenario: Adding a site

- **WHEN** an administrator types `registry.example.org` and adds it
- **THEN** the page lists it with the administrator's login and the time, and the next agent step may reach it

#### Scenario: Something that is not a host name

- **WHEN** an administrator submits `https://x.example/path`, `10.0.0.1` or `*.com`
- **THEN** the page refuses it and keeps nothing

#### Scenario: Removing a site

- **WHEN** an administrator removes a site added from the page
- **THEN** it is no longer listed and the next agent step may not reach it, unless the operator's own list holds it

#### Scenario: Not an administrator

- **WHEN** someone who is not an administrator posts a site
- **THEN** it is refused and nothing changes

### Requirement: The admin page says the sites list is not applied when agents run in containers

The system SHALL, when agents run in containers (`SHELF_ISOLATION=container` on the worker, told to the web service by `SHELF_AGENTS_IN_CONTAINERS=on`), replace the form that adds a site in the Guard section by a sentence saying that the list of sites is not applied in that mode (the sandbox that enforces it is off, the container is the boundary and its network is not filtered yet), SHALL refuse a site posted anyway, and SHALL keep listing the rules already added with a note that they are kept but not applied. In the other mode nothing changes.

#### Scenario: The admin page in container mode

- **WHEN** an administrator opens the admin page and agents run in containers
- **THEN** the Guard section says the sites list is not applied and offers no field to add a site

#### Scenario: A site posted in container mode

- **WHEN** an administrator posts a site anyway
- **THEN** it is refused with a conflict and nothing is kept

#### Scenario: Sandbox mode

- **WHEN** agents run in the worker's sandbox
- **THEN** the form to add a site is shown as before

### Requirement: An administrator frees a project agent file for the agents' writes, from the admin page

The system SHALL let an administrator, in the Guard section of the admin page and when the instance keeps rules from the page, choose from a fixed list of project-level agent files (`opencode.json`, `opencode.jsonc`, the `.opencode` and `.codex` folders, the Copilot and hooks folders under `.github`) one that agents may write, add it, see who added it and when, and remove it; SHALL offer nothing outside that list, so that the settings and hooks of Claude Code, the guard's own files and the git hooks can never be freed from the page; SHALL keep it with the other rules added from the page and write it to the guard's overlay as `[paths] unprotect`; SHALL say that the file still goes through the pull request, where a person reads it; and SHALL apply it from the next call an agent makes.

#### Scenario: Freeing opencode.json

- **WHEN** an administrator chooses `opencode.json` and adds it
- **THEN** the page lists it with the administrator's login and the time, the overlay holds `unprotect = ["**/opencode.json"]`, and an agent may write that file from the next call

#### Scenario: Something outside the list

- **WHEN** a request names `**/.claude/settings.json` or any pattern that is not in the list
- **THEN** it is refused and nothing is kept

#### Scenario: Removing it

- **WHEN** an administrator removes the exception
- **THEN** the overlay no longer frees the file and agents may not write it again

#### Scenario: Not an administrator

- **WHEN** someone who is not an administrator posts a file
- **THEN** it is refused and nothing changes

### Requirement: A decision that ends the work asks in a themed dialog, never in the browser's own

The system SHALL ask before a decision that ends a work (reject, abort, and closing a work as an administrator) in a dialog of the interface itself, in the light and the dark theme, that says what is about to happen and that it cannot be undone and offers a cancel and a confirm button named for the action; SHALL open it with the cancel button focused, close it with Escape, a click outside it or the cancel button without sending anything, keep the keyboard inside it while it is open, and return the focus to the button that opened it; SHALL send the decision only when the person confirms it; and SHALL NOT use a dialog of the browser (`confirm`, `alert` or `prompt`) anywhere in the interface.

#### Scenario: Rejecting a work

- **WHEN** a person presses Reject on the page of a work
- **THEN** a themed dialog says the work will be rejected and cannot be recovered, and nothing is sent until they confirm

#### Scenario: Cancelling

- **WHEN** the person presses Cancel, Escape or the backdrop
- **THEN** the dialog closes, nothing is sent and the focus returns to the Reject button

#### Scenario: Confirming

- **WHEN** the person confirms
- **THEN** the decision is sent exactly as it would have been from the button

#### Scenario: No native dialog

- **WHEN** the interface's own scripts and templates are searched
- **THEN** none calls the browser's `confirm`, `alert` or `prompt`

### Requirement: The page of a work can be downloaded as one file for debugging

The system SHALL offer, on the page of a work, a button that downloads one Markdown file about that work, named `shelf-<work id>.md`, holding: what the work is (repository, requester, how it began, its phase and outcome, its pull request, the stops it does without a person and how hard its reviews look); the pipeline's steps with their state and when; the request as written; the whole conversation of the pull request in order, each comment with who spoke, when and what they wrote, without the cut that keeps the page short; every document of the work as written; and what the agents used per agent and in total; SHALL give it only to a person who may see that work, exactly as the page is; SHALL put each document in a fence that nothing inside it can close; and SHALL say plainly, in the file, a part that could not be read, without failing the download.

#### Scenario: Downloading a work

- **WHEN** a person who may see a work presses Download
- **THEN** they get `shelf-<work id>.md` with the facts, the steps, the request, every comment, every document and the usage

#### Scenario: A comment or document that holds a code fence

- **WHEN** a comment or a document contains a fenced block
- **THEN** it is placed in a longer fence so that it stays one block in the file

#### Scenario: GitHub cannot be read

- **WHEN** the conversation or the documents cannot be read
- **THEN** the file says which part is missing and the rest is still delivered

#### Scenario: Somebody who may not see the work

- **WHEN** a person who may not see the work asks for the file
- **THEN** they are refused as they are for the page

### Requirement: The guard's note about only watching follows its current mode

The system SHALL show the note that the guard is only watching, above the list of stopped calls, only when the guard's latest recorded call was judged in audit mode, and not because an older call in the list was only recorded, so that an operator who switched the profile to enforcing is not told it is still watching.

#### Scenario: A guard switched to enforcing

- **WHEN** the list holds a call that was only recorded earlier and the guard's latest call was judged in enforce mode
- **THEN** the row says the call was not stopped and the note about only watching is not shown

#### Scenario: A guard that still only watches

- **WHEN** the guard's latest call was judged in audit mode
- **THEN** the note is shown

### Requirement: The downloaded file holds the record of every agent run

The system SHALL add to the file of a work, when run records are kept, a section for each agent run in order with: the step, the round and the role, when it began and ended, how it ended and why it stopped, the model, what it used, whether it continued a session or started again, what the worker had told it about tools and the CI, the errors it reported, the calls its permissions refused, the number of tool calls, and the calls that failed with the start of what each said, then the other calls in order; SHALL say plainly when no record exists (a work from before they were kept, or an instance that keeps none) without failing the download.

#### Scenario: A work with failed commands

- **WHEN** an agent's command failed during a run
- **THEN** the file lists that command under the run, marked as failed with the start of the error

#### Scenario: A work with no records

- **WHEN** no record exists for the work
- **THEN** the file says that no run record was kept and the rest is unchanged

### Requirement: The downloaded file says what the guard flagged while the work ran

The system SHALL add to the file of a work, when the guard can be read, a section listing the calls the guard stopped or would have stopped between the first step of the work and its last activity (or now, while it runs), each with its time, the agent, what it was (the command or the address, as the guard shortens it), the risks found, the reason, and whether it was stopped or only recorded; SHALL say that the guard keeps only its latest calls when the oldest it lists is later than the start of the work, so that a missing call is not taken for none; and SHALL say plainly, without failing the download, when the guard cannot be read, and when it flagged nothing in that time.

#### Scenario: Calls flagged during the work

- **WHEN** the guard flagged two calls between the first step and the last activity of the work, and one before it started
- **THEN** the file lists the two, each with its time, command, risks, reason and whether it was stopped, and not the third

#### Scenario: Nothing flagged

- **WHEN** the guard flagged nothing in that time
- **THEN** the file says so

#### Scenario: The guard cannot be read

- **WHEN** the guard is not installed or does not answer
- **THEN** the file says it could not be read and the rest of the file is unchanged

#### Scenario: The guard keeps only its latest calls

- **WHEN** the oldest call the guard lists is later than the start of the work
- **THEN** the file says that earlier calls may be missing

### Requirement: A work the workflow engine has forgotten can still be downloaded while its records are kept

The system SHALL, when the workflow engine no longer holds a work but run records of it are kept, still give the file of that work at the same address to a person who may see the repository it named, built from what is kept: the records (and from them the repository, who asked, how it began and what the agents used), the documents on the work's branch, and the conversation of the pull request found from the work's branch; SHALL say in the file that the engine no longer holds the work, so that the steps, its outcome and its stops are not known; SHALL refuse it as it refuses a work they may not see, and answer not found for a work with no record; and SHALL keep the records for thirty days after the last run.

#### Scenario: A work that ended days ago

- **WHEN** the engine has forgotten a work, its records are kept, and a person who may see its repository asks for its file
- **THEN** they get a file with the work's facts from the records, the runs, the documents, the conversation and the usage, and a line saying the engine no longer holds it

#### Scenario: A repository they may not see

- **WHEN** someone who may not see the repository named in the records asks for the file
- **THEN** it is refused as not found

#### Scenario: No record

- **WHEN** the engine does not hold the work and no record exists
- **THEN** the answer is not found

### Requirement: The start form asks one question about a disagreement, with what each answer does

The system SHALL replace, on the start form, the choice to stop at a deadlock by one question, "When the reviewer and the author cannot agree", with four answers (`ask`, `arbitrate-ask`, `arbitrate-go`, `go`), preset from the repository, each with one plain sentence of what happens and what it costs, the arbitrating answer that asks a person only when the arbitrator cannot decide marked as the recommended one for work that must go on alone, and the chosen answer summarised under the group in words (who decides, in how long, at what cost, when a person is asked).

#### Scenario: The four answers

- **WHEN** a person opens the start form
- **THEN** the question shows four answers with their sentences, the repository's answer chosen, and a summary of the chosen one

### Requirement: A stop is a decision card, not a pasted review

The system SHALL show a work that waits for a person at a disagreement as a decision card: the question in one line; what the reviewer says and what the author says, in two or three lines each with the full texts folded; the arbitrator's recommendation and brief when it ran; and buttons that act: follow the recommendation (send the changes with its text), edit it and send, go on and note it on the pull request (where the phase may be passed), and reject. The system SHALL write the comment on the pull request in the same shape, short, with the `/shelf changes` text ready to copy, and SHALL show an arbitration as an entry of its own in the conversation, with its verdict as a badge, and the work as arbitrating while it runs.

#### Scenario: The arbitrator could not decide

- **WHEN** a person opens a work that waits after an `ESCALATE`
- **THEN** the card names the question, shows the options and the recommendation, and *Follow the recommendation* sends its text as the requested changes

#### Scenario: No arbitrator

- **WHEN** a work that waits at a disagreement has no arbitration
- **THEN** the card still shows the two sides in short and offers the buttons that apply

### Requirement: The merge view and the pull request say what was settled without the person

The system SHALL end the pull request description and the work page, when the work is ready to merge, with a section "Settled without you" that lists every arbitration (phase, verdict, one line of why, a link), every open point passed on and every assumption an agent recorded, and SHALL mark an `OVERRULE` and a passed deadlock as to check before merging.

#### Scenario: Ready to merge after an overrule

- **WHEN** a work reaches the merge after an arbitration that overruled a reviewer
- **THEN** the section lists it with its evidence and marks it to check before merging

#### Scenario: Nothing was settled for the person

- **WHEN** a work reaches the merge with no arbitration, no passed deadlock and no assumption
- **THEN** the section says nothing was settled without the person
