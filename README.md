# Shelf SDLC Agents

A self-hosted software factory: drive agent work on your GitHub repositories from a web UI, from a need to a pull request.

## Status

<!-- Experimental, beta, stable? What works, what does not yet. -->

## Getting started

```bash
python -m pip install uv && uv sync --frozen
uv run pytest
```
<!-- A minimal example of use, with its real output. -->

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
