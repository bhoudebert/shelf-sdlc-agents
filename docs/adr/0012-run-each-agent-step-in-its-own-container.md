# 0012. Run each agent step in its own container

- Status: proposed
- Date: 2026-11-13

## Context

Today every agent runs as a Claude Code process inside the `worker` container, under Claude's own sandbox (bubblewrap). Inside
Docker that sandbox runs in its weaker nested mode, which is why the worker needs `seccomp=unconfined`. All agents of all works
and all repositories therefore share one filesystem, one environment and the worker's mounts, which include the GitHub App's
private key and the `.env` credentials. The repository's `checks` run through `workspace.run` (`shell=True`) with the worker's
full environment, outside any sandbox. The installation token an agent receives (`GH_TOKEN`) covers every repository the App is
installed on.

What agents really need, from `application/steps.py` and `domain/roles.py`: the clone of one repository with its history, the
repository's own agent files, a shell for the coding roles (`git log`, `git diff`, tests, `gh`), and network access to GitHub, the
Claude API and the package registries of the repository. The worker already does the commit, the push, the pull request comments
and the `checks`. Nothing needs the App key, the other clones, or other repositories.

The goal is a closed perimeter: an agent cannot reach the host, the operator's secrets, or another repository. This record
refines the stages proposed in 0011.

## Decision

The worker stays the orchestrator and never runs untrusted code. Each agent step, and the `checks` of a repository, runs in its
own short-lived container started by the worker through a new `AgentBackend` adapter (`ContainerBackend`). The domain and the
workflow are untouched.

A step container has:

- **Mounts:** the step's own clone only (with `.git`), plus an optional per-repository dependency cache volume. Never the App
  key, `.env`, other clones, or the Docker socket.
- **Environment:** the Claude credential, and an installation token narrowed to the work's repository
  (`repositories: [name]`) with the permissions the step needs, valid for one hour.
- **Limits:** CPU, memory, process count and wall time per step; removed when it ends.
- **Network:** an `internal` Docker network whose only exit is an egress proxy.

The container runs the same Claude Agent SDK call as today, through a small entrypoint that reads the `AgentTask` on standard
input and prints the answer. Prompts, roles, tools and turn limits do not change. The unit is the step: it matches the fresh
clone per step that exists today, and nothing survives from one step to the next except the repository's dependency cache.

### Starting containers

Mounting the Docker socket in the worker is root on the host, so it is a first stage, not the destination. A **runner service**
that alone holds the socket and accepts one narrow request (run the fixed image on workspace X with limits Y; no flags, mounts or
privileged mode chosen by the caller) comes next. Rootless Podman or sysbox stay options for hosts that can run them.

### The egress proxy and the admin pane

The proxy identifies each step by a random credential in the proxy URL, registered by the runner for the step's lifetime
(`HTTPS_PROXY=http://<step>:<secret>@proxy`), so it knows the work, the repository and the requester without the Docker API. The
`internal` network leaves no other route: a tool that ignores the proxy simply has no connection.

Domains are decided in an admin pane:

- a built-in baseline of ecosystem presets (npm, PyPI, Maven Central, GitHub release hosts, the Claude API) the operator may switch
  off;
- allowlists per repository and global, where the operator's list caps what a repository may ask for in `.shelf/config.toml`;
- a mode per repository: **open and log** (learn), **ask**, or **strict**.

In **ask** mode the proxy refuses an unknown host with a clear 403, records every refused host of the step, and the step ends as
"blocked: needs these hosts". The workflow enters a waiting state, like the approval gates, and an administrator sees the request
(hosts, repository, requester) and allows it for this repository, for everyone, or denies it. Allowing re-runs the step. This
needs a new decider state and event, a protocol bump and `workflow.patched`, with the golden histories kept green.

The proxy also feeds a dashboard of outbound requests (host, bytes, work, time). The web service logs its own inbound traffic
(webhook deliveries, sign-ins, refusals) to the same dashboard.

### Stages

Each stage is its own pull request with spec, tests and a status update here.

1. Run the repository's `checks` with a scrubbed environment.
2. Narrow the installation token to the work's repository.
3. `ContainerBackend`, opt-in with `SHELF_ISOLATION=container` (the current mode stays the default), Docker socket mounted in the
   worker, open egress. The worker then drops `seccomp=unconfined` and the nested sandbox when the mode is on.
4. The runner service; the worker loses the socket.
5. Network: (a) proxy with logging and the outbound dashboard, (b) allowlists, admin pane and the per-repository mode, (c) the
   blocking workflow state.

## Consequences

- A leaked step container exposes one repository and one Claude credential for an hour, not the host, the App key or the other
  works. The sandbox no longer depends on user namespaces inside the worker, so the Ubuntu AppArmor workaround stops mattering
  for agents.
- Every step pays a container start (about a second or two, an estimate to measure in stage 3), a cold dependency cache on the
  first step of a repository, and a first image pull per host. An agent step takes minutes, so the start is small; the cache
  volume handles the rest.
- The image must carry the toolchain a repository needs. A shared image is simple and never fully right; a repository naming its
  own image in `.shelf/config.toml` is the way out, and that image is untrusted but boxed.
- The Claude credential and the narrowed token are inside the container. An egress allowlist reduces the ways to send them out
  but cannot close it: an allowed host (a gist, a package registry) can still receive data. The remaining protection is how
  little the container holds.
- The proxy sees host names, not paths, because it does not decrypt TLS.
- Stage 3 alone leaves the worker holding the socket: a bug in the worker is then host root. Stage 4 removes that.
- A shared per-repository dependency cache lets one work poison the cache of another work on the same repository. Accepted for a
  single team; read-only roles mount it read-only.
- Administrators get one more thing to answer. The baseline presets and the learn mode keep the number of requests low.

## Alternatives considered

- **Narrow the token only (0011 stage A).** Limits what GitHub accepts but not what the agent reaches on the machine. Kept as a
  stage here, not as the answer.
- **Scrub the environment and keep the in-worker sandbox.** Cheap and a good first stage, but the agents still share a
  filesystem and the App key stays readable. Kept as stage 1.
- **One long-lived container per worker, per work item, or per repository.** Faster, but steps of different works or repositories
  share a filesystem again, or a container lives for days waiting on approvals with a live token. Rejected for the step as the
  unit.
- **Docker socket behind a filtering proxy.** Filters endpoints, not request bodies, so a caller can still ask for a privileged
  container with the host mounted. Rejected in favour of the runner service.
- **A static list of allowed domains.** Every repository needs different hosts, so a global list is either too tight or
  meaningless. Replaced by presets, per-repository lists and the ask flow.
- **A pre-scan phase that guesses the hosts from `package.json` or `pom.xml`.** Misses transitive dependencies and install
  scripts. Learning from the actual refusal is accurate.
- **A package mirror as the only exit.** The cleanest answer where one exists, but a service to run. Left as an option behind the
  same proxy.
- **gVisor, Firecracker or one virtual machine per step.** Stronger, but they depend on host setup the compose file cannot
  promise. Left open for later.
