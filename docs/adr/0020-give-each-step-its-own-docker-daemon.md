# 0020. Give each step its own Docker daemon, so that any agent can start any container

- Status: proposed
- Date: 2026-11-21

## Context

Decision 0019 puts every step in a short-lived container and says a private Docker daemon is a later, opt-in stage. The first real
run in container mode showed that this was the wrong order. The developer was told "Docker is not available, so tests have to run
without it". The target repository's tests need a PostgreSQL on `localhost:5432` and say so in their own specification (the
repository's compose file starts it). The developer could not start it, the checks could not start it, and the work went round
the developer and checks steps until the round limit asked for a person, having changed nothing in the last rounds.

A database is the example, not the case. Repositories need an OAuth2 server for a smoke test, a Redis or a broker, a browser, a
mock of a third-party API, a service built from their own Dockerfile. They need it while developing and again in integration tests,
whether the repository starts it with `docker compose`, with Testcontainers, or with `docker run`. An agent that cannot start a
container cannot finish such work, and a rule that lists the containers it may start will always be one short.

## Decision

When the operator enables it, each step that runs repository code (the developer, the code reviewer, the repository's checks and
the tool set-up) gets **its own private Docker daemon inside its step container**. The agent, the checks and any tool they run can
use `docker`, `docker compose`, Testcontainers and the Docker API with nothing filtered: the daemon is the step's own. The images,
containers, networks and volumes it creates live in the step container and go with it. The host's daemon is never reachable, and
no step holds the runner's socket.

- **The boundary is a runtime, not a filter.** A daemon inside a container needs a runtime built for it (sysbox, or any runtime that
  gives the container its own kernel view, such as Kata or a microVM). The operator names it (`SHELF_STEP_RUNTIME`), the runner
  passes it to the engine for these steps, and the runner **refuses to start with the daemon enabled and no runtime**. It never
  falls back to privileged mode or to the host's socket.
- **One fixed flag, not an engine option.** A request to the runner gains the single field `docker`, set by the worker from the
  operator's setting and the kind of step. The runner decides what it means. A request still has no field for mounts, capabilities,
  devices, privileged mode or any other engine option.
- **How permissive the step is depends on the host, so the host says.** A daemon needs a writable cgroup filesystem, and what a host's
  guest kernel and filters allow differs. The runner takes one of a fixed set of profiles (`standard`, `unconfined`, `cgroupns`),
  none of them privileged mode, which under Kata hands the host's devices to the virtual machine (it failed on the first real
  host). `host-runtime.sh --probe` finds the first that works on a host and `install.sh` writes it down, so no host is tuned by hand.
- **The network is the step's.** What a nested container reaches is what the step container reaches, so the step's network rules
  and the egress decisions of 0019 apply to it unchanged. Registries the daemon pulls from are hosts like any other.
- **Images are not cached between steps yet.** The daemon's storage is a volume of the step that goes with it, so each step pulls
  what it starts. A cache per repository needs one holder at a time (two daemons must never share a storage) and is a change
  of its own.
- **The host is prepared by a script, not by hand.** A separate, rerunnable script installs and checks the runtime (Ubuntu and
  Debian), and `install.sh` offers to run it, so no operator has to follow a list of commands.
- **The agents are told the truth.** The note about tools says that a private Docker is available, that it is the step's own and
  disappears with it, and that tests may start what they need. When the daemon is off, the note says Docker is not available, as
  today.
- **Off until it is verified.** The setting defaults to off. Spike S7 of the design (a daemon under the chosen runtime on the Ubuntu
  hosts in use: start time, image cache, a Testcontainers run, a `docker compose up --wait`) decides the runtime the install
  script documents.

## Consequences

- A repository's own way of running its dependencies works unchanged, for the developer and for the checks, and a failing build
  means the code, not a missing service.
- The operator must install a runtime for nested containers. Without it the mode cannot be enabled, and the refusal says why.
- A step costs the start of a daemon (seconds) when it asks for one, and memory for what it runs: the step's limits cover the nested
  containers too.
- A compromised step can run any container it likes, inside its own boundary: the egress rules still decide what it reaches, and
  the runtime decides what it cannot escape. The strength of the isolation is the runtime's strength.
- The checks must run in the same kind of container (stage 3b of 0019), since the worker has no daemon and must not get one.

## Alternatives considered

- **The host's Docker socket in the step.** It is host root: a container may mount `/` or run privileged. Rejected.
- **A proxy that filters the socket.** Compose and Testcontainers use volumes, networks, labels, privileged-looking options and
  host paths, and a bind mount names a path on the host, not in the step. A filter that lets them work lets too much, and one that
  does not breaks them.
- **The runner starts the services a repository's compose file lists.** It covers a database and nothing else: not Testcontainers,
  not a service built from a Dockerfile, not `docker run` in a script. Rejected as a design, though it could sit on top.
- **Tests that use an embedded or mocked database.** It changes the repository's tests, and differs from the real database where
  it matters. The target repository forbids it in its own specification.
- **A virtual machine per step.** The strongest boundary and one possible runtime for this decision, but it depends on host
  support that a compose file cannot promise.
