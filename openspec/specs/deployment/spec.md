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

### Requirement: A closed instance is flagged on every run

The system SHALL warn on every run of the install script when the access file lists nobody, because nobody could then sign in.

#### Scenario: No names listed

- **WHEN** the access file lists no organisation, user or admin
- **THEN** the script warns that nobody can sign in until someone is listed

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

### Requirement: A missing model credential is flagged by the worker and the web service

The system SHALL log a warning when the worker starts without a model credential, and SHALL treat a Claude token, an API key or a gateway address as a credential.

#### Scenario: Worker start

- **WHEN** the worker starts with none of them set
- **THEN** it logs how to get a token and where to put it

### Requirement: The web service wraps GitHub lookups in a short cache

The system SHALL wire the web service's GitHub access through a cache of about a minute, so that a long-open interface does not spend GitHub's rate limit.

#### Scenario: A long-open interface

- **WHEN** the interface stays open for an hour
- **THEN** GitHub receives about one lookup per person per minute at most

### Requirement: The web service reads the work's documents through a short cache

The system SHALL wire the web service to read a work's documents from GitHub through a cache of a few seconds, so that a page refreshing every few seconds does not spend GitHub's rate limit.

#### Scenario: A page left open

- **WHEN** a work page stays open
- **THEN** GitHub is asked for the documents at most once every few seconds

### Requirement: The agents' sandbox can be turned off where it cannot start

The system SHALL let the operator turn the agents' sandbox off, for hosts where it cannot start inside the container, and SHALL document how to test it and what the trade-off is.

#### Scenario: A host without user namespaces

- **WHEN** the sandbox cannot start and the operator turns it off
- **THEN** the agents can run commands with the container as the only boundary

### Requirement: The operator can check that the agents work

The system SHALL provide a command that runs tiny real agent checks against the instance's configuration in a throwaway repository (a shell, the repository's agent file, the title convention, commands in the sandbox, the credential) and reports each with what to do about a failure.

#### Scenario: A sandbox that cannot start

- **WHEN** the developer cannot run a command
- **THEN** the report says so and names the setting that turns the sandbox off

### Requirement: The operator can point the agents at a specific Claude executable

The system SHALL let the operator name a Claude Code executable to use instead of the one bundled, and SHALL relax AppArmor for the worker along with its other profile, because the sandbox needs user namespaces that Ubuntu hosts restrict.

#### Scenario: A host with its own Claude

- **WHEN** the operator names an executable
- **THEN** the agents use it

### Requirement: Webhook deliveries are logged

The system SHALL log each webhook it refuses, applies or cannot apply, with the reason, so that an operator can follow a command typed on a pull request in the web service's log.

#### Scenario: A refused delivery

- **WHEN** a delivery is refused
- **THEN** the log says why

### Requirement: The doctor probes the sandbox itself and says how to fix it

The system SHALL have the doctor start the sandbox's own tool first and, when it cannot start, report what the tool said with the host fix and a warning that disabling the sandbox exposes the worker's environment.

#### Scenario: A repository rule adds a closing word

- **WHEN** the agent that names pull requests answers with a correct title followed by the closing word a repository rule asks for
- **THEN** the title check reads the first line and passes

#### Scenario: Ubuntu 24.04

- **WHEN** the sandbox cannot start on an Ubuntu host
- **THEN** the report names the AppArmor setting to change and the safer order of remedies
