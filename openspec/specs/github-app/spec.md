# GitHub App

## Purpose

Use one GitHub App for three jobs: sign people in, show them the repositories they can use, and give agents a short-lived identity of their own.

## Requirements

### Requirement: People sign in with their GitHub identity

The system SHALL trade the OAuth code from the sign-in redirect for the person's user token, and SHALL read their login and organisations with it, raising a clear error when GitHub refuses the code.

#### Scenario: A valid code

- **WHEN** GitHub accepts the code
- **THEN** the person's token, login and organisations are available to the access check

#### Scenario: A refused code

- **WHEN** GitHub answers with an error instead of a token
- **THEN** sign-in fails with GitHub's reason

### Requirement: A person sees only what the App and they share

The system SHALL list the repositories of every installation the person can reach, following pagination, using the person's own token, so that no access table is kept.

#### Scenario: Several installations and pages

- **WHEN** the person reaches two installations and one has a second page of repositories
- **THEN** every repository of both is listed once

### Requirement: Agents act as the App with a token minted per step

The system SHALL sign a short-lived JWT with the App's private key, find the installation covering a repository, and mint an installation token from it, and SHALL NOT store the token.

#### Scenario: Cloning as the App

- **WHEN** a step needs to clone a repository
- **THEN** an installation token is minted and the clone URL authenticates with it as `x-access-token`

#### Scenario: The JWT lifetime

- **WHEN** the JWT is signed
- **THEN** it expires within ten minutes of being issued

### Requirement: The App is public so that more than its owner can sign in

The system SHALL register the App as public and with a description, because GitHub shows a private App to no account but its owner and answers 404 to every other account that tries to sign in. The description (Markdown) SHALL say what the App does, what it may touch and that only the people and organisations the operator lists can use the instance, and SHALL be offered to copy on the setup page for the registration by hand. Public SHALL NOT widen access: who may use the instance stays decided by the access list.

#### Scenario: One-click registration

- **WHEN** the manifest is built
- **THEN** it is public and carries the description

#### Scenario: A second person signs in

- **WHEN** a person who does not own the App signs in and is on the access list
- **THEN** GitHub lets them authorize it

#### Scenario: A person who is not listed

- **WHEN** a person who is not on the access list authorizes the public App
- **THEN** they are refused by the instance after signing in

### Requirement: Registration is one click

The system SHALL build the App's manifest from the instance's public address, post it to GitHub from the browser, and convert the code GitHub returns into the App's credentials.

#### Scenario: The manifest

- **WHEN** the manifest is built for a public address
- **THEN** the callback, setup and webhook URLs derive from it, with the minimum permissions and the events the system listens to

#### Scenario: The conversion

- **WHEN** GitHub returns a registration code
- **THEN** the system exchanges it for the App id, client id and secret, webhook secret and private key

### Requirement: The manifest is one GitHub accepts

The system SHALL subscribe the manifest only to events an App may select, and only to events covered by a permission it requests, and SHALL NOT list the events GitHub always sends.

#### Scenario: Only the events the system reads

- **WHEN** the manifest is built
- **THEN** it subscribes to `pull_request` and `issue_comment` and to nothing else, and the setup page and the site list the same two

#### Scenario: Always-sent events

- **WHEN** the manifest is built
- **THEN** it does not list `installation`, `installation_repositories` or `ping`

### Requirement: Registering by hand is fully explained

The system SHALL explain, on the setup page, every field of GitHub's form with the exact value to type, where each credential is found on the App's page, and SHALL say to put the private key file at `deploy/secrets/github-app.pem`.

#### Scenario: A manual registration

- **WHEN** a person opens the by-hand guide
- **THEN** they see each form field with its value, a table of where each credential comes from, and where the key file goes

#### Scenario: A missing credential

- **WHEN** a required credential is missing at startup
- **THEN** the error names it and says where to find it

### Requirement: The App's own setup is checked against what GitHub reports

The system SHALL read from GitHub, as the App, which events the App subscribes to, which permissions it has, its webhook URL and secret, and its recent webhook deliveries, and SHALL judge them with a pure function that names each problem and what to change, most serious first: missing events, too low a permission, a webhook URL that is not this instance's, no webhook secret, and a latest delivery that failed (a refused signature, an unreachable address, another error).

#### Scenario: No events subscribed

- **WHEN** the App is subscribed to neither pull request nor issue comment events
- **THEN** the finding says so, names the page and the boxes to tick, and that a box stays greyed until its permission is granted

