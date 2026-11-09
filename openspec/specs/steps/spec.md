# Steps

## Purpose

Carry out one step of the pipeline: a fresh clone, the agent role of the phase (or the project's own checks), and a result the state machine can use.

## Requirements

### Requirement: Every step runs in a fresh clone that is removed afterwards

The system SHALL clone the repository anew for each step, continue the work's branch if an earlier step pushed it, and remove the clone when the step ends, whatever its outcome.

#### Scenario: A later step

- **WHEN** a second step starts after a first one pushed
- **THEN** the clone contains what the first step pushed

#### Scenario: Cleanup

- **WHEN** a step ends
- **THEN** its clone no longer exists

### Requirement: Each role is limited to its own tools and budget

The system SHALL give each agent only the tools of its role, with reviewers read-only and only the implementer able to run commands, run inside the sandbox, and bounded in turns and money.

#### Scenario: A reviewer

- **WHEN** a code review runs
- **THEN** the agent may only read and search the clone

### Requirement: Producers leave their work on the work's branch

The system SHALL commit and push what a producing step wrote, to the work's branch, as the App's bot identity, and SHALL push nothing when nothing changed.

#### Scenario: A document

- **WHEN** the intake step writes the spec
- **THEN** the spec is committed and pushed to the work's branch

### Requirement: A reviewer's verdict is read from its last verdict line

The system SHALL take the last `VERDICT:` line of a reviewer's answer as its verdict and the text before it as the issues, and SHALL send the work to a person when there is no verdict.

#### Scenario: Changes requested

- **WHEN** a reviewer ends with `VERDICT: CHANGES`
- **THEN** the issues go back as feedback

#### Scenario: No verdict

- **WHEN** a reviewer gives no verdict line
- **THEN** it is never treated as approval

### Requirement: Agents get the tools the repository declares, and caches of its own

The system SHALL, when a cache directory is configured, give each step the home directory of its repository under that directory, with the tool shims of `mise` first on its path, trust only that step's clone, and tell the agent to install the declared tools, run the repository's own build and tests, and fix what fails before finishing; and SHALL NOT share a home or a cache between repositories.

#### Scenario: A repository with declared tools

- **WHEN** a step runs for a repository that declares its tools in `mise.toml`
- **THEN** the agent's home is that repository's own directory in the cache and its prompt tells it to run `mise install` and then the repository's tests

#### Scenario: Two repositories

- **WHEN** steps run for two repositories
- **THEN** each has a different home, so nothing one downloads is seen by the other

#### Scenario: No cache directory

- **WHEN** no cache directory is configured
- **THEN** the agent's environment and prompt are unchanged

### Requirement: The sandbox reaches only the sites a build needs

The system SHALL let sandboxed commands reach only the tool downloads, the common package registries and GitHub, plus the sites the operator adds.

#### Scenario: An extra registry

- **WHEN** the operator lists an extra domain
- **THEN** it is reachable in addition to the defaults, and nothing else is

### Requirement: Checks run the repository's own commands

The system SHALL run each command the repository lists as a check in the clone and report every failure, with the end of its output, to the implementer.

#### Scenario: One command fails

- **WHEN** one of two checks exits non-zero
- **THEN** the report names that command and its exit code, and the step is not passed

### Requirement: A line of the request is shortened for the board

The system SHALL shorten a request to its first non-empty line, without markdown heading marks and with whitespace collapsed, and end it with an ellipsis when it is longer than ninety characters.

#### Scenario: A long first line

- **WHEN** the first line is longer than ninety characters
- **THEN** the summary is exactly ninety characters ending in an ellipsis

### Requirement: Checks do what they can here and rely on the repository's CI for the rest

The system SHALL, once the repository's own commands pass, read the CI of the pull request (every check run and commit status of its head commit) and SHALL decide from it: no run found after a short grace for runs to appear means the repository has no CI and the checks pass; every run finished without failure means they pass; any run that failed, timed out, was cancelled, failed to start or ended in a conclusion the system does not know means they fail, with each such run's name, link and what it reports sent to the implementer; a run still going, or waiting for a person to approve it on GitHub, means the checks wait. The system SHALL NOT wait for a CI after a local command failed. A step SHALL look at the CI every minute for up to half an hour and then hand the wait back to the workflow, which looks again without counting a round or running the commands again and without repeating its comment on the pull request. The report SHALL say, for the commands and for the CI separately, whether each passed, failed, was not configured or is still running, and SHALL NOT show a check that did not run as passed.

#### Scenario: A cancelled run is a failure

- **WHEN** the head commit has a run that ended `cancelled` or `timed_out`
- **THEN** the checks fail and the implementer receives that run's name, link and report

#### Scenario: The CI is still running

- **WHEN** a run has not finished at the end of the step's share of the wait
- **THEN** the checks report that they wait, and the workflow looks again later in the same round

#### Scenario: No CI

- **WHEN** no run appears within the grace
- **THEN** the checks pass and the report says no CI run was found, not that CI passed

#### Scenario: A wait never needs a heartbeat of its own

- **WHEN** a step waits between two looks at the CI
- **THEN** it does nothing to stay alive: the activity that runs it heartbeats for it

#### Scenario: Local commands fail

- **WHEN** a configured command exits non-zero
- **THEN** the checks fail at once without reading the CI

### Requirement: The developer sees the CI too

The system SHALL give the developer, in its task, the state of the CI of the pull request and, for each failing run, what it reported including the end of the job's log, so that it fixes the cause without being able to reach GitHub itself, and SHALL tell it to read the first real error and never to answer that it cannot see the CI. The worker image SHALL carry the GitHub command line, so that an agent may look further with the token it is given.

#### Scenario: A round after a red CI

- **WHEN** the developer is asked to fix a red CI
- **THEN** its task names the failing runs with their logs

### Requirement: A reviewer never approves over a CI that is red or unfinished

The system SHALL give the code reviewer the state of the CI of the pull request and SHALL turn an approval into changes requested when the CI is red, and into a request for a person when it is not finished or waits for approval, whatever the reviewer's own verdict. The reviewer SHALL be told to read the whole picture (the repository's agent instructions, specs and decisions including older ones, and the CI workflows) and not only the diff.

