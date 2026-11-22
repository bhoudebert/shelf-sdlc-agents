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

### Requirement: The web service serves only what the access list names

The system SHALL wire the web service so that every repository it lists or acts on has passed the access list's owner check, whichever page or webhook asks.

#### Scenario: Wired once

- **WHEN** the web service starts with the GitHub App configured
- **THEN** the forge its pages and webhooks use is the one narrowed to listed owners, not the raw one

### Requirement: The access file is picked up when it changes

The system SHALL read the access list again whenever `shelf.toml` changes, in the web service and in the worker, without a restart, keeping the rules in force when an edit cannot be read or is not valid and saying so in its log; the compose file SHALL mount the folder that holds the file and not the file alone, so that an editor which replaces the file is still seen.

#### Scenario: An edit that adds a person

- **WHEN** an operator adds a user to `shelf.toml` while the instance runs
- **THEN** that person can sign in on their next attempt, with no restart

#### Scenario: An edit with a typo

- **WHEN** the file is saved with invalid TOML
- **THEN** the previous access list stays in force and the log names the file and the mistake

#### Scenario: A file that is gone

- **WHEN** the file is deleted while the instance runs
- **THEN** the previous access list stays in force until the file is back

#### Scenario: An editor that replaces the file

- **WHEN** an editor saves by writing a new file and renaming it over the old one
- **THEN** the change is seen, because the folder is mounted

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

### Requirement: The setup and the admin pages say how to let a second person sign in

The system SHALL say on the setup page, for the registration by hand, to choose Any account for where the App can be installed and to copy the description it offers, SHALL explain that public does not open the instance, and SHALL tell on both the setup page and the administrator's check what to do when a second person gets a 404 signing in: make the App public from its Advanced tab.

#### Scenario: The setup page

- **WHEN** the setup page is served
- **THEN** it offers the description to copy, asks for Any account and names Make public

#### Scenario: The administrator's check

- **WHEN** the administrator opens the check
- **THEN** it says that a 404 on sign-in for a second person means the App is private and how to make it public

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

### Requirement: The web service reads a pull request's conversation through a short cache

The system SHALL wire the web service to read a pull request's conversation through a cache of ten seconds, so that a page polling every twenty seconds costs GitHub little.

#### Scenario: Two reads within the cache time

- **WHEN** the same pull request's conversation is read twice within ten seconds
- **THEN** GitHub is asked once

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

### Requirement: Docker in steps is off until the operator names a runtime that can honour it

The system SHALL read `SHELF_STEP_DOCKER` (`off` when unset, or `on`), `SHELF_STEP_RUNTIME` (the name of the container runtime that makes a daemon inside a step safe) and `SHELF_STEP_DNS` (the resolvers a step with Docker is given, as addresses separated by commas; empty keeps Docker's own) and `SHELF_STEP_DOCKER_PROFILE` (`standard` when unset, or `unconfined`, `systempaths` or `full`: how permissive the step's container is, as the host needs), SHALL give steps a private Docker daemon only when the first is `on`, and SHALL refuse to start, naming the setting, when `SHELF_STEP_DOCKER` is `on` and the runtime is not named, is not one the container engine reports, or the isolation is not `container`, so that a step never gets a daemon without the boundary that makes it safe.

#### Scenario: The resolvers of the host

- **WHEN** `SHELF_STEP_DOCKER` is `on` and `SHELF_STEP_DNS` is not set
- **THEN** `install.sh` asks the host script to probe, which finds the host's upstream resolvers (those Docker copies on its default network, without the loopback ones) and proves that a step under the runtime, on a user-defined network, resolves a name with them, and `install.sh` writes them into the environment file once and never replaces a value that is set

#### Scenario: No resolver that works

- **WHEN** the host has no upstream resolver a step can use, or a step cannot resolve a name with it
- **THEN** the probe fails, says so, and says to set `SHELF_STEP_DNS` by hand

#### Scenario: A profile that does not exist

- **WHEN** `SHELF_STEP_DOCKER_PROFILE` is a name that is not one of the profiles
- **THEN** the runner and the worker refuse to start and name the setting and the accepted values

#### Scenario: Unset

- **WHEN** `SHELF_STEP_DOCKER` is not set
- **THEN** steps have no Docker daemon and the agents are told that Docker is not available

#### Scenario: On without a runtime

- **WHEN** `SHELF_STEP_DOCKER` is `on` and `SHELF_STEP_RUNTIME` is empty
- **THEN** the runner and the worker refuse to start and say that a runtime must be named

