# Steps

## Purpose

Carry out one step of the pipeline: a fresh clone, the agent role of the phase (or the project's own checks), and a result the state machine can use.

## Requirements

### Requirement: A repository with no base branch can still be worked on

The system SHALL, when the base branch cannot be cloned, tell an empty repository (no branch at all) from one that has other branches: for an empty repository it SHALL start the base branch with one empty commit so that the work branch and its pull request have something to be cut from and opened against, and for one that has other branches but not the named base it SHALL stop with the branches it has and the setting that names the right one, never choosing one on its own; a repository that cannot be reached SHALL report git's own error, and a review of a pull request on an empty repository SHALL be refused because there is none.

#### Scenario: A repository that was just created

- **WHEN** work starts on a repository with no commit
- **THEN** its base branch is created with an empty "initialise the repository" commit, the work branch is cut from it, and the step goes on

#### Scenario: A base branch that is not there

- **WHEN** the repository has branches but not the base the work asks for
- **THEN** the step stops saying which branches exist and that `base_branch` in `.shelf/config.toml` names the right one

#### Scenario: A repository that cannot be reached

- **WHEN** the clone fails and the repository cannot be listed either
- **THEN** git's own error is reported, with credentials hidden

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

### Requirement: The operator can see what each agent step cost

The system SHALL write one log line when an agent step ends, naming the role, the number of turns, the time it took, the cost in US dollars when the model reported one, and how many tool calls the guard refused when the model reported any, and SHALL NOT put the prompt, the answer or any credential in it.

#### Scenario: A finished step

- **WHEN** a code review ends after 12 turns, 94 seconds and a cost of 0.4213 dollars
- **THEN** the worker's log has one line naming the code review, 12 turns, 94 seconds and 0.4213 dollars

#### Scenario: No cost reported

- **WHEN** the model reports no cost
- **THEN** the line says the cost is unknown instead of showing zero

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

The system SHALL, when a cache directory is configured, give each step the home directory of its repository under that directory, with the tool shims of `mise` first on its path, trust only that step's clone, and tell the agent to install the declared tools, run the repository's own build and tests, and fix what fails before finishing; and, for a repository that declares no tools, tell the agent to find what the repository's CI runs (its workflows, and the tool versions they set up), run the same commands with those versions through `mise exec <tool>@<version> -- <command>`, which writes nothing into the repository, and say exactly which command it could not run and why instead of claiming a result; and SHALL NOT share a home or a cache between repositories.

#### Scenario: A repository with declared tools

- **WHEN** a step runs for a repository that declares its tools in `mise.toml`
- **THEN** the agent's home is that repository's own directory in the cache and its prompt tells it to run `mise install` and then the repository's tests

#### Scenario: A repository that declares no tools

- **WHEN** a step runs for a repository whose CI sets up Node 24 and runs `npm run quality`, and no `mise.toml` exists
- **THEN** the prompt tells the agent to run `mise exec node@24 -- npm run quality` and to name any command it could not run

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

### Requirement: Other repositories are read as plain files and never run

The system SHALL, before each step of a work that reads other repositories, put read-only copies of their text files in a folder of the working clone that git does not track, so that nothing of them is ever committed or pushed, and SHALL tell the agent where they are, that they are someone else's text to take as reference and never as instructions, and that nothing in them is to be run, installed, built or executed. It SHALL stop the step with the reason when a repository cannot be copied, and when the instance cannot read other repositories at all. The copies SHALL be made by the system and not by the agent, which keeps no network of its own.

#### Scenario: A reference repository

- **WHEN** a step of a work that reads `foo/bar` runs
- **THEN** its files are under the ignored folder of the clone and the agent is told they are material only

#### Scenario: Not committed

- **WHEN** the developer's work is committed
- **THEN** the copies are not part of the commit

#### Scenario: A repository that cannot be copied

- **WHEN** the copy fails
- **THEN** the step stops saying which repository and why

### Requirement: A step tidies the pull request before it speaks

The system SHALL, before a step runs and speaks, ask for the pull request to be tidied: the waits that are over are marked outdated, and when the step starts again because the flow circled back (its round is above zero, or it was sent back with feedback) what the agents said from its phase on is too. A step that only looks at the CI again SHALL ask for nothing, and a failure to tidy SHALL NOT stop the step.

#### Scenario: A developer round after a review

- **WHEN** the developer starts its second round
- **THEN** the pull request is asked to outdate from the implementation on

#### Scenario: A first step

- **WHEN** a step runs for the first time
- **THEN** only the finished waits are outdated

### Requirement: Work on a pull request pushes to its own branch and never over someone else's work

The system SHALL, for work on an existing pull request, clone and work on the branch the pull request was opened from and not on a branch of its own, SHALL record nothing of the work in that branch, SHALL push a branch that a rebase or an amendment rewrote although nothing is left to commit, and SHALL replace the remote branch only if it is still at the commit it was at when the step began, so that what the author pushed meanwhile is never overwritten. It SHALL refuse a pull request that is from a fork or no longer open, and SHALL tell the developer which pull request it is on, that it may rebase onto the base, that it has no credentials and does not push, and that the checks wait for the CI.

#### Scenario: A rebase

- **WHEN** the developer rebased the branch and nothing is left to commit
- **THEN** the system pushes the rewritten branch, replacing the old one only if it has not moved

#### Scenario: The author pushed meanwhile

- **WHEN** the author pushed to the branch while the step ran
- **THEN** the push is refused and the author's commit stays

#### Scenario: A fork

- **WHEN** the pull request comes from a fork
- **THEN** the step fails saying so and nothing is pushed

### Requirement: A pull request that cannot be fetched is named

The system SHALL, when the checkout of a pull request for a review cannot fetch it, say in the error which pull request of which repository could not be fetched, that the repository may have no such pull request or the App may not see it, and that the work may have been started on the wrong repository, without the token.

#### Scenario: A missing pull request

- **WHEN** a review checkout asks for a pull request the remote does not have
- **THEN** the error names the pull request and the repository and suggests checking the repository

### Requirement: Agents of a run that goes on past a deadlock are told nobody will answer

The system SHALL tell every agent of work whose policy proceeds on deadlock that nobody is available to answer, SHALL ask it to choose the most reasonable reading of an open point instead of stopping, and to write each such choice under an `Assumptions` heading of its document, and SHALL NOT say so to the agents of other work.

#### Scenario: Unattended work

- **WHEN** a step of work that proceeds on deadlock is prompted
- **THEN** the prompt says nobody will answer and asks for an `Assumptions` heading

#### Scenario: Attended work

- **WHEN** a step of work that does not proceed on deadlock is prompted
- **THEN** the prompt has no such note

### Requirement: Each agent role can have a model of its own

The system SHALL let the operator choose the model of each agent role with `SHELF_MODEL_<ROLE>`, where `<ROLE>` is the role's name in capitals (`INTAKE`, `SPEC_CRITIC`, `ARCHITECT`, `DESIGN_REVIEWER`, `PLANNER`, `IMPLEMENTER`, `CODE_REVIEWER`, `TITLER`). A role without a model of its own SHALL use `SHELF_MODEL`, and when that is not set either the system SHALL ask for no model and leave the choice to Claude Code. The run record of a step SHALL name the model the system asked for, else the one the provider reported. The system SHALL refuse to start, naming the variable and the roles, when a `SHELF_MODEL_` variable names no role, so that a misspelt name does not leave a reviewer on another model than the operator meant.

#### Scenario: A role with a model of its own

- **WHEN** `SHELF_MODEL_CODE_REVIEWER` and `SHELF_MODEL` are both set
- **THEN** the code review's task asks for the first, and every other role's task for the second

#### Scenario: No model set for a role

- **WHEN** neither `SHELF_MODEL_<ROLE>` nor `SHELF_MODEL` is set
- **THEN** the task asks for no model

#### Scenario: A misspelt role

- **WHEN** `SHELF_MODEL_REVIEWER` is set
- **THEN** the system does not start and says which roles exist

### Requirement: A reviewer of work that skips a stop decides what the author can decide

The system SHALL tell the spec reviewer and the design reviewer of work that does without a person at the spec or the design stop, and that still stops at a deadlock, that the person asked for the work to go on without them wherever it can. The reviewer SHALL NOT answer `ESCALATE` for a choice that the author can make from the request and the repository, even a trade-off: it SHALL recommend one option and ask for it with `CHANGES`, and the author records the choice under an `Assumptions` heading. The reviewer SHALL keep `ESCALATE` for what nobody here can decide (a contradiction of the request, a fact that is not in the repository, money or access). The system SHALL NOT add this note for work that stops at every stop, for work that proceeds on deadlock (which has its own note), or for any step that is not a spec or design review.

#### Scenario: A spec review of work that skips the spec stop

- **WHEN** the spec review of work that does without a person at the spec stop, and does not proceed on deadlock, is prompted
- **THEN** the prompt asks for `CHANGES` with a recommended option instead of `ESCALATE` for a choice the author can make

#### Scenario: Work that stops everywhere

- **WHEN** a review of work that skips no stop is prompted
- **THEN** the prompt has no such note

#### Scenario: Another step

- **WHEN** the step of the developer, or a code review, of work that skips a stop is prompted
- **THEN** the prompt has no such note

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

### Requirement: The operator chooses where agents run

The system SHALL read `SHELF_ISOLATION` as `sandbox` (the default: agents run in the worker, under the sandbox) or `container` (each agent step runs in a container of its own, decision 0019), SHALL refuse any other value at startup, and SHALL refuse `container` at startup, naming what is missing, unless the runner's address and token, and the three volumes it shares with the runner (the clones, the tools and the sessions), are set.

#### Scenario: Default

- **WHEN** `SHELF_ISOLATION` is not set
- **THEN** agents run in the worker under the sandbox, as before

#### Scenario: An unknown value

- **WHEN** `SHELF_ISOLATION` is `vm`
- **THEN** the worker does not start, and the message lists `sandbox` and `container`

#### Scenario: Container mode without a runner

- **WHEN** `SHELF_ISOLATION` is `container` and no runner or no shared volume is configured
- **THEN** the worker does not start, and the message names what is missing

#### Scenario: Container mode with everything set

- **WHEN** `SHELF_ISOLATION` is `container` and the runner and the three volumes are set
- **THEN** the worker starts and every agent step runs in a container of its own

### Requirement: A step in a container reports itself as a stream of versioned lines

The system SHALL have the code that runs in a step's container report what the agent does as lines of JSON on its standard output, starting with a `hello` line that carries the protocol version, followed by `tool`, `tool_result`, `audit` and `result` lines (or, for a repository's check, one `check` line with the command's exit code and the end of its output) and `ping` lines as a keepalive, and ending with an `exit` line written by whoever runs the container, never by the agent; and SHALL make the worker's reader ignore any field and any kind of line it does not know. A stream that ends without `exit`, a line that is not JSON and a protocol version newer than the worker knows SHALL fail the step, and the error SHALL NOT repeat the offending line.

#### Scenario: A round trip

- **WHEN** a step reports two tool calls, one of them failed, and a result
- **THEN** the worker's record of the run holds the same two tool calls, the failure with its note, the usage, the session, the stop reasons and the refused calls that the sandbox path would have kept

#### Scenario: A newer sender

- **WHEN** a line has a field or a kind that the worker does not know
- **THEN** the worker ignores it and the step goes on

#### Scenario: A stream that stops

- **WHEN** the stream ends without an `exit` line
- **THEN** the step fails, whatever came before

#### Scenario: A timeout is not a failure of the agent

- **WHEN** the `exit` line says the container was stopped for time
- **THEN** the step fails with a reason that names the time limit

#### Scenario: Nothing leaks into the error

- **WHEN** a line on the stream is not JSON
- **THEN** the step fails with a message that does not contain that line

#### Scenario: A session that cannot be continued

- **WHEN** a step asked to continue a session fails
- **THEN** the worker runs it again once from the whole task, and the record says it fell back, as the sandbox path does

### Requirement: The runner service starts each step in a container it builds itself

The system SHALL have a runner service, the only holder of the container engine's socket, that accepts a step as a fixed request (a key, a kind, a repository, a session folder, an environment and the task) with no field for mounts, capabilities, devices, ports, user, network, privileged mode or any engine option, and SHALL build the container itself: non-root, read-only root filesystem, every capability dropped, no new privileges, a process limit, a memory limit, a CPU limit, a sized temporary filesystem, an init process, no published port, volumes only and never a host path, and labels on every container it makes. The runner SHALL stream the lines the step wrote and then write the `exit` line itself, with a reason when the step ran out of time, was stopped or ran out of memory; SHALL return the same step, never a second container, when asked again with the same key; SHALL refuse a key, a repository, a session folder or an environment name that does not match its rules, naming the field and never repeating a secret; and SHALL accept requests only with the caller's token, refusing to start without one and without an engine it can read.

#### Scenario: A request cannot ask for more than the runner allows

- **WHEN** a request carries a field the runner does not know, such as `privileged` or `mounts`
- **THEN** the runner refuses it and starts no container

#### Scenario: The container is built the same way every time

- **WHEN** the runner starts a step
- **THEN** the container is non-root with a read-only root, all capabilities dropped, no new privileges, the limits the operator set, no published port and no host path

#### Scenario: Asking again

- **WHEN** a request arrives with the key of a step that is running or finished
- **THEN** the runner streams that step from its first line and starts no second container

#### Scenario: A step that runs out of time

- **WHEN** a step is still running when its time is up
- **THEN** the runner stops and removes the container and ends the stream with an `exit` line whose reason is `timeout`

#### Scenario: A name that does not match

- **WHEN** the environment of a request names a variable outside the allowed patterns, or the repository is not `owner/name`
- **THEN** the runner refuses the request with a message that names the field and does not contain the value

#### Scenario: No token

- **WHEN** a request does not carry the caller's token
- **THEN** the runner answers that it is not allowed and does nothing else

#### Scenario: Nothing to authenticate with

- **WHEN** the runner starts with no caller token and without the operator's explicit permission to run without one
- **THEN** it does not start, and the message says a token is needed

#### Scenario: The runner restarts

- **WHEN** the runner starts and finds containers with its label whose time has passed
- **THEN** it stops and removes them, and it leaves every container without its label alone

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

### Requirement: The repository's checks run without the worker's secrets

The system SHALL run the repository's own commands (its `checks`, and the commands the system itself runs in the clone) with
the worker's environment minus the worker's secrets and the model credential: the session and webhook secrets, every GitHub App
setting, and the Claude token and API key. The ordinary variables a command needs (such as `PATH`) are kept.

#### Scenario: A check that prints its environment

- **WHEN** a repository's check prints its environment and the worker's environment holds the session secret, a GitHub App
  setting and the model credential
- **THEN** none of those appear in the output

#### Scenario: An ordinary variable

- **WHEN** a check reads `PATH`
- **THEN** it has the worker's value

### Requirement: Agents run without telemetry or automatic memory

The system SHALL start every agent with telemetry off and Claude Code's automatic memory off, so that nothing an agent learns in one step is carried into another, unless the step's own environment says otherwise.

#### Scenario: An agent's environment

- **WHEN** an agent starts
- **THEN** its environment turns telemetry off and automatic memory off

### Requirement: An agent loads the skill bundles bound to its role

The system SHALL load into each agent the generated skill plugins that the operator bound to its role, taken from the synced catalog, and SHALL skip, with a warning, a bound name that the catalog does not have. Plugins registered for every agent are enabled by the managed policy, not here.

#### Scenario: A bound role

- **WHEN** the implementer is bound to a source the catalog has
- **THEN** that source's plugin is loaded for the implementer and not for the spec critic

#### Scenario: A name the catalog lacks

- **WHEN** a role is bound to a name the catalog does not have
- **THEN** the agent starts without it and the warning names it

#### Scenario: No catalog

- **WHEN** the instance has no synced catalog
- **THEN** agents start with no extra plugin

### Requirement: Every agent step runs under Warden

The system SHALL have every agent's tool calls judged by Warden through the managed policy, which repository settings cannot override: commands are checked and wrapped so that their output is redacted, file reads, writes and fetches are checked, and a call that Warden cannot judge is refused; the operator's locked policy and the repository's own `.warden/policy.toml` (which can only tighten it) apply.

#### Scenario: A dangerous command

- **WHEN** an agent runs a command that downloads text and pipes it into a shell
- **THEN** the call is refused with a reason, and the decision is in the audit log

#### Scenario: A repository that tries to loosen the guard

- **WHEN** a repository's `.warden/policy.toml` allows what the operator's file denies
- **THEN** the operator's rule holds

### Requirement: The work's own files live in a `.shelf` folder, and what lasts goes where the repository keeps it

The system SHALL keep the documents of a piece of work (the request, the spec, the design and the plan) in `.shelf/<work-id>/` of the repository, and SHALL still read the `docs/shelf/<work-id>/` folders that earlier runs left. The result of the work that is meant to last SHALL be written where the repository keeps such things: a change of behaviour as a requirement with scenarios in the repository's specs folder (`openspec/specs/<capability>/spec.md` by default), and a lasting architectural choice as a decision record in its decisions folder (`docs/adr/` by default, numbered after the last one and following its template).

#### Scenario: A run that changes behaviour

- **WHEN** a run for a repository that keeps its specs in `openspec/specs/` changes what the software does
- **THEN** the pull request changes the requirement of that capability in `openspec/specs/`, and the run's own documents are under `.shelf/<work-id>/`

#### Scenario: An older run

- **WHEN** a repository holds `docs/shelf/work-0/spec.md` from an earlier run
- **THEN** it is still offered to the agents as earlier work

### Requirement: A repository with no specs or no decision records gets them started

The system SHALL, when a run has to write a spec or a decision record and the repository has no such folder, create it in the form the project's own conventions describe, or in the standard form (a `README.md` that says how to write one; for decisions the template and the first record that decides to keep records), and SHALL NOT drop the result because the folder is missing.

#### Scenario: A repository with no `openspec`

- **WHEN** a run changes behaviour in a repository that has no `openspec/` folder
- **THEN** the pull request creates `openspec/specs/<capability>/spec.md` and the folder's `README.md`

### Requirement: A new decision record must not contradict an earlier one by accident

The system SHALL have the design reviewer compare a new decision record with every earlier accepted record and refuse the design when they conflict, unless the request says the earlier decision is to be changed or the new record states that it supersedes it, in which case the earlier record's status SHALL be changed to superseded and nothing else in it rewritten; with the conflict setting `warn` the conflict SHALL be reported without refusing, and with `off` it SHALL NOT be checked.

#### Scenario: A silent contradiction

- **WHEN** a design's record chooses a database that an accepted record rules out, and neither the request nor the record mentions it
- **THEN** the design reviewer's verdict is a refusal that names both records

#### Scenario: A stated change

- **WHEN** the request says to replace the earlier choice and the new record says `supersedes 0007`
- **THEN** the design is not refused, and record 0007's status becomes `superseded by` the new record

#### Scenario: A conflict under `warn`

- **WHEN** the setting is `warn` and a record conflicts with an earlier one
- **THEN** the conflict is written in the review and the verdict is not a refusal

### Requirement: A spec is as large as the request

The system SHALL tell the spec writer that the size of the spec follows the size of the request: a small request gets a handful of requirements, each describing behaviour a person can observe; it SHALL NOT add requirements for tests, tooling, lint rules or process that the request did not ask for; a section with nothing to say is left out or reduced to one line; and a fact it cannot check (a tool it cannot run, a document it cannot read) goes under open questions in one line, never into a requirement.

#### Scenario: A two-sentence request

- **WHEN** the request asks to support one more client the way two others are supported
- **THEN** the spec states what changes for that client and where it is named, in a few requirements, with no new test framework

#### Scenario: Something it cannot check

- **WHEN** the writer cannot read the documentation of a tool the request names
- **THEN** it says so in one line under open questions, and no requirement depends on it

### Requirement: The spec and design reviewers approve what can be built and do not add scope

The system SHALL tell the spec reviewer and the design reviewer to approve a document a team could build from, to list only problems that would stop the work (an untestable requirement, a contradiction with a specification or decision that binds the repository, a requirement the request does not imply that makes the work bigger), at most five, most serious first, and to treat a requirement or design element that goes beyond the request as a major issue; and SHALL NOT have them ask for more tests, tooling, edge cases or process than the request calls for, nor repeat a point the author has fixed.

#### Scenario: A document that is buildable

- **WHEN** a spec has a few testable requirements that match the request and one minor wording issue
- **THEN** the verdict is to approve

#### Scenario: A spec that grew past the request

- **WHEN** a spec adds a lint test and a tool the request never asked for
- **THEN** the review names them as a major issue and asks for their removal, not for more detail

### Requirement: The repository's own specs are written after the spec is approved

The system SHALL have the requirements of a piece of work written into the repository's own specs folder by the architect, after the spec has been approved, and SHALL keep the run's own `spec.md` as the only copy of the spec while it is being reviewed, so that two copies are never kept in step during review.

#### Scenario: A spec in review

- **WHEN** the spec writer and the spec reviewer go through their rounds
- **THEN** only `.shelf/<work-id>/spec.md` changes

#### Scenario: After approval

- **WHEN** the spec has been approved and the architect designs the change
- **THEN** the requirements are written into `openspec/specs/` and the design says so

### Requirement: The depth of a review follows the repository's choice

The system SHALL tell the spec reviewer and the design reviewer how deep to look according to the depth chosen for that review when the work was started, or else the repository's `spec_review_depth` or `design_review_depth`: with `quick`, one reading, only the problems that would stop the work from being built or tested, at most three, approving when a team could build from the document; with `standard`, the reviewers' own instructions unchanged; with `thorough`, a hard look at edge cases, failure modes, what is missing and what is vague, up to ten problems; and SHALL NOT change the depth of the code review, which judges correctness.

#### Scenario: A quick review

- **WHEN** the repository's depth is quick and the spec reviewer is started
- **THEN** its task says to report at most three problems that would stop the work and to approve a document a team could build from

#### Scenario: A thorough review

- **WHEN** the design review's depth is thorough and the design reviewer is started
- **THEN** its task asks for edge cases, failure modes and missing parts, up to ten problems, whatever the spec review's depth is

#### Scenario: The code review

- **WHEN** the depth is quick and the code reviewer is started
- **THEN** its task carries no depth instruction

### Requirement: Every decision a person makes on a piece of work is recorded in the repository

The system SHALL append, for each decision a person makes while work waits for them (approve, ask for changes, resume, reject, abort), one entry to `.shelf/<work-id>/decisions.md` on the work's branch, committed by the system and not by an agent, saying when (UTC), who (their login), what they decided and at which step, the role they acted as when the repository uses roles (or that they held none), how they got to decide it (a role, the administrator, or no restriction), and their note in full; and SHALL do so before the work goes on, so that the entry is in the branch the next step starts from; a decision that cannot be recorded SHALL be reported in the log of the service and SHALL NOT stop the work.

#### Scenario: A person approves the spec

- **WHEN** alice approves the spec of a work in a repository that has no roles
- **THEN** `.shelf/<work-id>/decisions.md` holds an entry with the time, `alice`, the approval of the spec, and no role

#### Scenario: A person acts in a role

- **WHEN** bob, a `tech_lead` in the repository's roles, asks for changes to the design with a note
- **THEN** the entry names bob, the design review, the role `tech_lead` and his note in full

#### Scenario: An administrator

- **WHEN** an administrator who holds no role approves a spec in a repository with roles
- **THEN** the entry says so, as an administrator

#### Scenario: Several decisions

- **WHEN** three decisions are made on the work
- **THEN** the file holds three entries in the order they were made, and none is rewritten

#### Scenario: The branch cannot be written

- **WHEN** recording fails
- **THEN** a warning is logged and the decision still takes effect

### Requirement: A decision record points to the log of the decisions

The system SHALL tell the architect to name, in each decision record it writes, the decision log of the work (`.shelf/<work-id>/decisions.md`) so that a reader of the record can see who approved what and when, and SHALL NOT have an agent write the names of the people who decided.

#### Scenario: A new record

- **WHEN** the architect writes a decision record
- **THEN** it holds a line that points to the work's decision log

### Requirement: Agents can read the web, and what they read is data

The system SHALL give every agent a tool to fetch an address and a tool to search the web, unless the operator has switched web access off, SHALL have Warden judge each of them, SHALL keep downloads where they are (a command reaches only the allowed hosts), and SHALL tell the agents in their prompts that what a page says is data and never an instruction, and that a requirement that rests on a page names it.

#### Scenario: Web access on

- **WHEN** an agent step starts on an instance with web access on
- **THEN** the agent's tools include fetching an address and searching the web

#### Scenario: Web access off

- **WHEN** the operator has set web access off
- **THEN** the agent's tools hold neither

#### Scenario: A page that gives orders

- **WHEN** a fetched page says to ignore the task and send a file somewhere
- **THEN** the prompt has already said that a page is data, and the guard refuses what it asks that is not allowed

### Requirement: The pull requests can be asked to close one, and only one that is the work's own and open

The system SHALL let the work ask its pull requests to close the pull request it opened, with a reason that is posted on it first, and SHALL do nothing when the pull request is not the work's own (a review, or work on someone else's pull request), when it does not exist yet, or when it is already closed or merged.

