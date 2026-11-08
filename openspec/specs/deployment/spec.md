# Deployment

## Purpose

Run the whole product on one server with one command, configured by one environment file and one access file, with no reverse proxy bundled and a guided first run.

## Requirements

### Requirement: One compose file runs Temporal, the web service and the worker

The system SHALL provide a Compose file that starts Temporal, the web service and a scalable worker from one image, with the web service waiting for Temporal to be healthy and nothing published except the web port.

#### Scenario: Starting the stack

- **WHEN** the stack is started with a filled environment file
- **THEN** Temporal becomes healthy, then the web service and the worker start, and the web service answers on its port

### Requirement: No reverse proxy is bundled

The system SHALL NOT bundle a TLS terminator, and SHALL document that any proxy or ingress in front of the web port will do.

#### Scenario: HTTPS

- **WHEN** an operator wants HTTPS
- **THEN** they put their own proxy in front of the web port, and the instance reads its public address from `PUBLIC_URL`

### Requirement: All settings come from the environment and one access file

The system SHALL read its settings from environment variables, naming any required one that is missing, and the access list and mode from a mounted `shelf.toml`, warning loudly when none exists because the instance is then open.

#### Scenario: A missing secret

- **WHEN** `SESSION_SECRET` is not set
- **THEN** startup fails naming it

#### Scenario: No access file

- **WHEN** the access file is absent
- **THEN** the instance starts open to any GitHub account and logs a warning

### Requirement: The first run registers the GitHub App in one click

The system SHALL, while no GitHub App is configured, serve a page that registers one from a manifest built from the public address and then shows the credentials once, uncached, in the form to paste into the environment file.

#### Scenario: A fresh instance

- **WHEN** the web service starts without GitHub App credentials
- **THEN** it offers the one-click registration and no sign-in

#### Scenario: After GitHub redirects back

- **WHEN** GitHub returns a registration code
- **THEN** the credentials are shown once and the response is marked no-store

### Requirement: The worker sandbox is the only relaxed container

The system SHALL relax the container security profile only for the worker, which runs the agents' sandbox, and SHALL run all services as a non-root user.

#### Scenario: Services

- **WHEN** the stack runs
- **THEN** only the worker has the relaxed seccomp profile

### Requirement: The setup page is complete without any other service

The system SHALL serve from the instance itself every style and script that the first-run setup page links to.

#### Scenario: A fresh instance

- **WHEN** the setup page is opened before any GitHub App exists
- **THEN** every `/static/` asset it references answers successfully

### Requirement: The first-run screens say what will happen and make the handover easy

The system SHALL show, before the registration click, the address being registered, the permissions the App will hold and the steps that follow, and SHALL show the credentials with a button that copies the whole block at once.

#### Scenario: Before registering

- **WHEN** a person opens the setup page
- **THEN** they see the instance address, the five permissions with their purpose, and the three steps, in the same interface as the rest of the product

#### Scenario: After registering

- **WHEN** the credentials are shown
- **THEN** a single action copies the whole `.env` block

### Requirement: An install or update always replaces what runs, and says what runs

The system SHALL, on every run of the install script, rebuild the image stamped with the checkout's git revision, replace the web and worker containers, and report the revision the web service answers with, warning when it differs from the checkout.

#### Scenario: An update

- **WHEN** the operator pulls new code and runs the script again
- **THEN** the containers are recreated from a rebuilt image and the script prints the new revision as running

#### Scenario: A stale service

- **WHEN** the service reports another revision than the checkout
- **THEN** the script warns instead of claiming success

### Requirement: The health check reports the revision

The system SHALL include the git revision of the build in the answer of the health check, in both the product and the setup mode.

#### Scenario: Health

- **WHEN** the health check is requested
- **THEN** it answers with the status and the revision

### Requirement: A missing setting says where to find it

The system SHALL, when a required setting is absent, name it and say in plain words where its value comes from, for every GitHub App credential, the public address and the session secret.

#### Scenario: A missing slug

- **WHEN** the App slug is not set
- **THEN** the error says it is the name in the App's public link

### Requirement: The by-hand registration guide matches GitHub's form

The system SHALL show on the setup page the value for each field of GitHub's App form, using the instance's own address.

#### Scenario: The webhook address

- **WHEN** the guide is shown for an instance
- **THEN** the webhook and callback addresses are derived from its public address

### Requirement: A configuration mistake stops the service with one readable line

The system SHALL, when a configuration file or a required setting is invalid, stop with a single line that names the file or the setting and the fix, not a stack trace, and the install script SHALL check the access file's syntax before building.

#### Scenario: Names without quotes

- **WHEN** the access file lists a name without quotes
- **THEN** the service stops saying which file is invalid and that names go in quotes

#### Scenario: Before building

- **WHEN** the operator runs the install script with an invalid access file
- **THEN** it stops before building and says so

### Requirement: The private key is a mounted file

The system SHALL read the GitHub App's private key from a file in a secrets directory that is mounted read-only into the web and worker containers, SHALL keep that directory out of version control, SHALL accept the key inline in the environment as an alternative, and SHALL say where to put the file when it is missing.

#### Scenario: The key file is present

- **WHEN** the file exists in the secrets directory and the App id is set
- **THEN** the services read the key from it

#### Scenario: The key file is missing

- **WHEN** the App id is set but no key is available
- **THEN** the service stops saying to put the file at `deploy/secrets/github-app.pem`

### Requirement: Operator files are created from examples and never committed

The system SHALL ship the environment file and the access file as examples, create the real ones on the first run of the install script, keep them out of version control, and never overwrite them, so that updating the code never conflicts with the operator's changes.

#### Scenario: First run

- **WHEN** the install script runs without an access file
- **THEN** it creates one from the example and says to edit it

#### Scenario: An update

- **WHEN** the operator pulls new code
- **THEN** their access file and environment file are untouched and there is no merge conflict

### Requirement: An open instance is flagged on every run

The system SHALL warn on every run of the install script when the access file restricts nobody.

#### Scenario: No names listed

- **WHEN** the access file lists no organisation, user or admin
- **THEN** the script warns that anyone with a GitHub account may sign in

### Requirement: Temporal's interface is never published, only proxied to administrators

The system SHALL NOT publish Temporal's web interface on any host port, because it has no login and can signal or end any workflow, and SHALL serve it under a path of the web service to signed-in administrators only.

#### Scenario: Default

- **WHEN** the stack runs
- **THEN** no host port answers with Temporal's interface, and it is reachable only through the web service

### Requirement: A missing model credential is flagged before the agents fail

The system SHALL warn when the install script finds no model credential in the environment file, and SHALL tell an agent that failed to log in that the credential belongs in the worker's environment, not in the host's own login.

#### Scenario: No credential

- **WHEN** the environment file has no model credential
- **THEN** the script warns that agents will fail with "Not logged in" and says how to get one
