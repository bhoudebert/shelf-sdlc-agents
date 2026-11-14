# 0014. Guard agents with Warden, a policy engine in Rust

- Status: accepted
- Date: 2026-11-14

## Context

Shelf runs coding agents on its own, with nobody watching. Each is a Claude Code process with the full toolset, `Bash`
included. What stands between an agent and a dangerous action today is the model's judgement, the sandbox's network
allowlist, and the environment shelf blanks for it. Nothing reads what the agent is about to do, and nothing stops a
secret in a command's output from reaching the model. A person at a keyboard has the same gap with Claude Code, Codex,
Copilot or OpenCode.

Every one of these agents offers lifecycle hooks: a program called before each tool call, which sees the call as text and
can allow it, refuse it with a reason, or change it. Hooks are not a sandbox: they judge text, and a program the agent
writes and runs can open any socket. They are still the only layer that can explain a refusal to the model, rewrite a
command into a safer one, redact what comes back and leave a record of intent.

A first version of this idea was tried on a developer machine, in Go. It showed what is worth keeping (one policy for every
agent, a real bash parser, reversible tokens for secrets, a verifiable log) and what a run without a person needs that a
desktop tool does not.

## Decision

Warden is a policy engine written in Rust, a component of this repository with its own binary, its own releases and a
standalone install, and the guard Shelf puts around every agent it runs. It is not a separate product: the profile Shelf
uses is defined by the operator's deploy configuration, and the same policy will later drive the egress proxy of
decision 0012.

**It does four things.** It gates every command: parsed as bash (pipes, lists, subshells, substitutions, nested shells,
wrappers such as `sudo` and `xargs`), classified into risk categories, then allowed, asked, denied or rewritten (`git push
--force` becomes `--force-with-lease`). It keeps secrets and personal data off the model: an allowed command runs through a
redactor, values become stable tokens such as `<EMAIL_1>`, and the real value is restored when the agent writes a file. It
protects itself: agent settings, its own policy, shell startup files and git hooks cannot be written by the agent. It
records every decision in a hash-chained log that can be verified.

**Profiles**, each a preset the policy extends:

- `observe`: everything is classified and logged, nothing is blocked. For trying it on a repository.
- `guarded`: dangerous actions ask, exfiltration and obfuscation are denied, routine work flows. For a person at a keyboard.
- `strict`: everything risky asks or is denied. For repositories that hold production credentials or customer data.
- `unattended`: nobody answers, so nothing asks. Catastrophic actions and leaks are denied, routine work is allowed and
  logged. For agents that run alone.
- `shelf`: `unattended`, plus the operator's own locked file. What Shelf runs.

**An ask is only possible with a person to answer it.** Where the agent has no way to ask (Codex), or the profile says
nobody is there, an ask is resolved by the profile: denied with its reason, so the agent sees why and tries another way.
A later stage may send it to an administrator's queue (decision 0012), but a silent profile never blocks on a prompt nobody
reads.

**Layers.** A preset, then a global file (or the operator's), then the repository's `.warden/policy.toml`. Lists add up and
nothing can be removed, per-key decisions override, and a layer marked `locked` cannot be loosened by the layers below it.
Exceptions are rules, not removals. Writing agent or Warden configuration, and reaching a denied domain, are always denied
whatever a rule says. The format is TOML, like the rest of Shelf's configuration, and a `warden test` corpus pins the
behaviour of a policy.

**Failing safe.** A policy that cannot be loaded denies. Unreadable hook input is let through with a message in `guarded`
and denied in `unattended` and `shelf`.

**Agents.** One engine, one adapter per agent: Claude Code, Codex CLI, OpenCode and GitHub Copilot. Each adapter turns the
agent's hook payload into one internal call and the verdict into what that agent expects. What each agent can intercept,
rewrite or answer differs, and the adapter's documentation says so instead of pretending.

**In Shelf.** The worker image carries a pinned, checksum-verified `warden`. The operator's `[warden]` section chooses the
profile and may name a policy file that is mounted read-only and locked. `shelf-catalog sync` writes the hook into the
managed policy, which agents cannot override, so every step runs under it. A repository's own `.warden/policy.toml` may
only tighten what the operator set.

**Stages.** Each is its own pull request with its spec and tests.

1. This record and the scaffolding: a Cargo workspace in `warden/`, a CI job, the release configuration.
2. The engine: policy model and layers, the bash parser and classifier, decisions, rewrites, the presets, `explain`, `test`
   and `policy`.
3. Redaction: detectors, session tokens, `warden run`.
4. The audit log and `status`, `audit verify`.
5. The Claude Code adapter, `hook`, `init`, `uninstall`, `doctor`, the companion skill and the installer.
6. The Shelf integration: the image, the `[warden]` configuration, the managed-policy hook, the `shelf` profile.
7. The Codex, OpenCode and Copilot adapters.

## Consequences

- Shelf's agents get a command gate and a redactor that do not depend on the model behaving. A refused command comes back
  with a reason the agent can act on.
- The repository becomes two components: Python and Rust. CI gains a Rust job, releases gain a second package, and the
  quality gate before a push grows by `cargo fmt`, `clippy` and `test`.
- A hook is not a sandbox. A script an agent writes and runs is not seen, and the repository's `checks` run outside any
  agent hook. The container and egress plan of decision 0012 stays the perimeter; Warden is the layer inside it.
- Redaction is pattern-based. It misses a short password, a key in an unknown format and a name nobody listed. The policy's
  names and custom patterns are how a repository makes it good for its own data.
- A binary starts for every tool call. In Rust that costs a few milliseconds, which keeps the guard usable.

## Alternatives considered

- **A separate repository.** Cleaner release, but the guard's value in Shelf is that its profile comes from the deploy
  configuration and its audit log will reach the same administrator pane. A second repository would pin Shelf to a version
  it does not control. A standalone install of this component gives the same freedom.
- **Keep it in Go, or write it in Python inside the worker.** A hook runs once per tool call: a Python start is tens of
  milliseconds a call, and a static Rust binary installs anywhere with no runtime.
- **tree-sitter for parsing.** Error-tolerant and widely used, but it builds C code, which makes a static binary on every
  target harder. A pure Rust bash parser is enough, and a command it cannot parse is itself a finding.
- **A policy language such as Rego.** Powerful, and one more language to learn for a problem the size of a TOML file.
- **A mandatory sandbox instead.** It cannot explain a refusal to the model, rewrite a command or redact output, and it is
  different on every platform. It stays the layer underneath, owned by decision 0012.
- **Hashing or blanking secrets instead of tokens.** Blanking breaks the agent's work and hashing is not reversible, so a
  file the agent writes would hold the hash. Tokens keep both the structure and the file correct.