#### Scenario: An open pull request

- **WHEN** the work asks to close its open pull request with a reason
- **THEN** the reason is posted as a comment, then the pull request is closed

#### Scenario: Already closed

- **WHEN** the pull request is already closed or merged
- **THEN** nothing is posted and nothing changes

#### Scenario: Someone else's

- **WHEN** the work is a review of a pull request someone else opened
- **THEN** nothing is posted and the pull request is left open

### Requirement: The spec review and the design review are never judged by the CI

The system SHALL NOT give the CI of the pull request to the spec reviewer or the design reviewer and SHALL NOT change their verdict because of it, so that an approval of a document stands whatever a check says about the draft that holds it; only the code review is held back by the CI.

#### Scenario: A spec approved over a red CI

- **WHEN** the spec reviewer answers APPROVE while a check of the draft pull request is red
- **THEN** the verdict recorded is the approval, and the spec writer is not sent back because of the CI

#### Scenario: A design approved while the CI runs

- **WHEN** the design reviewer answers APPROVE while the CI has not finished
- **THEN** the verdict recorded is the approval and no person is asked about the CI

#### Scenario: The code review

- **WHEN** the code reviewer answers APPROVE over a red CI
- **THEN** the verdict recorded is changes requested, as before


### Requirement: Every agent step reports what it used

