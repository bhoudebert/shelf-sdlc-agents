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