#### Scenario: Approval over a red CI

- **WHEN** the reviewer answers APPROVE and a run of the CI failed
- **THEN** the verdict recorded is changes requested and lists the failing runs

#### Scenario: Approval while the CI runs

- **WHEN** the reviewer answers APPROVE and the CI has not finished
- **THEN** the verdict recorded asks a person to decide

### Requirement: A pull request under review receives the review

The system SHALL post the code review as a comment on a pull request that was submitted for review, and read that pull request's head without being able to push to it.

#### Scenario: Review my pull request

- **WHEN** the code review of a submitted pull request ends
- **THEN** its verdict and issues are posted on that pull request

### Requirement: A push refused for the Workflows permission is explained

The system SHALL, when GitHub refuses a push because it changes `.github/workflows` and the App lacks the Workflows permission, keep the refusal and add what to do: grant the permission and accept it on the installation, or make the change by hand.

#### Scenario: A step must change a workflow

- **WHEN** a step's push is refused for the Workflows permission
- **THEN** the failure the person reads names the permission and how to grant it

### Requirement: Secrets never appear in errors

The system SHALL NOT include the installation token in an error raised by a failed git command.

#### Scenario: A failed clone

- **WHEN** a clone fails
- **THEN** the error text does not contain the token

### Requirement: The agents' sandbox works inside a container when asked

The system SHALL run the agents' sandbox in its weaker nested mode only when the operator turns it on, which a container deployment does for the worker, and SHALL keep the sandbox on in both cases.

#### Scenario: Default

- **WHEN** the nested sandbox is not turned on
- **THEN** the sandbox is on in its normal mode

#### Scenario: In Docker

- **WHEN** the operator turns the nested sandbox on
- **THEN** the sandbox is on in its nested mode

### Requirement: A failed login tells the operator where the credential goes

The system SHALL, when an agent fails because it is not logged in, say that the credential belongs in the worker's environment (a Claude token or an API key in the environment file), not in the host's own login.

#### Scenario: Not logged in

- **WHEN** an agent step fails with a login error
- **THEN** the failure names the environment variables to set and where

### Requirement: The submitted text is recorded in the repository

The system SHALL write the text a person submitted into the work's document folder in the file its entry point implies (the request, the spec, the design or the plan), once, and never overwrite it, so that every agent and reviewer reads the same document from the repository.

#### Scenario: A submitted spec

- **WHEN** work starts from a spec
- **THEN** the spec is recorded as the spec the reviewers read, and committed

### Requirement: Every step says what it did on the pull request

