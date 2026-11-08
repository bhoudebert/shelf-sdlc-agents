# Roadmap

Ideas, not promises. When an idea is done, remove it and record what was learnt; when one is added, say who it is for and
when it would be used. An idea that cannot be described in those terms is not ready to build.

## Next

- **A first full run on a real repository with a real model**, and what it teaches. For the first operators; every step so
  far is tested with scripted agents, and the Claude backend only through its options.
- **Per-repository settings editable in the UI** (kept next to the repository's file), for administrators who cannot edit
  `.shelf/config.toml`.
- **`continue_as_new` after very long waits**, so a work item can live for months.

## Later

- **Isolate the agents from the keys, in stages** ([ADR 0011](docs/adr/0011-isolate-the-agents-from-the-keys.md)): split the
  worker so the one that runs agents holds no App key and reaches only the model and GitHub, then an egress allow-list, then one
  throwaway container or microVM per step behind the `AgentBackend` port (rootless runtime, no host mounts, resource limits), then a
  capped or proxied model credential. For operators who let agents work on repositories they do not fully trust.
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
