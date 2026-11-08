# Security

## Secrets

Keys and tokens live in environment variables or an untracked `.env`, never in the repository. `.env` is git-ignored;
commit an `.env.example` with the names and no values. If a secret is ever committed, treat it as leaked: revoke it, then
remove it from the history.

## What this project reaches

- **Network:** the web service listens on one port (8080) and expects your TLS proxy in front. It calls GitHub (REST and OAuth)
  and Temporal; the worker calls GitHub, the model provider and Temporal, and clones over HTTPS. Temporal's port is not published.
- **Credentials:** the GitHub App's private key and client secret, the webhook secret, the session secret and the model
  credential are read from the environment; installation tokens are minted per use (valid one hour) and never stored. A
  signed-in person's GitHub token stays in the web service's memory and is lost on restart.
- **Who may act:** the operator's access list decides who signs in (leave it empty and anyone with a GitHub account can spend
  your model quota); per-repository roles limit who may decide; webhooks require a valid HMAC signature; `/shelf` commands
  count only from people with write access and are matched against a fixed list.
- **Agents:** each step runs in a fresh clone with the tools of its role, inside Claude Code's sandbox. In a container the
  worker runs with `seccomp=unconfined` and the sandbox's weaker nested mode, which is a weaker boundary than a VM: run the
  worker on a host you are willing to expose to the repositories you let people use.
- **Repository content is untrusted.** It is read by agents (prompt injection is possible) and the project's checks run
  commands from `.shelf/config.toml`. Only enable the App on repositories whose contributors you trust.

## Reporting a vulnerability

Open a private security advisory on the repository (Security tab, "Report a vulnerability"), or contact the maintainer
directly. Please do not open a public issue for a vulnerability. Expect an answer within a few days.

## Supported versions

The latest release receives fixes.