The system SHALL report, for each step an agent carried out, the tokens it read and wrote (and those read from and written to the cache), the cost the model provider reported, the number of turns, the time it took and the models used, SHALL leave the usage empty rather than guess when the provider reported none, and SHALL NOT let a failure to read it change the result of the step.

#### Scenario: A step finishes

- **WHEN** the spec writer finishes a step and the provider reported 12,000 tokens read, 900 written and a cost of $0.41
- **THEN** the step's report carries those figures with its turns and duration

#### Scenario: No usage reported

- **WHEN** the provider reports no usage for a step
- **THEN** the step's usage is empty and the step's result is unchanged

### Requirement: The worker sets up the tools the repository's CI uses, before the code steps, when the repository declares none

The system SHALL, when a cache directory is configured and before the developer or the code reviewer starts, read the repository's CI workflows and version files (the versions its `setup-node`, `setup-python`, `setup-go` and `setup-java` steps use, `.nvmrc`, `.node-version`, `.python-version`, the `engines` of `package.json` and the `go` line of `go.mod`) and install those versions of Node, Python, Go and Java itself, outside the agent's sandbox, into the repository's own home so that the agent finds them on its path; SHALL do nothing of the kind, and leave the agent to run `mise install`, when the repository declares its tools in `mise.toml`, `.mise.toml` or `.tool-versions`; SHALL install only those four tools and only from a plain version number or `lts`, never a name or an address the repository wrote; SHALL tell the agent what was installed, or why nothing was, instead of letting it find out; and SHALL NOT stop the step when the installation fails.

