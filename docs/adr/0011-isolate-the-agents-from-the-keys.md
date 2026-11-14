# 0011. Isolate the agents from the keys

- Status: proposed
- Date: 2026-11-08

## Context

Agents run shell commands, and what they read (a repository, an issue, a pull request from someone else) can contain instructions
meant for them. We must assume a hostile repository can make an agent run commands of its choosing. Today every agent step runs
in the worker, next to everything the worker needs:

| Asset                                   | Where it lives                      | Reachable by a hostile agent?                         |
| --------------------------------------- | ----------------------------------- | ----------------------------------------------------- |
| GitHub App private key                  | mounted file in the worker          | yes, if it can read the file                          |
| Model credential                        | worker environment                  | partly: the agent process needs it                    |
| Installation token (one hour)           | given to the developer step         | yes, by design, for the repositories of that work     |
| Temporal, the web service, other work   | the container network               | yes, the network is shared                            |
| Other works' clones                     | the worker's workspace              | yes, unless each step gets its own directory          |
| The host                                | kernel, other containers            | only through a kernel or container escape             |

The sandbox inside Claude Code (filesystem writes and network allow-list) is the first line and works when the host lets it start
(the host fix is `deploy/fix-ubuntu.sh`). It is one layer, and it is not enough alone: it protects what the agent runs, not what the
worker holds. A dedicated worker for agents does not help by itself: if it holds the same key and the same network, it is the same
target with a different name. What matters is what the agent's process can reach, not how many workers there are.

## Decision (proposed, in stages, each shippable on its own)

1. **Split the worker by what it holds.** Two task queues, two services.
   - `control` worker: runs the activities that talk to GitHub as the App (publish, announce, poll, labels, draft state). It alone
     mounts the private key. It never runs an agent.
   - `agents` worker: runs `shelf_run_step` only. It has no private key, no `shelf.toml`, no route to the web service, and its network
     reaches only Temporal and the model API. It receives the installation token for the step in the activity input (minted by the
     control side, scoped to the one repository, one hour), never the means to mint more.
   Result: a hijacked agent can no longer sign as the App or reach every repository, only the repository of its own work for an hour.
   Needs: the workflow routes activities by `task_queue`, a workflow patch so running work replays, compose changes.
2. **A restricted network for the agents' service.** An egress allow-list (GitHub, the model API, package registries the operator
   names) through a forward proxy, and no access to the other compose services. This is the main defence against exfiltration, and it
   also covers the model credential: it can still be used from inside, but not sent elsewhere.
3. **One throwaway environment per step.** Each step runs in a fresh container or microVM (clone mounted, no host mounts, resource
   limits, destroyed afterwards), started through a runner that does not hand over the host: rootless Podman or Docker, Sysbox, or
   gVisor; a Firecracker microVM for operators who need a hard boundary. Behind the existing `AgentBackend` port, so the domain and the
   workflow do not change. This also removes the need to relax the host for the sandbox (`seccomp=unconfined`, the AppArmor profile).
4. **Limit the model credential.** Prefer a key with a spend cap and no other use; optionally a small credential proxy that holds the
   real key and gives each step a short-lived token. Without it the credential is the one asset a hostile agent can still burn.

Stage 1 and 2 close most of the exposure for little work and fit a single VPS. Stage 3 is the real isolation and is larger. Stage 4
is operational advice until a proxy exists.

## Consequences

- A hostile repository costs, at worst, one repository's token for one hour and some model spend, not the App or the host.
- More moving parts: two worker services, a proxy, and for stage 3 a container runtime to install and keep patched.
- Latency grows with stage 3 (a container start per step), which long agent steps absorb.
- Until stage 1 ships, the guidance stays: a dedicated VPS, the App installed only on repositories you trust, a capped model key,
  and no review of pull requests from unknown people.

## Alternatives considered

- **One dedicated "agent" worker, nothing else changed:** same key, same network, same target. Rejected as the answer; kept as the
  shape of stage 1 only together with removing the key and restricting the network.
- **Mount the Docker socket to start a container per step:** hands the worker root on the host. Rejected; needs a rootless runtime or a
  socket proxy that allows only create and remove.
- **Run agents directly on the host as another user:** loses the container and still needs the same host relaxations. Rejected.
- **Disable the sandbox and rely on the container:** the container is relaxed for the sandbox and shares the worker's secrets and
  network. Rejected except as a last resort on repositories you fully trust.
