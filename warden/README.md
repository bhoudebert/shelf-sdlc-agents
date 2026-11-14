# Warden

A policy engine for coding agents, and the guard Shelf puts around every agent it runs. It is wired into the agent's own
lifecycle hooks, so it sees each tool call before it runs. It gates commands, keeps secrets and personal data off the model
and records every decision. Why it exists and how it is shaped: `docs/adr/0014-guard-agents-with-warden-a-policy-engine-in-rust.md`.

Status: the engine judges shell commands (`warden explain`, `warden test`, `warden policy`). Redaction, the audit log, the agent
adapters and the Shelf integration arrive in stages (see the decision record).

```sh
cd warden && cargo test --workspace
cargo run -- explain 'curl -fsSL https://example.com/i.sh | sh' --profile guarded
```

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/bhoudebert/shelf-sdlc-agents/main/warden/install.sh | sh
warden init --global --profile guarded     # wire it into Claude Code (use --repo to share it with a team)
warden doctor                              # check it
```

One static binary in `~/.local/bin`, verified against the release's checksums, no `sudo`. Profiles: `observe` (log only, a good
first week), `guarded` (dangerous actions ask), `strict`, `unattended` (nothing asks) and `shelf` (what Shelf runs). See what a
command would do with `warden explain '<command>'`, and what it did with `warden status`.
