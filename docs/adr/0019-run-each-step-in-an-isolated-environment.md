# 0019. Run each step in an isolated environment, with nothing less than today

- Status: proposed
- Date: 2026-11-18

## Context

Every agent runs as a Claude Code process inside the `worker` container, under Claude's own sandbox (bubblewrap) in its weaker
nested mode. That is why the worker runs with `seccomp=unconfined` and `apparmor=unconfined`. All agents of all works share the
worker's filesystem and its mounts, which hold the GitHub App's private key, and the model credential is in their environment.
The repository's `checks` run in the worker itself, outside any sandbox. Tools are installed by the worker, outside the sandbox,
from a declaration that had to be sanitised because installing it would run repository code next to the worker's secrets.

Over the last weeks the same boundary cost real work: a JVM that ignores `HTTPS_PROXY`, twenty-two unreadable placeholder files
that broke a formatter, a home directory that cannot be written, no way to run what a repository's tests need (a Docker
daemon, a browser), and a trust argument ("we only install plain tool names") that exists only because the worker cannot be
trusted with the declaration. The proposal of decision 0012 (still open as a pull request) named the right direction in
November, before Warden, mise, run records and the admin guard existed. This record replaces it with a design that starts from
what exists today and keeps all of it.

## Decision

Each agent step, each run of a repository's `checks` and each tool installation runs in **its own short-lived container**, created
by a small **runner service** that alone holds access to the container engine. The worker stays the orchestrator: it clones,
commits, pushes, comments and records, and never executes anything a repository or an agent controls. The domain, the workflow
and the prompts do not change; a new `ContainerBackend` sits behind the existing `AgentBackend` port.

The container is the boundary, so it can hold more than the sandbox allowed: a writable home, real package managers, tools
installed on demand, local services (a database, a browser, a front end) as plain processes, and, where the operator provides a
safe runtime, a private Docker daemon for tests that need one. It holds less of what matters: no App key, no other clone, no
other repository, no long-lived credential beyond the model's, a network that has a single exit with a log, and limits on CPU,
memory, processes, disk and time.

The mode is chosen by the operator (`SHELF_ISOLATION=sandbox|container`). `sandbox`, today's behaviour, stays the default until a
parity run on real repositories shows nothing is lost, and stays available for one release after the default changes.

The technical design (components, schemas, the parity matrix, stages and open questions) is in
[`docs/design/isolated-step-environments.md`](../design/isolated-step-environments.md).

## Consequences

- A compromised step exposes one repository's clone and one hour of credentials, not the host, the App key or other works.
- `seccomp=unconfined`, `apparmor=unconfined`, the nested sandbox, the placeholder-hiding hack and the JVM proxy special cases
  disappear in container mode.
- Repository tools can be installed in full (including plugin-based backends) because they run boxed, which lifts the limits of
  the sanitising that protects the worker today. The sanitiser stays for `sandbox` mode.
- The runner holds the engine socket, which is host root. It is the one component whose code must stay small and whose API is a
  fixed shape, not a way to pass container options.
- A step pays a container start and, the first time on a host, an image pull. Measured, not assumed, in the first stage.
- Operators need a container engine whose version supports volume sub-paths. Rootless Podman works behind the same API.
- One more service, one more image target and a network to operate; `install.sh` and the doctor must check them.

## Alternatives considered

- **Keep the sandbox and add checks to it.** Cheapest, and what exists. It cannot give a writable home, a clean network model, a
  Docker daemon or a browser, and it keeps every agent on the worker's filesystem.
- **Mount the engine socket in the worker.** Simple, and root on the host for any bug in the worker. Allowed only as a temporary
  first stage in decision 0012; rejected here as the destination.
- **A filtering proxy in front of the socket.** Filters endpoints, not bodies: a caller can still ask for a privileged container.
- **One container per work item or per repository.** Faster, but steps of different works share a filesystem again, or a container
  lives for days holding a live token while a person decides.
- **A virtual machine per step** (Firecracker, gVisor). Stronger; depends on host support a compose file cannot promise. Left as
  a runtime the runner can be told to use.
