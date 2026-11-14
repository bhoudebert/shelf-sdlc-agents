# Roadmap

Ideas, not promises. When an idea is done, remove it and record what was learnt; when one is added, say who it is for and
when it would be used. An idea that cannot be described in those terms is not ready to build.

## Next

- **A first full run on a real repository with a real model**, and what it teaches. For the first operators; every step so
  far is tested with scripted agents, and the Claude backend only through its options.
- **Per-repository settings editable in the UI** (kept next to the repository's file), for administrators who cannot edit
  `.shelf/config.toml`.
- **`continue_as_new` after very long waits**, so a work item can live for months.
- **A guard summary on each pull request**: how many calls the agents made for this work, what the guard refused and
  redacted. For whoever reviews the pull request. It needs the step's working directory in the audit record (it has the
  directory already) and a replay-safe new activity in the workflow, so it is not a small change.
- **A spend total per work item and a view of it.** The worker now logs the cost of each step; a total needs the cost kept
  in the workflow's state (a patched, replay-safe change) and a place to show it. For operators who share one model account.
- **The board says which runs proceed without you.** The start form records the autonomy of a run, the board does not show
  it. For the person who started several runs before going to bed.

## Later
- **Warden checked against the real Copilot CLI and OpenCode.** Claude Code is checked against a mock model, and Codex is
  being checked the same way; Copilot and OpenCode adapters were written from their documentation only. For anyone who
  runs those agents under Warden.
- **Warden audit log retention.** The log grows by a day file per day and is never pruned; pruning must keep the chain
  verifiable (an anchor record). For operators with long-lived instances.

- **An isolated environment created for each step.** Each step runs in its own short-lived container (an image with the toolchains,
  the clone mounted, no host mounts, no credentials, a restricted network, resource limits), thrown away afterwards, so an agent
  cannot harm anything outside the repository. It needs a way to start containers that does not hand the worker the host: a
  rootless Docker or Podman, or a socket proxy that only allows creating and removing containers. Behind the `AgentBackend` port.
  For operators who let agents work on repositories they do not fully trust.
- **Another agent backend** (OpenCode, or a harness made for local models) behind the `AgentBackend` port, for teams that
  must stay on local models.
- **Budget per work item** and a spend view, for operators who share one model account.
- **GitHub OIDC for CI**, so a repository's CI can ask for a review without a shared secret.
- **Bring-your-own model key per repository**, stored encrypted, for public instances.

## Not now

- **Agents that merge.** Accountability for the default branch stays with a person.
- **A user database.** Access is the operator's file plus GitHub; roles are a per-repository setting.
- **Free-form conversations between agents.** The pipeline is a deterministic state machine; agents are stateless steps.
- **Kubernetes manifests or a Helm chart.** `deploy/compose.yml` documents every service, variable and volume; translating it
  is left to people who run Kubernetes.