#### Scenario: A runtime the engine does not have

- **WHEN** `SHELF_STEP_RUNTIME` names a runtime the container engine does not list
- **THEN** the runner refuses to start and names the runtime and the ones the engine has

#### Scenario: On in sandbox mode

- **WHEN** `SHELF_STEP_DOCKER` is `on` and `SHELF_ISOLATION` is not `container`
- **THEN** the worker refuses to start and says that Docker in steps needs the container mode

#### Scenario: Everything set

- **WHEN** `SHELF_STEP_DOCKER` is `on`, the runtime is installed and named, and `SHELF_ISOLATION` is `container`
- **THEN** the services start and the steps that run repository code get a Docker daemon

#### Scenario: Container mode runs the repository's checks in steps

- **WHEN** the worker is given the runner's address and token (`SHELF_ISOLATION=container`)
- **THEN** it runs each command of a repository's checks as a step through the runner, over the same clone, tools and sessions volumes as the agents' steps and with a Docker daemon in it when `SHELF_STEP_DOCKER` is `on`, and in the sandbox mode it runs them in its own shell

#### Scenario: One setting for the services that share the environment file

- **WHEN** `SHELF_STEP_DOCKER=on` is set in the environment file that the web service, the catalog, the worker and the runner share
- **THEN** the web service and the catalog start with it off, as they run no agent, and the worker and the runner have it on

#### Scenario: The image with Docker

- **WHEN** the operator installs with `SHELF_STEP_DOCKER=on`
- **THEN** `install.sh` builds the step image that has a Docker daemon, with the engine, its client and Compose in it, and the runner uses it only for a step that asks for Docker

### Requirement: The install guide and the install script say what the host needs, and what installing it does