#### Scenario: A repository whose CI sets up Node 24

- **WHEN** the developer starts on a repository with no `mise.toml` whose workflow sets up Node 24
- **THEN** Node 24 is installed into the repository's home before the agent starts, and the agent's task says so

#### Scenario: A repository that declares its tools

- **WHEN** the repository has a `mise.toml`
- **THEN** nothing is detected or installed by the worker and the agent is told to run `mise install` as before

#### Scenario: A version that is not a plain version

- **WHEN** a workflow sets the Node version from an expression or a URL
- **THEN** it is ignored

#### Scenario: The installation fails

- **WHEN** the installation fails or takes too long
- **THEN** the step goes on and the agent is told which tool could not be installed

#### Scenario: The second time

- **WHEN** another piece of work starts on the same repository
- **THEN** the tools are already in its home and nothing is downloaded again

### Requirement: An operator can clear the caches the agents' tools live in

The system SHALL provide `shelf-cache prune`, which removes the home of every repository that nothing used for a number of days (30 unless told otherwise), says what it removed and how much space that freed, and removes nothing outside the cache directory.

#### Scenario: An old home

- **WHEN** the home of a repository was last used 40 days ago and `shelf-cache prune` runs with the default
- **THEN** it is removed and the output says so with its size

#### Scenario: A recent home

- **WHEN** a home was used yesterday
- **THEN** it is kept

### Requirement: The documents an agent writes are formatted as the repository formats its files

The system SHALL tell each agent that writes a document of the work (the spec, the design, the plan) that the document is committed to the repository and checked by the repository's own formatter and linters, and to run the formatter on the files it wrote when the repository has one, so that the work's own files never fail a check that covers the whole repository.

#### Scenario: A repository that checks formatting

- **WHEN** the planner is started on a repository whose CI runs `prettier --check .`
- **THEN** its task tells it to run the repository's formatter on `plan.md` before it finishes

#### Scenario: A step that writes no document

- **WHEN** a reviewer is started
- **THEN** its task carries no such note

### Requirement: An agent that is sent back continues its own session

The system SHALL, when an agent runs again on the same work (sent back by a reviewer, by the checks or by a person), continue the session it ran before instead of starting a new one, and tell it that this is round N, that the working copy is a fresh checkout of the work's branch holding what everyone pushed since, to re-read what changed before answering and to address the feedback first, without repeating the whole task; SHALL start a new session for an agent that has none, and when the session cannot be continued (it is gone, or the agent refuses it) SHALL run it again from the whole task, with the failure logged, so that a step never fails because a session could not be found.

#### Scenario: The spec writer is sent back

- **WHEN** the spec reviewer asks for changes and the spec writer runs its second round
- **THEN** it continues its first session, its task says it is round 1 and carries the reviewer's feedback, and it is not given the whole request again

#### Scenario: The first round

- **WHEN** an agent runs for the first time on a work
- **THEN** it starts a new session and the session's id is kept

#### Scenario: The session is gone

- **WHEN** the session of an earlier round cannot be continued
- **THEN** the step runs from the whole task and the work goes on

#### Scenario: Two agents

- **WHEN** the spec writer and the spec reviewer both ran
- **THEN** each continues its own session and neither sees the other's

### Requirement: When Nix is on, the worker turns a repository's flake into the environment of the agent

The system SHALL, when `SHELF_NIX` is on and before the developer or the code reviewer starts, use the repository's own `flake.nix` development shell when its CI runs through Nix (a workflow that installs Nix or runs `nix develop`) or when it declares no tools for mise and its CI sets up none the system knows; SHALL ask Nix for that shell's environment without entering it, in a scrubbed environment that holds no credential, with a time limit, and without writing into the repository (no lock file, no shell hook run); SHALL give the agent the `PATH` of that environment before its other paths, and the plain exported variables it sets that are safe to pass (never the home, the shell, a Nix variable or a value that is not plain text); SHALL tell the agent what was made available, or why not, and never stop the step; and SHALL do nothing of this when the repository declares its tools for mise.

#### Scenario: A repository whose CI runs through Nix

- **WHEN** the developer starts on a repository with a `flake.nix` whose workflow runs `nix develop`
- **THEN** the agent's path holds the tools of the flake's development shell and its task says so

#### Scenario: A repository whose CI sets up Node

- **WHEN** the repository has a `flake.nix` and its workflow sets up Node 24 with `setup-node`, and does not use Nix
- **THEN** the worker installs Node 24 as before and does not evaluate the flake

#### Scenario: Nix is off

- **WHEN** `SHELF_NIX` is not on
- **THEN** the flake is not looked at

#### Scenario: The flake does not evaluate

- **WHEN** Nix fails on the flake, or takes longer than the time limit
- **THEN** the step goes on and the agent is told why nothing was made available

#### Scenario: Nothing leaks into the evaluation

- **WHEN** the worker's environment holds a token
- **THEN** the process that evaluates the flake does not receive it

#### Scenario: The repository is left as it was

- **WHEN** the flake has no lock file and a shell hook
- **THEN** no lock file is written and the hook does not run

### Requirement: The decision log is one of the documents of a work

