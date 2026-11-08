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

### Requirement: The install script catches the usual mistakes before building

The system SHALL, before building, refuse to continue when the public address or the session secret is empty or the web port is already used by something else, and SHALL warn about an environment file at the repository root and about a GitHub App credential left empty when the App ID is set.

#### Scenario: A busy port

- **WHEN** the configured web port is already in use by another program
- **THEN** the script stops and tells the operator to set another port

#### Scenario: The wrong file

- **WHEN** a `.env` exists at the repository root
- **THEN** the script warns that only `deploy/.env` is read

### Requirement: The web port is published on the loopback by default

The system SHALL publish the web port on the loopback address unless the operator sets another address, so that the reverse proxy is the only way in.

#### Scenario: Default

- **WHEN** no bind address is set
- **THEN** the web service is reachable from the host itself and not from the network