The system SHALL list, in the install guide of the site and in `deploy/README` text shown by the install script, everything an operator must install or enable on the host for each mode: the container engine and its minimum version, and, for Docker in steps, the runtime (its name, the kernel, the distribution releases it is known to work on, and the settings of the host it depends on, such as the kernel's rules for user namespaces or access to virtualisation), the command that installs it, and what that command does to a host that already runs containers (whether it restarts the engine and so stops them). `install.sh` SHALL check what it can (the engine version, the runtime the engine reports, the kernel) and, when `SHELF_STEP_DOCKER` is `on` and something is missing, SHALL stop before it builds anything and print what is missing and the page that says how to add it, so that no operator has to find out from a failed work.

#### Scenario: Docker in steps with no runtime installed

- **WHEN** `SHELF_STEP_DOCKER` is `on` and the engine lists no runtime by the name in `SHELF_STEP_RUNTIME`
- **THEN** `install.sh` stops, names the missing runtime, and prints the guide's address

#### Scenario: A host that is not known to work

- **WHEN** the host's distribution release or kernel is one the guide lists as failing for the runtime
- **THEN** `install.sh` says so before it builds anything and does not go on unless the operator confirms

#### Scenario: What installing it does is written down

- **WHEN** an operator reads the guide's section on the runtime
- **THEN** it says whether the install restarts the container engine and what that does to containers already running on the host

### Requirement: A separate host script prepares the runtime for Docker in steps, one checked step at a time

The system SHALL provide a host script, apart from `install.sh` because it changes the system and needs root, that prepares the runtime named by `SHELF_STEP_RUNTIME` (Kata Containers by default) on Ubuntu and Debian, on x86_64 and arm64, and refuses on any other system with the reason and the other options. The script SHALL be safe to run again: each step SHALL check whether it is already done, SHALL skip it if so, and otherwise SHALL do it and verify it. The steps are: the platform (the engine's minimum version, `/dev/kvm`, nested virtualisation); the kernel modules the runtime needs, loaded and kept across reboots; the runtime's release, at a version and with a checksum that the script holds and verifies before it extracts anything; the runtime's entry in the engine's `daemon.json`, merged into the existing file after a dated backup and refused when the file is not valid; a reload of the engine, then a check that the runtime is listed and that the containers that were running still run; and two smoke tests (a container under the runtime that reports a kernel other than the host's, and a Docker daemon, in the image the runner uses and started with the container flags the runner uses (the same user, read-only root, init process and temporary folders), that proves what a repository's checks use, started without privileged mode and with only the capabilities a step is given: that it runs a container, that a container with a healthcheck becomes healthy, that a command can be executed in a running container (a healthcheck is one), and that a port published on a port the host already uses answers from inside the step; by trying the step profiles in a fixed order and naming the first under which all of it works). The script SHALL say before it changes anything what it will install and change, SHALL restart the engine only when asked to, and SHALL list the containers a restart would stop. `install.sh` SHALL, when `SHELF_STEP_DOCKER` is `on` and `SHELF_STEP_DOCKER_PROFILE` is not set, ask the script to find the first profile that works on this host (`--probe`) and write it into the environment file, so that each host runs its steps with the profile it supports; and SHALL run the script's read-only check when `SHELF_STEP_DOCKER` is `on` and, when something is missing, SHALL offer to run the script through `sudo`, or run it when given the flag for it.

#### Scenario: The host needs a more permissive profile

- **WHEN** the standard profile does not start a Docker daemon on this host but a later one does
- **THEN** the script says which profile works, and that the runner must be given it, and does not report the host as ready under the standard one

#### Scenario: No profile works

- **WHEN** no profile starts a Docker daemon on this host
- **THEN** the script fails, shows the last lines each attempt printed, and says that Docker in steps cannot be used on this host

#### Scenario: A service that drops its privileges

- **WHEN** the proof starts the service whose healthcheck it waits for
- **THEN** it is one that runs as a non-root user after it starts (a database image), because a container that never changes user can be entered without the capability that one that does needs, and would let a host pass the proof although a real database could never become healthy

#### Scenario: A profile under which a container cannot be entered

- **WHEN** a daemon in a step runs a container but a command cannot be executed in it, as under a profile where the container cannot be entered, so that no healthcheck can pass
- **THEN** the script does not take that profile: it tries the next one, and if none works it fails and shows what each attempt printed

#### Scenario: A published port the host already uses

- **WHEN** the proof publishes a port that a service of the host already holds
- **THEN** it answers from inside the step, because the daemon publishes in the step's own network and not on the host

#### Scenario: The proof is the step

- **WHEN** the proof starts its container
- **THEN** it uses the image of a step with Docker and the runner's own flags, so that what passes the proof passes in a step, and when that image is not built it says that it fell back to another and that the result is weaker

#### Scenario: Never privileged

- **WHEN** the script starts a container to prove a Docker daemon
- **THEN** it does not use privileged mode, which under the runtime passes the host's devices through

#### Scenario: Only looking

- **WHEN** the script runs with `--check`
- **THEN** it changes nothing and starts no container, names each step as done or missing, and exits with a status that says whether the host is ready

#### Scenario: Nobody to ask

- **WHEN** the script has something to change and is run without a terminal and without `--yes`
- **THEN** it changes nothing and says that `--yes` is needed

#### Scenario: An interrupted download

- **WHEN** the release is cut short or fails its checksum
- **THEN** the runtime's folder is as it was before the run, because the release is unpacked aside and moved into place only when whole

#### Scenario: Run twice

- **WHEN** the script runs on a host where every step is done
- **THEN** it changes nothing, reports each step as done, and runs the smoke tests

#### Scenario: A host that cannot do it

- **WHEN** the host has no `/dev/kvm`, or is not Ubuntu or Debian
- **THEN** the script stops before changing anything, says which requirement failed and names the other options

#### Scenario: An existing daemon configuration

- **WHEN** `/etc/docker/daemon.json` already holds other settings
- **THEN** they are kept, a dated copy of the file is made first, and a file that is not valid JSON is left untouched with an error

#### Scenario: The reload does not register the runtime

- **WHEN** the engine does not list the runtime after a reload
- **THEN** the script says so, lists the containers a restart would stop, and restarts only with the flag that asks for it

#### Scenario: A tarball that does not match

- **WHEN** the downloaded release does not match the checksum the script holds
- **THEN** nothing is extracted and the script stops

#### Scenario: The image is built before it is proved

- **WHEN** `install.sh` has to probe the host
- **THEN** it builds the image of a step with Docker first, so that the probe runs in it

#### Scenario: install.sh finds the profile of the host

- **WHEN** `SHELF_STEP_DOCKER` is `on`, the host is ready and no profile is set
- **THEN** `install.sh` asks the script to probe, writes the profile it names into the environment file, and does not probe again on later runs

#### Scenario: install.sh finds the runtime missing

- **WHEN** `SHELF_STEP_DOCKER` is `on`, the runtime is missing and a person is at the terminal
- **THEN** `install.sh` shows what is missing, asks before running the host script through `sudo`, and goes on only if the check then passes

### Requirement: The worker refuses an isolation setting it cannot honour

The system SHALL read `SHELF_ISOLATION` when the worker starts, SHALL run the agents in the worker under the sandbox when it is unset or `sandbox`, and SHALL refuse to start, naming the setting and the accepted values, when it holds anything else or asks for `container` without what that mode needs (the runner's token and the folders of the clones, the tools and the sessions that it shares with the runner), so that an agent never runs with less isolation than the operator asked for.

#### Scenario: Unset

- **WHEN** `SHELF_ISOLATION` is not set
- **THEN** the worker starts and the agents run in it under the sandbox, as before

#### Scenario: A value that does not exist

- **WHEN** `SHELF_ISOLATION` is `vm`
- **THEN** the worker does not start and the message lists `sandbox` and `container`

#### Scenario: Container mode that cannot run

- **WHEN** `SHELF_ISOLATION` is `container` and the runner's token or one of the shared folders is not set
- **THEN** the worker does not start and the message names each missing setting, instead of falling back to the sandbox

#### Scenario: Container mode with everything set

- **WHEN** `SHELF_ISOLATION` is `container`, the runner's token is set and the three shared folders are given
- **THEN** the worker starts, clones into the shared folder and asks the runner for each agent step

#### Scenario: The model credential follows the worker into container mode

- **WHEN** the worker was given a model credential in the environment file and runs in container mode
- **THEN** it keeps that credential for the steps it asks the runner for, and no log, message or printed setting shows it

#### Scenario: A new shared folder is writable by the worker

- **WHEN** the volumes for the clones and the sessions are created empty on the first start in container mode
- **THEN** the worker, which does not run as root, can create what it needs in them, as it can in its other volumes

#### Scenario: The web service in container mode

- **WHEN** `SHELF_ISOLATION` is `container` in the environment file the services share
- **THEN** the web service still starts, because it runs no agent, and it holds neither the runner's token nor a shared folder

### Requirement: The step image's user lives in the home the tools are mounted on

The system SHALL give the step image's user, in the user database as well as in `HOME`, the home the runner mounts the repository's tools on, so that a program that reads its home from the user database and one that reads `HOME` agree.

#### Scenario: Both ways of asking give one home

- **WHEN** a program in a step container asks the user database for the home of the user it runs as
- **THEN** the answer is the folder `HOME` names

### Requirement: Links to pull requests use the GitHub address the App is registered on

The system SHALL build the links it shows to pull requests from the web address of the GitHub the App belongs to, github.com unless the operator names another.

#### Scenario: The default

- **WHEN** nothing names another GitHub
- **THEN** a pull request is linked at `https://github.com/<owner>/<repo>/pull/<number>`

### Requirement: The service can look at its own App on GitHub

The system SHALL wire, when the App's credentials are present, the means to read the App's own configuration from GitHub, so that the admin page can check it, and SHALL NOT need any setting beyond the App's credentials for it.

#### Scenario: A configured instance

- **WHEN** the web service starts with the App's id and private key
- **THEN** the admin page can ask GitHub about the App without further configuration

### Requirement: The worker image carries the GitHub command line

The system SHALL build the worker image with the GitHub command line, pinned and checked against its published checksum, so that an agent can read the CI runs of its pull request with the installation token it is given.

#### Scenario: The image is built

- **WHEN** the image is built for amd64 or arm64
- **THEN** `gh` is on the path and its download matched the pinned checksum

### Requirement: The worker keeps a cache for each repository's tools

The system SHALL ship the worker image with a pinned, checksum-verified `mise` and no toolchain, and give the worker a persistent volume, owned by the image's user, where the tools and package caches of each repository are kept.

#### Scenario: The image

- **WHEN** the image is built
- **THEN** `mise` is present at a pinned version whose download matched its published checksum, and no JDK, Node or Maven is installed in it

#### Scenario: The volume

- **WHEN** the stack starts
- **THEN** the worker has a writable cache volume that survives a recreate, and keeps its other mounts

### Requirement: One script fixes the Ubuntu host for the agents' sandbox

The system SHALL provide a script that finds what an Ubuntu 23.10+ host restricts for the sandbox (the user-namespace sysctl and the bubblewrap AppArmor profile), says what it will change and what that costs, asks before changing, makes the change survive a reboot, can undo it, and does nothing on a host that is already open; and the install script and the doctor SHALL point to it.

#### Scenario: A restricted Ubuntu host

- **WHEN** the operator runs the script on a host with either restriction active and agrees
- **THEN** both are lifted and persisted, the worker is restarted and the doctor runs

#### Scenario: Already open or not Ubuntu

- **WHEN** nothing is restricted, or the host is not Ubuntu
- **THEN** the script changes nothing and says so

#### Scenario: Undo

- **WHEN** the operator runs it with `--undo`
- **THEN** Ubuntu's defaults are restored

### Requirement: The operator can replay what a step meets and get a report safe to share

The system SHALL provide `shelf-diagnose`, run where the worker runs with a work id or `owner/repo#number`, that uses the App's real credentials to report, without ever printing a secret, which installation covers the repository and what it was granted and has not accepted yet, what GitHub says the pull request is, what git lists and whether the checkout a review does works, and for a work id the repository, the pull request and the latest failed or timed-out attempts of its workflow with their times and innermost messages. It SHALL also report the guard: each check of `warden doctor` as a finding, a warning counting as a failure because an unguarded agent is what this system must not run, and the counts of `warden report`; where the guard is not installed it SHALL say so as a note. Its exit code SHALL say whether anything failed, and its output SHALL be safe to paste into an issue or a chat.

#### Scenario: A repository the App is not installed on

- **WHEN** the repository has no installation of the App
- **THEN** the report says so and to install it, and goes no further

#### Scenario: A permission not accepted

- **WHEN** the App asks for a permission that the installation has not accepted
- **THEN** the report names it with what was asked and what is granted

#### Scenario: A work id

- **WHEN** it is run with a work id
- **THEN** the report starts from the workflow's own repository and pull request and lists its latest failed attempts

#### Scenario: Secrets

- **WHEN** a secret would appear in any line
- **THEN** it is blanked

#### Scenario: The guard is not wired

- **WHEN** `warden doctor` warns that Claude Code is not wired in any settings file
- **THEN** `shelf-diagnose` prints that warning as a failure and exits with status 1

#### Scenario: No guard installed

- **WHEN** the `warden` binary is not found
- **THEN** `shelf-diagnose` notes that the guard is not installed and does not count it as a failure

### Requirement: The install script catches the usual mistakes before building

The system SHALL, before building, refuse to continue when the public address or the session secret is empty or a Compose file it is about to use cannot be read, saying what Compose reported, or the web port is already used by something that is not this service, saying that the port is the private one the proxy forwards to and to set another, and SHALL warn about an environment file at the repository root, which Compose does not read.

#### Scenario: A busy port

- **WHEN** the configured web port is in use by another program
- **THEN** the script stops before building and tells the operator to set another port and point the proxy at it

#### Scenario: Our own service holds the port

- **WHEN** the web port is held by this service's own container from the last run
- **THEN** the script goes on, because it is about to replace it

#### Scenario: A Compose file that cannot be read

- **WHEN** a Compose file the script is about to use does not parse or does not validate
- **THEN** the script stops before it looks at the port and prints what Compose said, instead of reporting the port as busy

#### Scenario: The wrong file

- **WHEN** a `.env` exists at the repository root
- **THEN** the script warns that only `deploy/.env` is read

### Requirement: The web port's address is the operator's choice

The system SHALL publish the web port on every interface unless the operator sets `WEB_BIND`, SHALL say while it is unset that `127.0.0.1` makes a same-host reverse proxy the only way in, and SHALL NOT change an existing instance's reachability by itself.

#### Scenario: Unset

- **WHEN** no bind address is set
- **THEN** the port is published as before and the script prints the note

#### Scenario: Loopback

- **WHEN** `WEB_BIND=127.0.0.1`
- **THEN** the web service is reachable from the host itself and not from the network

### Requirement: The web service reads existing material to start work from

The system SHALL wire the web service to read the issues, pull requests and files that a start refers to, as the App, with an installation token minted for the request.

#### Scenario: A start from a file

- **WHEN** the form carries a reference
- **THEN** the service reads it before the work starts

### Requirement: Reference repositories are read by the worker and cached beside the tools

The system SHALL read reference repositories in the worker, with no credential, and SHALL keep their copies for an hour under the worker's cache directory when one is set, so that the agents' own network allow-list does not change.

#### Scenario: A cache directory

- **WHEN** a cache directory is set
- **THEN** the steps of one work share one download of each repository

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

### Requirement: The worker tells Temporal that a step is alive for as long as it runs

The system SHALL send a heartbeat from the worker every fifteen seconds for as long as a step runs, whatever it is doing (an agent working, a build, a wait for the repository's CI), so that Temporal never mistakes a long step for a dead one, and SHALL stop when the step ends. It SHALL read how long a step waits for the CI from `SHELF_CI_WAIT` and `SHELF_CI_GRACE`.

#### Scenario: A step that is silent for minutes

- **WHEN** a step waits for the CI for twenty minutes without any output
- **THEN** a heartbeat reaches Temporal every fifteen seconds and the step is not timed out

#### Scenario: The step ends

- **WHEN** the step finishes or fails
- **THEN** the heartbeats stop

### Requirement: The first-run page serves fingerprinted assets like the service

The system SHALL build the first-run setup page from the same templates and the same fingerprinted static addresses as the service, so that a browser that kept an old stylesheet from an earlier visit fetches the current one.

#### Scenario: The setup page's links

- **WHEN** the setup page is served
- **THEN** each stylesheet and script it links to carries a fingerprint and is served

### Requirement: The catalog is synced when the instance is installed

The system SHALL, when the install script runs, create the operator's `catalog.toml` from the example if it is absent and sync the catalog into volumes that the worker mounts read-only, for the skill plugins and for the managed policy, and SHALL stop with the reason when the sync fails, leaving the previous catalog in place.

#### Scenario: A first install

- **WHEN** the install script runs with no `catalog.toml`
- **THEN** the example is copied and the catalog it lists is synced

#### Scenario: A failing sync

- **WHEN** a source cannot be fetched
- **THEN** the install stops naming the source and the worker keeps the previous catalog

### Requirement: The image carries the tools the corporate plugins need

The system SHALL ship in the worker image the tools that the corporate plugins and managed hooks rely on (Node for plugin hooks, and the open-source edition of `rtk` for shell output), each pinned to a release and verified against its published checksum when the image is built.

#### Scenario: Building the image

- **WHEN** the image is built
- **THEN** Node and `rtk` are installed from pinned releases and the build fails if a checksum does not match

### Requirement: The image carries Warden, built from the same commit, with a volume for its log

The system SHALL build Warden from the repository's own `warden/` sources into the image, put it at `/usr/local/bin/warden`, give the worker the profile (`SHELF_WARDEN_PROFILE`, `shelf` by default), the operator's policy file (`config/warden.toml`, loaded as a locked layer), a state volume holding the audit log and a folder for the session tokens of sandboxed commands, and create `config/warden.toml` from a fully commented example on install without ever overwriting an edited one.

#### Scenario: The worker's environment

- **WHEN** the stack is started
- **THEN** the worker has `WARDEN_PROFILE`, `WARDEN_OPERATOR_POLICY`, `WARDEN_STATE_DIR` and `WARDEN_SESSION_DIR`, and the state volume is mounted

#### Scenario: The example changes nothing

- **WHEN** `config/warden.toml` is created from the example
- **THEN** it is valid TOML that sets nothing until the operator uncomments a part

#### Scenario: An edited file

- **WHEN** the operator edited `config/warden.toml` and the install script runs again
- **THEN** their file is as they left it

### Requirement: The catalog image is rebuilt before it syncs

The system SHALL, when the install script runs, build the catalog service's image before running the sync, because that service sits behind a profile and is not rebuilt with the web and worker images, so that the sync always runs from the revision just built and its managed policy carries what that revision ships (Warden's hooks).

#### Scenario: An update

- **WHEN** the install script runs after the checkout was updated
- **THEN** the catalog image is built before the sync runs

### Requirement: The install script says whether the guard is wired

The system SHALL, once the services are up, ask the worker's `warden doctor` and print that the guard is wired into the agents when it has no warning, or a warning that names each warning line when it has, so an operator learns at once, not after a run that found nothing, that the guard is not in force; and SHALL skip this when `SHELF_WARDEN` is `off`, and never fail the script because the check could not run.

#### Scenario: A guard that is wired

- **WHEN** `warden doctor` prints only `ok` lines
- **THEN** the script prints that the guard is wired into the agents

#### Scenario: A guard that is not wired

- **WHEN** `warden doctor` prints a `warn` line saying Claude Code is not wired
- **THEN** the script warns and repeats that line

#### Scenario: The guard is switched off

- **WHEN** `SHELF_WARDEN=off` is set in the environment file
- **THEN** the script does not ask the guard

### Requirement: The web service can read the guard's log

The system SHALL give the web service the guard's state volume read-only and the same `WARDEN_STATE_DIR` as the worker, so the admin page can report on what the agents did without being able to change the log.

#### Scenario: The compose file

- **WHEN** the compose file is read
- **THEN** the web service mounts the `warden-state` volume read-only at the path `WARDEN_STATE_DIR` names

### Requirement: The worker names the instance's administrators in the record of a decision

The system SHALL give the worker the instance's administrators as they are in the access file when a decision is recorded, so that a decision made by an administrator who holds no role of the repository says so in the record, and a change of the file is seen without a restart.

#### Scenario: An administrator decides

- **WHEN** a login listed under `admins` in the access file approves a spec of a repository that uses roles and lists them in none
- **THEN** the record says that the person acted as an administrator

### Requirement: The operator can switch the agents' web access off

The system SHALL read `SHELF_WEB` from the environment, `on` by default, and give agents no web tool when it is `off`, and SHALL refuse any other value, naming the variable.

#### Scenario: The default

- **WHEN** `SHELF_WEB` is not set
- **THEN** agents may read the web

#### Scenario: Off

- **WHEN** `SHELF_WEB=off`
- **THEN** no agent can fetch or search

#### Scenario: A value that is not understood

- **WHEN** `SHELF_WEB=maybe`
- **THEN** the service does not start and the message names `SHELF_WEB`

### Requirement: The rules added from the admin page live in a volume only the web service writes

The system SHALL keep the overlay policy file, the list of the rules and the change log in a named volume that the web service writes and the worker only reads, SHALL give the worker `WARDEN_OVERLAY_POLICY` pointing at the overlay file in it and the web service the folder, SHALL replace the overlay file as a whole (a new file renamed over the old one) so that a guard never reads half a file, and SHALL need no migration and no restart when it is first used or changed: the volume is created when the service starts, and the guard reads the file on each call.

#### Scenario: A first install of this version

- **WHEN** an operator updates an instance that has no such volume
- **THEN** the volume is created and the guard works as before, with no overlay

#### Scenario: The worker cannot write

- **WHEN** the worker's container tries to write in the volume
- **THEN** it cannot

#### Scenario: A rule added while an agent works

- **WHEN** an administrator allows a command while a step is running
- **THEN** the agent's next call sees it, with no restart

### Requirement: The web service can close the pull request of a work an administrator closes

The system SHALL give the web service the same access to pull requests as the worker has, so that closing a work from its page can close the pull request it opened, using the GitHub App's installation token and no other credential.

#### Scenario: A work is closed from its page

- **WHEN** an administrator closes a work from its page
- **THEN** the pull request is closed with the App's token, as the worker would

### Requirement: An operator can add a persistent Nix store that the worker only reads

The system SHALL, when the operator sets `SHELF_NIX=on`, run a Nix daemon as a service of its own with its store in a volume (a named volume, or a folder of the host the operator names in `SHELF_NIX_STORE`) that outlives every update, and give the worker that store read-only and the daemon's socket, so that the worker's client builds through the daemon and nothing the worker or an agent runs can write the store; SHALL leave the daemon out entirely, and change nothing else, when the operator has not set it; SHALL have the daemon collect garbage by itself when the disk runs low, and say how to empty the store by hand; SHALL have the install script bring the service up only when asked, and say whether the worker reaches the daemon.

#### Scenario: Not asked for

- **WHEN** `SHELF_NIX` is not set
- **THEN** no Nix service runs, and the worker's volumes and environment are what they were

#### Scenario: Asked for

- **WHEN** `SHELF_NIX=on` and the install script runs
- **THEN** the daemon runs with its store in a volume, the worker has the store read-only, and the script says that the worker reaches the daemon

#### Scenario: The worker cannot write the store

- **WHEN** a command in the worker's container tries to write in `/nix`
- **THEN** it cannot

#### Scenario: An update

- **WHEN** the operator updates and runs the install script again
- **THEN** the store is kept, so nothing is downloaded again

#### Scenario: The daemon does not answer

- **WHEN** the worker cannot reach the daemon
- **THEN** the install script warns, and the agents work as they do without it

#### Scenario: A host folder

- **WHEN** the operator sets `SHELF_NIX_STORE` to a folder of the host
- **THEN** the store lives there, so that it can be kept, copied or emptied from the host

### Requirement: The installer proves again the resolvers it stored, and stops when they no longer work

The system SHALL, when `SHELF_STEP_DOCKER` is `on` and `SHELF_STEP_DNS` is already set in the environment file, prove at every run of the installer that those resolvers still resolve the model's host from a step under the configured runtime, by asking the host script for that proof alone (`--dns`: read-only, a few seconds, one container). When the proof fails the installer SHALL stop before it starts anything, name the resolvers it tried, and say how to find others (remove the `SHELF_STEP_DNS` line and run the installer again, or set the right addresses). It SHALL NOT replace a value the operator set. The full probe (the profile too) SHALL still run only when the profile or the resolvers are missing.

#### Scenario: The stored resolvers still work

- **WHEN** the installer runs with both values set and the resolvers resolve in a step
- **THEN** it goes on without the full probe

#### Scenario: The stored resolvers no longer work

- **WHEN** the installer runs with `SHELF_STEP_DNS` set to addresses that no longer resolve in a step
- **THEN** it stops before anything starts, names the resolvers, and says how to find others, and the value is not changed

#### Scenario: The host script proves the resolvers alone

- **WHEN** the host script runs with `--dns`
- **THEN** it changes nothing, prints `dns=<resolvers>` when they resolve, and fails with what the step said when they do not

### Requirement: The operator can switch Nix on, and nothing else changes

The system SHALL read `SHELF_NIX` from the environment, `off` by default, SHALL accept `on` and `off` only and refuse any other value by name, and SHALL not change what the worker does with a repository that has no flake when it is on.

#### Scenario: The default

- **WHEN** `SHELF_NIX` is not set
- **THEN** it is off

#### Scenario: A value that is not understood

- **WHEN** `SHELF_NIX=maybe`
- **THEN** the service does not start and the message names `SHELF_NIX`

### Requirement: The worker reads the rules the page keeps

The system SHALL give the worker the folder where the web page keeps its rules, read-only, and its location in `SHELF_GUARD_RULES_DIR`, so that the sites an administrator added reach the agents' sandboxes; and SHALL run without them when the folder is not set.

#### Scenario: A deployment with the compose file

- **WHEN** the stack starts from the compose file
- **THEN** the worker has the rules folder read-only and the variable that names it

#### Scenario: No folder

- **WHEN** `SHELF_GUARD_RULES_DIR` is empty on the worker
- **THEN** only the built-in and configured sites are reachable

### Requirement: The worker keeps the records of agent runs where the web page can read them

The system SHALL give the worker a folder for the records of agent runs that it can write and the web service can only read, named by `SHELF_RUNS_DIR` in both services, in a volume of its own; and SHALL keep no record, and run as before, when the variable is empty.

#### Scenario: A deployment with the compose file

- **WHEN** the stack starts from the compose file
- **THEN** the worker writes the records into the volume and the web service reads them from it, read-only

#### Scenario: No folder

- **WHEN** `SHELF_RUNS_DIR` is empty
- **THEN** no record is kept and the downloaded file says so

### Requirement: The environment file can pin the model, in general and per agent role

The system SHALL read `SHELF_MODEL` and `SHELF_MODEL_<ROLE>` (one per agent role, the role's name in capitals) from the environment file of the worker, and SHALL stop at start with the names it accepts when a `SHELF_MODEL_*` variable names no role. The example environment file SHALL show both forms, commented out, and say what runs when none is set.

#### Scenario: A role with its own model

- **WHEN** the environment file sets `SHELF_MODEL_PLANNER`
- **THEN** the planner runs with that model and the other roles keep `SHELF_MODEL`, or the tool's own choice when it is not set

#### Scenario: A misspelled role

- **WHEN** the environment file sets `SHELF_MODEL_PLANER`
- **THEN** the service does not start and the message lists the roles it accepts

### Requirement: The web service is told when agents run in containers

The system SHALL, in container mode, give the web service `SHELF_AGENTS_IN_CONTAINERS=on` (the web service itself runs no agent and keeps `SHELF_ISOLATION=sandbox`), and SHALL read the setting as on or off, refusing any other value by name, so that the admin page can say what does not apply in that mode.

#### Scenario: Container mode

- **WHEN** the stack starts with the container compose file
- **THEN** the web service has `SHELF_AGENTS_IN_CONTAINERS=on` and the worker has `SHELF_ISOLATION=container`

#### Scenario: A value that is neither on nor off

- **WHEN** `SHELF_AGENTS_IN_CONTAINERS` is `maybe`
- **THEN** the service does not start and the message names the setting

### Requirement: The arbitrator's model is a role setting like the others

The system SHALL accept `SHELF_MODEL_ARBITRATOR` among the per-role model settings and list `ARBITRATOR` among the roles it names when a setting is misspelt; and the example environment file SHALL show it, saying that the arbitrator runs on `opus` when it is not set.

#### Scenario: The setting is set

- **WHEN** the environment file sets `SHELF_MODEL_ARBITRATOR`
- **THEN** the service starts and the arbitrator uses that model