The system SHALL post on the pull request, after each step, the producer's summary with the file it wrote, the reviewer's verdict with its issues, or the checks' result.

#### Scenario: A review

- **WHEN** a reviewer finishes
- **THEN** its verdict and issues appear as a comment on the pull request

### Requirement: The documents of a work have fixed names and an order

The system SHALL keep a work's request, spec, design and plan in fixed file names inside its document folder and give them titles and a reading order, so that the interface and the agents agree on where each is.

#### Scenario: The folder

- **WHEN** a work's documents are listed
- **THEN** they come as request, spec, design and plan, each with its title

### Requirement: Each step says enough for a person to follow without opening the repository

The system SHALL have a producer show, in its comment, its closing message and the document it wrote, and have the developer show what changed, and SHALL have the checks list every command with its result and the output of the failures.

#### Scenario: The checks

- **WHEN** one of two checks fails
- **THEN** both commands are listed with their result and the failing output is shown

### Requirement: Every agent works with the normal Claude Code toolset

The system SHALL give every agent the normal toolset, including a shell, so that reviewers can run git, the tests and linters like anyone, because they work in a throwaway clone without credentials and only producers' work is committed; and SHALL tell a reviewer the base branch so that the diff it is asked to read can be run.

#### Scenario: A code review

- **WHEN** the code reviewer is told to read the diff against the base branch
- **THEN** it can run `git diff` for it and anything else that helps it judge

### Requirement: Agents follow the repository's own agent files

The system SHALL start each agent with Claude Code's default prompt plus its role, SHALL load the repository's own agent files (CLAUDE.md, skills, commands), and SHALL NOT load its hooks or MCP servers, which would run code in the worker.

#### Scenario: A repository with a CLAUDE.md

- **WHEN** an agent starts in a repository that has a CLAUDE.md
- **THEN** it follows the rules written there

#### Scenario: A repository with hooks

- **WHEN** the repository's settings define hooks
- **THEN** none of them runs

### Requirement: Credentials are not in the clone and only the developer gets the token

The system SHALL clone with a remote address that carries no credential, SHALL authenticate each network command with a header that exists only for that command, so that nothing an agent can read contains the installation token, and SHALL put the token in the environment of the developer only.

#### Scenario: The clone's configuration

- **WHEN** a step's clone is made
- **THEN** its git configuration contains no token

#### Scenario: A reviewer

- **WHEN** a reviewer runs
- **THEN** its environment holds no installation token

### Requirement: The pull request is named by the repository's own convention

The system SHALL have an agent that reads the repository's conventions, its pull request title check and its history propose the title of the pull request, clean it, fall back to the first line of the request only when it proposes nothing usable, and never let naming stop the work.

#### Scenario: A Conventional Commits repository

- **WHEN** the pull request is published
- **THEN** its title follows the repository's convention

#### Scenario: The agent fails

- **WHEN** naming fails
- **THEN** the work continues with the fallback title
### Requirement: Every agent sees the whole picture

The system SHALL point each agent, in its task, at the conventions, existing specifications, architecture decisions and the specs of earlier work that already bind the repository, SHALL tell the producers not to contradict them silently, and SHALL make a contradiction at least a major issue for every reviewer.

#### Scenario: A repository with specs and decisions

- **WHEN** an agent starts on a repository that has specifications and decision records
- **THEN** its task lists them and says not to contradict them

#### Scenario: A conflict in the work

- **WHEN** a reviewer sees the work contradict an existing specification
- **THEN** it reports it as at least a major issue naming the file and the requirement

### Requirement: The pull request type comes from the intent of the whole request

The system SHALL have the agent that names the pull request choose its type from what the whole request asks for, ignoring the factory's own bookkeeping (its documents folder and its own commits), SHALL hand it the request and a diff that excludes that bookkeeping, and SHALL let it use `docs` only when the request is about documentation alone.

#### Scenario: A feature whose first commit is a document

- **WHEN** the only commit so far is the spec of a new capability
- **THEN** the title is not `docs` for that reason

### Requirement: The agents never see the worker's secrets

The system SHALL blank, in each agent's environment, the worker's secrets the agent has no use for (the App's credentials, the webhook and session secrets), leave the model credential and ordinary variables alone, and tell the operator that turning the sandbox off lets an agent read the worker's environment.

#### Scenario: An agent's environment

- **WHEN** an agent starts in a worker that holds the App's client secret
- **THEN** that variable is empty in the agent's environment
