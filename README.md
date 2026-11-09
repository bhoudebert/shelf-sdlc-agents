# shelf-sdlc

<!-- badges:start -->
[![CI](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/ci.yml) [![CodeQL](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/codeql.yml) [![Specs](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/specs.yml/badge.svg?branch=main)](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/specs.yml) [![Pages](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/bhoudebert/shelf-sdlc-agents/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/release/bhoudebert/shelf-sdlc-agents?include_prereleases)](https://github.com/bhoudebert/shelf-sdlc-agents/releases) [![License](https://img.shields.io/github/license/bhoudebert/shelf-sdlc-agents)](https://github.com/bhoudebert/shelf-sdlc-agents/blob/main/LICENSE) [![Last commit](https://img.shields.io/github/last-commit/bhoudebert/shelf-sdlc-agents)](https://github.com/bhoudebert/shelf-sdlc-agents/commits/main) [![Stars](https://img.shields.io/github/stars/bhoudebert/shelf-sdlc-agents?style=flat)](https://github.com/bhoudebert/shelf-sdlc-agents) [![Open issues](https://img.shields.io/github/issues/bhoudebert/shelf-sdlc-agents)](https://github.com/bhoudebert/shelf-sdlc-agents/issues) [![Open pull requests](https://img.shields.io/github/issues-pr/bhoudebert/shelf-sdlc-agents)](https://github.com/bhoudebert/shelf-sdlc-agents/pulls)
[![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Temporal](https://img.shields.io/badge/workflows-Temporal-000000?logo=temporal&logoColor=white)](https://temporal.io/) [![FastAPI](https://img.shields.io/badge/web-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Docker Compose](https://img.shields.io/badge/deploy-docker%20compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Ruff](https://img.shields.io/badge/lint-ruff%20(all%20rules)-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/) [![Pyright strict](https://img.shields.io/badge/types-pyright%20strict-2b7489)](https://github.com/microsoft/pyright) [![Import Linter](https://img.shields.io/badge/architecture-import--linter-6f42c1)](https://import-linter.readthedocs.io/) [![Spec driven](https://img.shields.io/badge/specs-OpenSpec-0a7ea4)](https://github.com/bhoudebert/shelf-sdlc-agents/tree/main/openspec) [![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-FE5196?logo=conventionalcommits&logoColor=white)](https://conventionalcommits.org) [![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/bhoudebert/shelf-sdlc-agents/blob/main/CONTRIBUTING.md)
<!-- badges:end -->

A self-hosted software factory. Sign in with GitHub, pick a repository, and start agent work from the web UI at any step
of the lifecycle: a need, a spec, a design, a plan, code to write, or "review my pull request". Every step is a durable
Temporal workflow, every loop is bounded, and a person decides at the gates, from the UI or on the pull request.

```mermaid
flowchart LR
  need["Need"] --> spec["Spec"] --> sr{"Spec review"}
  sr -- changes --> spec
  sr -- approve --> gate(["You approve"])
  gate --> design["Design"] --> dr{"Design review"} --> plan["Plan"] --> impl["Implement"] --> chk{"Checks"}
  chk -- red --> impl
  chk -- green --> cr{"Code review"}
  cr -- changes --> impl
  cr -- approve --> pr(["Pull request: you merge"])
```

One GitHub App does sign-in, repository access and the agents' identity. Agents run on the Claude Agent SDK, in a fresh
clone per step, with the tools of their role and a one-hour token. Reviewers are a different model from producers.

## Status

**Early development, not yet verified end to end on real agents.** Built and tested: the pure pipeline core, access rules and
roles, the Temporal workflow (on a real server, with history replay), the GitHub App adapter (sign-in, repositories,
installation tokens, pull requests, one-click registration), the step runner (fresh clone, role prompts, verdicts, checks),
the web interface and the Docker Compose deployment (booted on real Docker). Not yet done: a full run with a real model on a
real repository, per-repository settings edited in the UI, continuing a workflow past very long waits, other agent backends.
See the [roadmap](ROADMAP.md).

## Getting started

### Run it

You need Docker, a public HTTPS address (any reverse proxy or tunnel in front of port 8080; none is bundled), and a model
credential (an Anthropic API key or a Claude subscription token).

```bash
git clone https://github.com/bhoudebert/shelf-sdlc-agents && cd shelf-sdlc-agents
sh deploy/install.sh https://shelf.example.org
```

Open that address. The first visit registers the GitHub App in one click and shows what to paste into `deploy/.env`; run
the script again, install the App on your repositories, and sign in. [The full guide](https://bhoudebert.github.io/shelf-sdlc-agents/docs/getting-started.html)
covers every setting. Kubernetes is up to you: `deploy/compose.yml` lists every service, variable and volume it takes.

### Develop

```bash
nix develop                      # or: install uv and Python 3.13
uv sync --frozen
uv run pytest                    # unit, property and Temporal tests
```

## Documentation

- [Contributing](CONTRIBUTING.md): the workflow from idea to release, commits, checks.
- [Engineering](docs/ENGINEERING.md): how it is built.
- [How it evolves](docs/EVOLVING.md): the path every change follows.
- [Decision records](docs/adr/README.md): why it is shaped this way.
- [Roadmap](ROADMAP.md)
- [Security](SECURITY.md) · [Support](SUPPORT.md) · [Code of conduct](CODE_OF_CONDUCT.md)

## Working with coding agents

`AGENTS.md` is the single source of the rules for Claude Code, Codex, Gemini CLI, GitHub Copilot and other agents;
`CLAUDE.md`, `GEMINI.md` and `.github/copilot-instructions.md` point to it.

## Licence

Apache-2.0, see [LICENSE](LICENSE).