The system SHALL count the log of decisions (`decisions.md` in the work's documents folder) among the documents of a piece of work, after the plan, written only by the system and never by an agent, so that whatever lists the work's documents lists it.

#### Scenario: The documents of a work

- **WHEN** the documents of a work are listed
- **THEN** the request, spec, design and plan come first and the decision log last

#### Scenario: Who writes it

- **WHEN** an agent step runs
- **THEN** no agent's role names the decision log as its document

### Requirement: The code review waits for the CI to finish before it judges

The system SHALL, before the code reviewer is asked, wait for the CI of the pull request to finish, as the checks step does and for as long as it does, so that a run that the work's own label changes or pushes started a moment ago is not mistaken for an unfinished CI that needs a person; and SHALL otherwise keep what the code reviewer is told and how its verdict is held back.

#### Scenario: A workflow retriggered by a label

- **WHEN** the stage label changes before the code review and the repository's workflow starts again
- **THEN** the code review starts once that run has finished, and its verdict is judged on it

#### Scenario: The CI never finishes

- **WHEN** the CI is still running when the waiting ends
- **THEN** the code review proceeds with the unfinished CI and its approval asks a person, as before

#### Scenario: A run starts while the reviewer works

- **WHEN** the CI was finished when the code reviewer was asked, a run shows up while it works, and it approves
- **THEN** the system waits for that run to finish and judges the approval on it, instead of asking a person about a CI that was not running when the review began

### Requirement: A repository's formatter does not check Shelf's own files

The system SHALL, when a repository uses Prettier (a Prettier configuration file, or `prettier` in its `package.json`), make sure its `.prettierignore` names the `.shelf/` folder, creating the file or adding one line, before the first step commits, so that a check that formats or checks the whole repository never fails on the request, the spec, the design, the plan or the decision log of a piece of work; SHALL change nothing when the folder is already ignored or when the repository does not use Prettier; and SHALL NOT download or run any program to do it.

#### Scenario: A repository that checks formatting with Prettier

- **WHEN** a work starts on a repository whose `package.json` lists `prettier` and has no `.prettierignore`
- **THEN** the first commit adds a `.prettierignore` that ignores `.shelf/`

#### Scenario: An existing ignore file

- **WHEN** the repository's `.prettierignore` lists other folders
- **THEN** a line for `.shelf/` is added after them and nothing else changes

#### Scenario: Already ignored

- **WHEN** the repository's `.prettierignore` already ignores `.shelf`
- **THEN** it is left as it is

#### Scenario: No Prettier

- **WHEN** the repository does not use Prettier
- **THEN** no file is created

#### Scenario: Run twice

- **WHEN** a second step starts on the same work
- **THEN** nothing is added again

### Requirement: Only the steps that build and test are told about tools

The system SHALL tell an agent about the repository's tools, and to install and run them, only when its step builds or tests (the developer and the code reviewer), and SHALL NOT give the spec writer, the architect, the planner or the reviewers of the spec and the design any such instruction, since they run no build and the tools are not available to them, so that they never spend turns trying to install a toolchain.

#### Scenario: The architect

- **WHEN** the architect is started on a repository with a cache directory
- **THEN** its task says nothing about installing tools

#### Scenario: The developer

- **WHEN** the developer is started on the same repository
- **THEN** its task carries the note about the repository's tools as before

### Requirement: The worker installs a Node repository's dependencies for the steps that build and test

The system SHALL, for the developer and the code reviewer on a repository whose CI uses Node, whose `package-lock.json` exists and whose `node_modules` does not, run `npm ci --ignore-scripts` in the clone, in the worker and outside the agent's sandbox, after the tools are installed, so that the repository's own linters, formatters and test runners (Prettier among them) are on disk when the agent starts and it never has to download them with `npx`; SHALL NOT run the dependencies' install scripts; SHALL tell the agent that the dependencies are installed, or that they could not be and why; and SHALL treat a failure as information for the agent, never as a failure of the step.

#### Scenario: A repository with a lockfile

- **WHEN** the code reviewer starts on a Node repository with a `package-lock.json` and no `node_modules`
- **THEN** the worker installs the dependencies without running their scripts and the reviewer is told they are installed

#### Scenario: The install fails

- **WHEN** `npm ci` fails
- **THEN** the step goes on and the agent is told that the dependencies are missing and the last line of the error

#### Scenario: No lockfile or already installed

- **WHEN** the repository has no `package-lock.json`, or `node_modules` already exists
- **THEN** the worker installs nothing

### Requirement: The code reviewer asks for what the author can still fix

The system SHALL tell the code reviewer that it approves only when it has nothing left that the author could fix in this pull request, however small (a stale sentence, a list that does not name the new case, a missing test), that every such item is a request for changes, and that what it writes under an approval is only what needs a person's judgment or a check nobody could run, so that an approval is never followed by a list of leftovers that no agent will read.

#### Scenario: A minor leftover

- **WHEN** the code reviewer finds a wording the change forgot to update
- **THEN** it is told to answer changes requested, not approve with a note

#### Scenario: Something only a person can judge

- **WHEN** what remains is a behaviour nobody could run in this environment
- **THEN** it may approve and say what a person has to confirm

### Requirement: The developer ends on the repository's own gate and its spec rule

The system SHALL tell the developer that the last thing it runs, after its final edit, is the repository's own gate as the repository's instructions name it (and the repository's spec-drift check when it has one), that a rule of the repository about changing code only together with its specification binds the developer too, and that it cannot add a label or a commit line: so a change to a source file that the repository's rules tie to a specification either updates that specification or is not made.

#### Scenario: A comment-only change in source

- **WHEN** the plan touches a doc comment in a source file that the repository's rules tie to a specification
- **THEN** the developer is told to update that specification or leave the file alone, never to rely on a label it cannot set

### Requirement: A reviewer says where it stands on its earlier points

The system SHALL tell every reviewer (the spec critic, the design reviewer and the code reviewer), in its first task and in the task of a round that continues its session, to write before its verdict a line `REPEATED: <n>` with the number of points it raised in an earlier round that remain unaddressed, and a line `BLOCKING: yes|no` saying whether any open point must be fixed before the work can merge; SHALL read them from the answer, taking none for `REPEATED` and yes for `BLOCKING` when a line is missing; and SHALL mark a review whose approval was held back by the CI as blocking.

#### Scenario: The lines are present

- **WHEN** a reviewer answers with `REPEATED: 1`, `BLOCKING: no` and `VERDICT: CHANGES`
- **THEN** the review is reported as changes with one repeated point and nothing blocking

#### Scenario: The lines are missing

- **WHEN** a reviewer answers with only a verdict
- **THEN** nothing is repeated and the review is blocking

#### Scenario: Approval held back by the CI

- **WHEN** a reviewer approves over a CI that is red or unfinished
- **THEN** the review is blocking, whatever the reviewer said

### Requirement: An agent looks up what the work rests on and follows the source over its memory

The system SHALL tell every agent that may read the web that a fact the work depends on and that lives outside the repository (the format of another tool's configuration, an interface, a flag, a version) is looked up before it is written down, that it never says it cannot check such a fact without having tried to fetch or search it, that when what it reads contradicts what it remembers it follows what it read and says so, and that a fact it still could not confirm is written as an open point for a person and not shipped as if it were known; and SHALL tell the reviewers that a load-bearing fact written from memory is a finding when a page could have confirmed it.

#### Scenario: A configuration format the work ships

- **WHEN** the work adds a configuration file for another tool whose format is documented online
- **THEN** the agent is told to read that documentation first and to follow it over its memory

#### Scenario: A source that cannot be reached

- **WHEN** the agent tried and could not confirm the fact
- **THEN** it is told to write it as an open point for a person, not as something known

### Requirement: Every outside fact in a design carries its source or is marked unverified

The system SHALL tell the architect to end `design.md` with a section `Outside facts` that lists each fact the change depends on that lives outside the repository (a key or shape another tool's configuration expects, an interface, a flag, a version), each with the address of the page it was read on and a short quotation from that page, or marked UNVERIFIED when it could not be read; SHALL tell the design reviewer to ask for changes when such a fact is missing from the section, has no quotation, or is written differently from its quotation; SHALL tell the developer to write into the repository only facts of that section that carry a quotation, never an UNVERIFIED one as if it were known, and to say which file holds an unverified one; and SHALL tell the code reviewer to check the outside facts in the diff against the section, and to ask for changes for one that contradicts its quotation or has none.

#### Scenario: A configuration key the work ships

- **WHEN** the design adds a configuration file for another tool
- **THEN** its Outside facts section gives the page and the quotation for each key, and the design reviewer asks for changes when a key has none

#### Scenario: A fact that could not be read

- **WHEN** the architect could not read the documentation
- **THEN** the fact is marked UNVERIFIED and the developer does not ship it as known

### Requirement: Every agent is told the work's own folder belongs to the system

The system SHALL tell every agent that the work's folder under `.shelf/` (the request, the spec, the design, the plan, the decision log) is part of the pull request on purpose, committed by the system, and that the `.shelf/` line it adds to a repository's `.prettierignore` belongs to the system too, so that no agent asks to remove them, writes that they stay out of the pull request, or judges them as a change of the repository.

#### Scenario: A reviewer sees the folder in the diff

- **WHEN** the code reviewer's diff holds the work's `.shelf/` folder and the `.prettierignore` line
- **THEN** it is told they are the system's, so it does not ask to remove them

#### Scenario: A spec writer decides where its documents go

- **WHEN** the spec writer starts
- **THEN** it is told its documents are committed on the branch and are part of the pull request

### Requirement: A command may reach the sites an administrator added from the page

The system SHALL let the commands an agent runs in its sandbox reach, besides the sites of the built-in list and of `SHELF_ALLOWED_DOMAINS`, the sites an administrator added from the admin page, reading them from the store for every step so that a change applies to the next step without a restart; and SHALL start the step with the built-in and configured sites alone when the store cannot be read.

#### Scenario: A site added from the page

- **WHEN** an administrator added a site and an agent step starts afterwards
- **THEN** the sandbox of that step may reach it

#### Scenario: An unreadable store

- **WHEN** the store of rules cannot be read
- **THEN** the step starts with the built-in and configured sites alone

### Requirement: The agent's sandbox placeholders do not break a repository's Prettier check

The system SHALL, for the developer and the code reviewer on a repository that uses Prettier, add to the clone's `.prettierignore` for the time the agent runs a clearly marked block that ignores the placeholder entries the agent's sandbox shows in the working directory (the shell start-up files, the git configuration files, the editor folders and the `.claude` folder, which it makes unreadable), so that `prettier --check .` and the repository's own scripts do not fail on files that are not part of the repository; SHALL remove that block again before anything is committed, so that it never reaches the pull request and the repository's own ignore file is unchanged by it; SHALL do nothing for a repository that does not use Prettier; and SHALL tell the agent the entries are the sandbox's and not part of the change.

#### Scenario: A repository that uses Prettier

- **WHEN** the developer starts on a repository with a Prettier configuration
- **THEN** the block is in `.prettierignore` while it runs and gone when its work is committed

#### Scenario: A repository that does not use Prettier

- **WHEN** the repository has no Prettier configuration, ignore file or dependency
- **THEN** its files are not touched

#### Scenario: The agent fails

- **WHEN** the agent run raises
- **THEN** the block is removed all the same


### Requirement: Every agent run leaves a record that can be read after the worker is gone

The system SHALL, when a folder for run records is configured, keep for every agent run (finished or failed) a record with: the work, the phase, the round, the role and the model, when it started and ended, how it ended and why it stopped, what it used, whether it continued an earlier session or started again after one could not be continued, what the worker had told it about its tools and about the CI, every tool call it made in order (the tool, what it was about shortened, whether it worked and, for a failure, the start of what the tool said), the calls its permissions refused, the errors the run reported and how long its answer was; SHALL replace anything that looks like a credential in a record by a mark before it is kept; SHALL keep at most a bounded number of calls per run, every failure first; SHALL never stop or fail a step because a record could not be kept; and SHALL keep the records of a work for thirty days after its last run.

#### Scenario: A run that failed

- **WHEN** an agent run raises
- **THEN** a record with outcome failed, the error and the calls made until then is kept, and the step fails as before

#### Scenario: A tool call that did not work

- **WHEN** an agent's command comes back with an error
- **THEN** the record holds that command, shortened, marked as failed, with the start of the error

#### Scenario: A credential in a command

- **WHEN** a command or an error holds a token or a password
- **THEN** the record holds a mark where it was

#### Scenario: A store that cannot be written

- **WHEN** the folder is full or read-only
- **THEN** the step goes on and the failure is logged

### Requirement: A run record names the repository, who asked and how the work began

The system SHALL put in every run record the repository of the work (as `owner/name`), the login of the person who asked for it and how the work began, so that a record alone says which work it belongs to and who may see it after the workflow engine has forgotten the work.

#### Scenario: A run of a work

- **WHEN** an agent run of a work asked for by alice on acme/shop is recorded
- **THEN** the record holds `acme/shop`, `alice` and how the work began

#### Scenario: A record from before

- **WHEN** a record written before these fields existed is read
- **THEN** they are empty and the work cannot be found from it

### Requirement: The worker installs what a repository declares for mise, and writes no lockfile

The system SHALL, for the developer and the code reviewer on a repository that declares its tools for mise (`mise.toml`, `.mise.toml` or `.tool-versions`), run `mise install` itself in the clone, in the worker and outside the agent's sandbox, into the repository's own home, before the agent starts, and tell the agent what was installed or why not, never stopping the step for a failure; SHALL set `MISE_LOCKFILE=false` for the agent and for that installation, so that no `mise.lock` is created or rewritten in a format an older mise on a person's machine cannot read; and SHALL run the repository's own `checks` commands with the same home and tool paths, so that `./mvnw`, `node` or `python` are found.

#### Scenario: A repository with a mise.toml

- **WHEN** the developer starts on a repository whose `mise.toml` names a JDK
- **THEN** the worker has installed it into the repository's home and the agent is told so, and no `mise.lock` is written

#### Scenario: The installation fails

- **WHEN** `mise install` fails in the worker
- **THEN** the agent is told why in one line and the step goes on

#### Scenario: A configured check

- **WHEN** the repository's `checks` hold `./mvnw -B verify`
- **THEN** the command runs with the installed tools on its path

### Requirement: The agent is told that the system runs the checks, with the repository's tools, outside its sandbox

The system SHALL tell the developer and the code reviewer, in the note about tools, that the repository's checks (`checks` in its configuration) are run by the system after the step, outside the agent's sandbox, with the tools that `mise` or the flake declares and with the network, so that the agent does not spend its turns making a build run in its sandbox; that a command in the sandbox may write only the clone and `$TMPDIR`; and, when the step has a private Docker daemon (see the requirement on the step's own Docker daemon), that Docker is available and is the step's own, so that tests and tools may start what they need; and, when it has none, that Docker is not available, so tests have to run without it (an embedded database, or a test that is skipped when the service is missing, and says so).

#### Scenario: A build that needs a database, with no Docker daemon in the step

- **WHEN** the developer is asked for tests against PostgreSQL and the step has no private Docker daemon
- **THEN** it is told that Docker is not available and that the tests must run without it

#### Scenario: A build that needs a database, with a Docker daemon in the step

- **WHEN** the developer is asked for tests against PostgreSQL and the step has a private Docker daemon
- **THEN** it is told that Docker is available in its step, that it is the step's own and goes with it, and that the tests may start the database with `docker compose` or with Testcontainers

### Requirement: A session that is continued is told whether Docker is available now

The system SHALL, when the developer or the code reviewer continues its earlier session, tell it in the continuation whether a Docker daemon is available to it now, with the same text as in a first prompt, because the session keeps the first prompt's note and the environment may have changed since (Docker was off, or not yet built, when the session began). The continuation SHALL say that this note replaces what the agent was told before. A step that is not told about tools SHALL NOT be told about Docker.

#### Scenario: Docker was turned on after the session began

- **WHEN** the developer continues a session that began when Docker was not available, and Docker is on now
- **THEN** the continuation tells it that it has its own Docker daemon and may start what the tests need, and that this replaces the earlier note

#### Scenario: Docker is off

- **WHEN** the developer continues a session and Docker is not on
- **THEN** the continuation tells it that Docker is not available

#### Scenario: A step that is told nothing about tools

- **WHEN** a reviewer of a document continues its session
- **THEN** the continuation says nothing about Docker

### Requirement: A step that runs repository code has its own Docker daemon when the operator enables it

The system SHALL, when the operator has enabled Docker in steps and named the runtime for it, start each step that runs repository code (the developer, the code reviewer, the repository's checks and the tool set-up) with a Docker daemon of its own inside the step container, so that the agent and every tool it runs can use `docker`, `docker compose`, Testcontainers and the Docker API without any filtering. The worker SHALL ask for the daemon with one fixed field of the request, and the runner SHALL decide what that means, from the operator's runtime and one of a fixed set of profiles the operator chose (the standard one, then each adding to the one before: lifting the guest's seccomp and AppArmor, then its read-only and masked system paths, then all capabilities and the guest's cgroup namespace, which is everything privileged mode gives except the host's devices): it starts the step with the operator's runtime, gives the daemon a storage of its own in the step's memory (never a volume of the host, which a virtual machine reaches through a shared file system that is slow and cannot hold the daemon's layers), sized from the step's memory limit, and never mounts the host's engine socket, never starts the step privileged against the host and never falls back to a step without the runtime. What the daemon creates (images, containers, networks, volumes) SHALL live and end with the step container, and a runner that has no runtime for it SHALL refuse a request that asks for it. A container the step starts SHALL reach what the step reaches and nothing more, under the same network rules.

#### Scenario: A repository that starts its own dependencies

- **WHEN** the repository's tests run `docker compose up -d --wait` or start a Testcontainers database, in the developer's step or in the checks
- **THEN** the daemon of that step starts it, the tests reach it, and it is gone when the step ends

#### Scenario: A daemon needs writable system paths

- **WHEN** a step with Docker starts
- **THEN** the step's own start makes the cgroup filesystem and `/proc/sys` writable before it starts the daemon, because a container gets them read-only and the daemon must make cgroups and set `ip_forward`

#### Scenario: The daemon's storage is fast

- **WHEN** a step with Docker starts
- **THEN** the daemon's storage is in the step's own memory, not in a volume, so that pulling an image and starting a database do not go through the shared file system

#### Scenario: The image carries the Docker project's own Docker

- **WHEN** the image of a step with Docker is built
- **THEN** its daemon, runtime and client are the Docker project's own release at a pinned version, the same that the host proof runs, and not an older one from the distribution, whose runtime could not enter a container on a newer guest kernel

#### Scenario: The daemon's container is not marked no-new-privileges

- **WHEN** a step with Docker starts
- **THEN** its container does not carry `no-new-privileges`, which the daemon's own containers would inherit, and the step's own command is run with it by the step's start script, so that the agent keeps the protection

#### Scenario: A container that dropped its privileges can be entered

- **WHEN** a container the step's daemon started runs as a non-root user (the official database images drop to one at start) and a command is executed in it, as a healthcheck does
- **THEN** it runs, because the step has the capability to enter a container whose process changed user; without it the runtime fails with `error executing setns process` and no healthcheck of such a container can ever pass

#### Scenario: A profile the host needs

- **WHEN** the operator chose a more permissive profile because the host needs it
- **THEN** the step's container is the standard one with only that profile's additions, and is still not privileged and still has no device, no host path and no engine socket

#### Scenario: Any container, not only a database

- **WHEN** a step runs `docker run` for an OAuth2 server, a cache, a browser, or builds an image from the repository's Dockerfile
- **THEN** the daemon of that step does it, with no list of allowed images or options

#### Scenario: The host is out of reach

- **WHEN** a step container started under the daemon asks to mount a host path, to run privileged, or to reach the host's engine socket
- **THEN** it can only affect the step's own daemon, and the host's containers, volumes and files are not visible

#### Scenario: A runner without a runtime

- **WHEN** a request asks for a Docker daemon and the runner was started without Docker in steps
- **THEN** the runner refuses it, names the field, and starts no container

#### Scenario: A step that does not run repository code

- **WHEN** the step is the spec, the design, the plan or a review of a document
- **THEN** it has no Docker daemon

#### Scenario: A request asks for more than the one field

- **WHEN** a request to the runner carries a mount, a capability, a device or privileged mode next to the Docker field
- **THEN** the runner refuses it and starts no container

### Requirement: In container mode the repository's checks run in a step of their own

The system SHALL, when agents run in containers, run each command of a repository's `checks` as a `check` step in a container of its own, built by the runner from the same fixed rules as an agent step: the clone mounted at `/work`, the repository's tools and caches, the step's Docker daemon when Docker in steps is on, and the step's limits, but with no model credential and no `GH_TOKEN`, which the runner SHALL refuse in a request for a check. The code in the container SHALL run the command in a shell in `/work` and report one `check` line with its exit code and the end of its output; the worker SHALL turn it into the same result, report and lines as a check run in the worker, and SHALL NOT wrap the command in the worker's own paths, because the step has its own home and tool shims. A check whose step did not end properly (a stream that broke, a step that ran out of time or memory, a runner that could not be reached) SHALL fail the check and say why, and SHALL NOT count as passed. When agents run in the worker's sandbox the commands SHALL run as before.

#### Scenario: A check that passes and one that fails

- **WHEN** the checks are `./mvnw -B verify` and the command exits with 0, or with 1 after a failing test
- **THEN** the worker reports the pass, or the failure with the command, its exit code and the end of its output, as for a check run in the worker

#### Scenario: A check that needs Docker

- **WHEN** Docker in steps is on and the check is `docker compose up -d --wait && ./mvnw -B verify`
- **THEN** the check runs with a Docker daemon of its own, starts the database, and the tests reach it on `localhost`

#### Scenario: No credential in a check

- **WHEN** a request for a `check` step carries a model credential or a `GH_TOKEN`
- **THEN** the runner refuses it, names the variable and starts no container

#### Scenario: The tools of the repository

- **WHEN** the worker installed the repository's tools before the checks
- **THEN** the check finds them on its path in its own container, and what it downloads (a build's cache) stays in the repository's tools folder

#### Scenario: A check that runs out of time

- **WHEN** a check is still running when its time is up
- **THEN** the check fails, saying that it ran out of time, and is not counted as passed

#### Scenario: A check that could not run

- **WHEN** the runner cannot be reached or the step's stream breaks
- **THEN** the check fails with the reason and is not counted as passed

#### Scenario: The worker's sandbox mode

- **WHEN** agents run in the worker's sandbox
- **THEN** the checks run in the worker as before

### Requirement: A step with Docker resolves names through the operator's resolvers, not Docker's embedded one

The system SHALL, for a step that has a Docker daemon of its own, write the operator's resolvers (`SHELF_STEP_DNS`) into the step's `/etc/resolv.conf` before it starts the daemon, because on a user-defined network Docker names its embedded resolver, which lives in the host's network namespace and which a virtual machine cannot reach, so the step could not resolve the model's host, GitHub or a registry. The runner SHALL pass the resolvers to the step itself, from its own settings and never from a request, and SHALL accept only addresses that a virtual machine can reach (no loopback address). The containers the step's daemon starts SHALL inherit them. A step that is given no resolvers SHALL keep the file Docker wrote.

#### Scenario: A step on a user-defined network resolves names

- **WHEN** a step with Docker runs on the step network and the operator's resolvers are set
- **THEN** its `/etc/resolv.conf` names them, the model's host resolves, and the step reaches the model

#### Scenario: A resolv.conf that cannot be written

- **WHEN** the step's `/etc/resolv.conf` is read-only, as the file a guest is given can be
- **THEN** the step mounts a file it wrote in its own temporary folder over it, writes the file directly only if the mount is refused, and starts the step all the same

#### Scenario: The resolvers cannot be set at all

- **WHEN** neither the mount nor a direct write works
- **THEN** the step says so on its standard error and goes on, because setting the resolvers never stops a step

#### Scenario: A step that ends before it says anything

- **WHEN** the container ends before the step wrote its first line
- **THEN** the worker reports that the step ended before it said hello, with its exit code, and not a protocol error about the first line

#### Scenario: A resolver the guest cannot reach is refused

- **WHEN** the operator's resolvers hold a loopback address or something that is not an address
- **THEN** the runner and the worker refuse to start and name the setting

#### Scenario: No resolvers given

- **WHEN** `SHELF_STEP_DNS` is empty
- **THEN** the step keeps the `/etc/resolv.conf` Docker wrote

#### Scenario: A step without Docker

- **WHEN** a step has no Docker daemon of its own
- **THEN** it is built as before, and Docker's own resolver serves it

### Requirement: A check that fails in a step with Docker says what the step's own containers said

The system SHALL, when a check command ends with a failure in a step that has a Docker daemon, add to the end of what it reports a section with the state of the containers the step started and the last lines of the log of each that is not running or is not healthy, so that "unhealthy" comes with the database's own message, and, for a container that has a healthcheck and is not healthy, the result of its last probes (the exit code and what the probe printed), because the log of the container says nothing of why a probe failed. The lines of an image pull that only repeat a layer's progress SHALL be collapsed to the last one of each layer, because they would otherwise fill the end of the output, which is all the report keeps. A step with no daemon, or whose daemon cannot be asked, SHALL report the command's output alone.

#### Scenario: A container that is unhealthy

- **WHEN** `docker compose up -d --wait` fails because a container is unhealthy
- **THEN** the report ends with that container's state and the last lines of its log

#### Scenario: A healthcheck that fails

- **WHEN** a container is `unhealthy` and its healthcheck printed something or exited with a code
- **THEN** the report shows its last probes with their exit code and output, after the container's log

#### Scenario: A container with no healthcheck

- **WHEN** a container that is not running has no healthcheck
- **THEN** no probes are shown for it

#### Scenario: A pull that printed thousands of progress lines

- **WHEN** an image is pulled and each layer printed a line per step
- **THEN** each layer shows once, at its last line, and the lines that matter are in the report

#### Scenario: A check that passes

- **WHEN** the command succeeds
- **THEN** nothing is added

#### Scenario: A step without Docker

- **WHEN** the check fails in a step that has no daemon
- **THEN** the report is the command's output as before

### Requirement: An agent's change to the repository's own configuration is never committed

The system SHALL, before it commits what an agent step changed, put `.shelf/config.toml` back to what the branch held when the step began (or remove it when the branch had none), because the repository's checks and policy are read from its default branch: a change on a work's branch has no effect on the work, and an agent that could change its own checks could make them pass. A change that a person committed to the branch before the step began is part of what the branch held and SHALL be kept. The other files under `.shelf/`, the documents of the work, SHALL NOT be touched. The system SHALL tell the developer and the code reviewer, in the note about tools, that the checks are read from the default branch and that the file is not theirs to edit.

#### Scenario: An agent rewrites the checks

- **WHEN** the developer edits `.shelf/config.toml` and also writes code
- **THEN** the commit holds the code and not the edit, and the branch's configuration is what it was when the step began

#### Scenario: An agent creates the file

- **WHEN** the repository has no `.shelf/config.toml` and an agent writes one
- **THEN** it is not committed

#### Scenario: Only the configuration changed

- **WHEN** the only change of a step is to `.shelf/config.toml`
- **THEN** nothing is committed or pushed

#### Scenario: A person changed it first

- **WHEN** a person committed a change to `.shelf/config.toml` to the branch, and a later step edits it
- **THEN** the person's version is what the branch keeps

#### Scenario: The documents of the work

- **WHEN** an agent writes `.shelf/<work>/spec.md`
- **THEN** it is committed as before

### Requirement: A step that cannot reach the model says so at once and says what to check

The system SHALL, before an agent's step in a container starts the agent, check that the host of the model's API resolves (the one of `ANTHROPIC_BASE_URL`, else `api.anthropic.com`), and when it does not, end the step within seconds with an error that names the host and says that the step's network or its resolvers must be checked (`SHELF_STEP_DNS` for a step with Docker), instead of letting the agent retry for minutes. The check SHALL be skipped when the step reaches the network through a proxy, where the proxy resolves. When an agent's step fails with an error that says the model could not be reached (a name that does not resolve, a refused connection), the system SHALL add to the error what to check, and SHALL keep the original text.

#### Scenario: A name that does not resolve

- **WHEN** the model's host does not resolve from the step
- **THEN** the step ends at once with an error naming the host and what to check, and the agent is not started

#### Scenario: A step that goes through a proxy

- **WHEN** `HTTPS_PROXY` or `ALL_PROXY` is set
- **THEN** the name is not looked up in the step and the agent starts

#### Scenario: The agent could not reach the model anyway

- **WHEN** an agent's step fails with `Can't reach the API server`
- **THEN** the failure reported for the work keeps that text and adds what to check

#### Scenario: Another failure

- **WHEN** a step fails for any other reason
- **THEN** its error is reported as it is

### Requirement: A step finds the JDK the worker installed without being told where it is

The system SHALL, in a step that runs in a container, give the step `JAVA_HOME` and put its `bin` first on the `PATH` when the repository's tools hold exactly one JDK (a folder under `.local/share/mise/installs/java` of the step's home), and `JAVA_HOME` is not set already, so that `./mvnw`, `java` and a build tool find it whether or not the tool shims work. The step SHALL NOT guess when there are several JDKs or none, and SHALL NOT replace a `JAVA_HOME` that is set. This applies to an agent's step and to a repository's check alike.

#### Scenario: One JDK

- **WHEN** the home holds one JDK and `JAVA_HOME` is not set
- **THEN** `JAVA_HOME` names it, and `java -version` and `./mvnw` run in the agent's commands and in a check

#### Scenario: A JAVA_HOME that is set

- **WHEN** the environment already names a `JAVA_HOME`
- **THEN** it is left as it is

#### Scenario: Several JDKs or none

- **WHEN** the home holds several JDKs, or none
- **THEN** nothing is set and the tool shims decide as before

### Requirement: The checks step installs the repository's tools before it runs its checks

The system SHALL, before it runs the repository's `checks`, install in the worker the tools that the clone declares for mise or detects from its CI, as for the developer and the code reviewer, so that a repository whose `mise.toml` an agent has just written is built with the tools that file declares; SHALL tell on the pull request when that installation failed, with its last line; and SHALL, when no check is configured, say on the pull request that nothing was verified here and how to configure one.

#### Scenario: A project started from an empty repository

- **WHEN** the developer wrote a `mise.toml` and the checks are `./mvnw -B verify`
- **THEN** the worker installs the JDK from `mise.toml` and runs the command with it

#### Scenario: The installation fails

- **WHEN** `mise install` fails in the worker before the checks
- **THEN** the pull request says so and the checks still run

#### Scenario: No check configured

- **WHEN** the repository has no `checks`
- **THEN** the comment says nothing was verified here and shows a `checks` example

### Requirement: The sandbox may reach the hosts a JDK and Maven come from

The system SHALL include in its built-in list of sites a sandboxed command may reach the hosts that mise downloads Java and Maven from (`mise-java.jdx.dev`, `api.adoptium.net`, `cdn.azul.com`, `corretto.aws`, `download.java.net`, `download.oracle.com`, `archive.apache.org`, `dlcdn.apache.org`).

#### Scenario: A JDK through mise

- **WHEN** an agent's command runs `mise ls-remote java`
- **THEN** the sandbox does not refuse `mise-java.jdx.dev`

### Requirement: The worker installs only the plain tools a mise declaration names, from backends that run no code

The system SHALL, when the clone declares tools for mise, read that declaration itself and install only the tools it names with a plain name (no backend prefix, no address) and a plain version (a version string, `latest`, or a list or table that holds only versions), with `mise use --global` into the repository's home and with the backends that run code at install time disabled (`asdf`, `vfox`, `npm`, `pipx`, `cargo`, `gem`, `go`, `spm`), so that the hooks, the environment scripts, the plugins and the tool options the declaration may hold never run in the worker; SHALL tell the agent which entries it ignored and why; and SHALL treat an agent's own use of the file inside its sandbox as before.

#### Scenario: A plain declaration

- **WHEN** `mise.toml` declares `java = "temurin-27.0.1+0"` and `maven = "3.9"`
- **THEN** the worker installs those two with `mise use --global` and no other file of the declaration is executed

#### Scenario: A declaration that would run code

- **WHEN** `mise.toml` holds a `[hooks]` section, a `[plugins]` section, a tool named `npm:left-pad` or a tool with a `postinstall` option
- **THEN** none of it is run, the tools that are plain are installed, and the agent is told what was ignored

#### Scenario: Another language

- **WHEN** the declaration names `rust`, `go`, `zig` or `ghc`
- **THEN** it is installed when mise provides it from a backend that runs no code, and ignored with a reason when it needs one that does

### Requirement: The step at the merge only looks at the CI

The system SHALL, for the step that runs once the pull request is ready, open no clone and run no agent: it waits for the repository's CI to settle, reports it on the pull request (staying quiet when it only looks again at a CI already reported as running), and answers passed, failed with the failing runs, or still waiting.

#### Scenario: A red CI at the merge

- **WHEN** the CI is red when the step looks
- **THEN** the step answers failed with the failing runs and comments them on the pull request

### Requirement: The worker gives each container step its clone, its repository's tools and its work's sessions

The system SHALL, for an agent step in container mode, clone into a folder of the shared clones volume and name that folder, the repository, the work and whether the role may change the tools in the request, never a path of the worker's; SHALL create, before asking, the folders of the repository's tools and of the work's sessions in their volumes; SHALL lay the tools out as the worker's own set-up does (the repository's home, with its `mise`, `.m2`, `.npm` and `.cache`), so that what the worker's set-up installs is what the step finds; SHALL give a reviewer those tools read-only and the developer read-write; and SHALL send as the step's environment the model credential the worker was given (`CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL`, whichever is set) together with the step's own variables, only the ones the runner accepts, leaving out the worker's `HOME`, `PATH` and `MISE_*`, which the step's image and the runner set, and SHALL never print that credential in a log, a message or the work's record.

#### Scenario: The clone is named, not its path

- **WHEN** the worker asks the runner for a step whose clone is in the clones volume
- **THEN** the request names the clone as a folder of that volume and holds no path of the worker's

#### Scenario: A reviewer cannot change the tools

- **WHEN** the step is a reviewer's
- **THEN** the tools are mounted read-only in its container

#### Scenario: A later step of the same work continues the session

- **WHEN** a second step of the same work, in another container, asks to continue the first one's session
- **THEN** it mounts the same sessions folder of that work and finds the session

#### Scenario: The worker's variables stay in the worker

- **WHEN** the step's environment holds `HOME`, `PATH` or `MISE_YES`
- **THEN** none of them is sent, and the step's own values apply

#### Scenario: The step has the model credential the worker has

- **WHEN** the worker was given a model credential and asks the runner for a step
- **THEN** the request's environment holds that credential, so that the agent in the container is logged in as it would be in the worker

#### Scenario: No credential was given

- **WHEN** the worker holds no model credential
- **THEN** the request holds none and the step fails as it does in the worker, by saying that no model is set up

#### Scenario: A tool that asks the user database for its home finds the tools

- **WHEN** a tool in the step, such as the JVM, takes its home from the user database and not from `HOME`
- **THEN** it gets the same home the tools were mounted on, so that Maven finds the repository's `.m2` there and does not look for a folder on the read-only root

### Requirement: The step container reads its policy, its catalog and its guard rules and can change none of them

The system SHALL mount into every step container, read-only, the volumes the operator names for the agents' managed policy, the skill catalog and the guard's rules, at their usual paths, and SHALL set the guard's variables from the operator's rules and never from a request, so that the guard's hooks run in the container as they do in the worker and an agent can neither change them nor point them elsewhere.

#### Scenario: The policy is there and read-only

- **WHEN** a step container starts with the policy, catalog and guard volumes named
- **THEN** each is mounted read-only at its path

#### Scenario: A request cannot change the guard

- **WHEN** a request's environment names a variable of the guard
- **THEN** the runner refuses the request, naming the variable
