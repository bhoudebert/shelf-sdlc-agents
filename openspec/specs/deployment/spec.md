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
