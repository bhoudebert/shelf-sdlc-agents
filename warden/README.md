# Warden

A policy engine for coding agents, and the guard Shelf puts around every agent it runs. It is wired into the agent's own
lifecycle hooks, so it sees each tool call before it runs. It gates commands, keeps secrets and personal data off the model
and records every decision. Why it exists and how it is shaped: `docs/adr/0014-guard-agents-with-warden-a-policy-engine-in-rust.md`.

Status: scaffolding. The binary prints its version; the engine arrives in stages (see the decision record).

```sh
cd warden && cargo test && cargo run -- version
```