#### Scenario: A refused signature

- **WHEN** the latest delivery was answered 401 or 403
- **THEN** the finding says the webhook secret on GitHub and in the instance's environment must be the same

#### Scenario: A healthy App

- **WHEN** events, permissions, URL, secret and the latest delivery are all right
- **THEN** every finding is a confirmation

#### Scenario: GitHub cannot be asked

- **WHEN** GitHub refuses the App's identity or cannot be reached
- **THEN** the result is a sentence saying why, not an error

### Requirement: The comments of a pull request are read back as a story

The system SHALL read, as the App, every comment of a pull request (up to five pages of a hundred) and classify each by who spoke: an agent by the hidden marker of its comments, a person, or the system's own announcements, and SHALL leave out the progress comment.

#### Scenario: A mixed conversation

- **WHEN** a pull request has an agent's comment, the progress comment and a person's comment
- **THEN** the story holds the agent's and the person's, in order

### Requirement: A pull request's branch and its state are read for the work on it

The system SHALL read, for a pull request, the branch it was opened from, where that branch is, whether it is open and whether it comes from the repository itself, as the person when they ask to start and as the App for each step.

#### Scenario: From the repository itself

- **WHEN** the head of a pull request is in the same repository
- **THEN** it can be changed by the App

#### Scenario: From a fork or a deleted fork

- **WHEN** the head repository is another one or is gone
- **THEN** it cannot

### Requirement: Issues, pull requests and files are read for the work that starts from them

The system SHALL read, as the App, an issue or pull request of a repository (its title and body, only when its author has write access) and a file of it (on its default branch or the one named, as text of at most 100 KB), and SHALL say plainly when it does not exist, is a folder, is too long or is not text.

#### Scenario: Written by an outsider

- **WHEN** the issue's author has no write access
- **THEN** nothing of it is used

### Requirement: A person's view of a pull request is asked as that person

The system SHALL ask GitHub, with the person's own token and not the App's, whether a pull request exists and is visible to them, so that what a person may start is limited by what they can see.

#### Scenario: A pull request the person cannot see

- **WHEN** GitHub answers 404 to the person's token
- **THEN** the pull request is treated as not existing for them

### Requirement: Comments of a pull request can be marked outdated

The system SHALL read the latest hundred comments of a pull request and mark as outdated, in one request, those the system decided no longer belong, never using an identifier that is not a node identifier, and SHALL do nothing when none qualifies.

#### Scenario: Several to hide

- **WHEN** two comments qualify and one is already hidden
- **THEN** one request marks the two and leaves the hidden one

#### Scenario: Nothing to hide

- **WHEN** no comment qualifies
- **THEN** only the question is sent

### Requirement: The CI of a pull request is read as the App

The system SHALL read, as the App, the check runs of the head commit of a pull request (with the summary and the annotations of the ones that failed) and its commit statuses, and SHALL carry on without statuses when GitHub refuses them to the App.

#### Scenario: Statuses are refused

- **WHEN** GitHub answers 403 for the commit statuses
- **THEN** the CI is judged from the check runs alone

### Requirement: A failing job's log reaches the agents

The system SHALL request the Actions permission at read, SHALL read as the App the end of the log of each failing GitHub Actions job of a pull request's head commit, and SHALL say in the report when it could not (permission missing, or the log expired) instead of leaving the report without detail. The admin check SHALL list a missing Actions permission as an error, because without the log the developer cannot see why a job failed.

#### Scenario: The log is readable

- **WHEN** a GitHub Actions job failed
- **THEN** the report of the run carries the last lines of its log

#### Scenario: The App lacks the permission

- **WHEN** GitHub refuses the log with 403
- **THEN** the report says the log could not be read because the App lacks the Actions permission, and the admin check lists that permission as missing

### Requirement: The Workflows permission is off by default and its state is shown

The system SHALL NOT request the Workflows permission, because a changed workflow runs with the repository's secrets, SHALL report on the admin page whether the App has it, as a confirmation either way, and SHALL explain how to grant it and, when granted, which GitHub safeguards keep changed workflows reviewed (code owners for `.github/`, environments with required reviewers, approval for fork workflows).

#### Scenario: Not granted

- **WHEN** the App lacks the Workflows permission
- **THEN** the check says agents cannot change CI workflow files and how to allow it

#### Scenario: Granted

- **WHEN** the App has Workflows at write
- **THEN** the check accepts it and names the safeguards that keep changed workflows reviewed

