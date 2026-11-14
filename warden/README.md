# Warden

A policy engine for coding agents, and the guard Shelf puts around every agent it runs. It is wired into the agent's own
lifecycle hooks, so it sees each tool call before it runs. It gates commands, keeps secrets and personal data off the model
and records every decision. Why it exists and how it is shaped: `docs/adr/0014-guard-agents-with-warden-a-policy-engine-in-rust.md`.

Status: it judges shell commands, file reads and writes, fetches and tool calls; redacts secrets and personal data into
reversible tokens; keeps a hash-chained audit log; and guards Claude Code, Codex, Copilot and OpenCode. Only Claude Code has
been checked against the real agent (with a mock model): `docs/LIMITS.md` says what has not been verified.

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

## Commands

| Command | What it does |
|---|---|
| `warden explain '<command>'` | how one command line is judged, and why |
| `warden test <corpus.toml>` | check a policy against a file of expected decisions |
| `warden policy` | the merged policy and the files it came from |
| `warden status` | what the log holds: counts, interventions, redactions (`--all`, `-n`, `--session`) |
| `warden audit verify` | whether any record of the log was changed or removed |
| `warden run -- '<command>'` | run a command and redact what it prints (the agents' hooks call this) |
| `warden init` / `uninstall` | wire it into an agent (`--agent claude\|codex\|copilot\|opencode`, `--global`, `--repo`, `--managed`) |
| `warden doctor` | check the install, the policy and the log |

## What each profile decides

A command is classified into the categories below, and the profile decides what happens for each: `allow`, `ask` (a person is
asked where there is one; with nobody to ask it is a deny) or `deny`. `observe` carries out the `guarded` decisions in audit
mode: nothing is blocked and everything is logged. The operator's file can only tighten a profile.

| Category | What it is | observe | guarded | strict | unattended | shelf |
|---|---|---|---|---|---|---|
| `destructive` | wipes or overwrites data beyond the workspace (`rm -r /`, `dd` to a device, `DROP DATABASE`, `kubectl delete`) | ask | ask | deny | deny | deny |
| `delete` | removes files (`rm -r` inside the workspace, `find -delete`) | allow | allow | ask | allow | allow |
| `vcs_destructive` | erases history or remote branches (`git push --delete`, `filter-branch`, `branch -D`) | ask | ask | deny | allow | allow |
| `vcs_force` | `git push --force` (rewritten to `--force-with-lease`) | ask | ask | deny | allow | allow |
| `bypass_checks` | skips hooks or checks (`--no-verify`, `core.hooksPath`) | ask | ask | deny | deny | deny |
| `exfil` | sends data out (`curl -d @file`, `scp` to a host, `nc`, a reverse shell) | deny | deny | deny | deny | deny |
| `network` | any network access, so it can be allowed or asked about | allow | allow | ask | allow | allow |
| `blocked_domain` | a request to a denied domain (always denied) | deny | deny | deny | deny | deny |
| `privilege` | `sudo`, `chmod 777`, system services | ask | ask | deny | deny | deny |
| `remote_exec` | downloaded or decoded text piped into a shell | deny | deny | deny | deny | deny |
| `package_install` | adds a dependency | allow | allow | ask | allow | allow |
| `publish` | releases something (`npm publish`, `docker push`, `terraform apply`, `gh release create`) | ask | ask | deny | deny | deny |
| `secret_access` | prints or reads a secret (credential files, `gh auth token`) | ask | ask | deny | deny | deny |
| `env_dump` | prints the environment | ask | ask | deny | deny | deny |
| `obfuscation` | a command line that cannot be read, or hides what it runs | deny | deny | deny | deny | deny |
| `eval` | `eval` of text only known when it runs | ask | ask | deny | deny | deny |
| `dynamic_exec` | a command whose name comes from an expansion | allow | allow | ask | allow | allow |
| `interpreter_exec` | `python -c`, `node -e` and similar | allow | allow | ask | allow | allow |
| `interpreter_shell` | an inline interpreter script that starts a shell command | ask | ask | deny | allow | allow |
| `out_of_scope` | writes outside the working directory and `/tmp` | ask | ask | deny | deny | deny |
| `tamper` | writes to the agent's own settings, Warden's policy, shell startup files or git hooks (always denied) | deny | deny | deny | deny | deny |
| `secret_write` | a credential in a file, an edit or a tool argument | ask | ask | deny | deny | deny |
| `supply_chain` | a registry other than the default | allow | allow | allow | allow | allow |
| `secret_prompt` |  | deny | deny | deny | deny | deny |
| `pii_read` | reads a file of personal data | deny | deny | deny | deny | deny |

A policy file (`~/.config/warden/policy.toml` or a repository's `.warden/policy.toml`) can change a category, add rules and path
globs, list denied or allowed domains and tune redaction; see `warden policy` for what is in force.
