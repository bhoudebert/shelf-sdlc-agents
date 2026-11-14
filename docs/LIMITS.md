# Limits

What shelf-sdlc does not do yet, what we know is weak, and what we plan to do about it. Read this before you point it at a
repository you care about.

The project is in early development and has had no external audit. Statements about the code come from reading it, not from
attacking it. Last reviewed 2026-11-13.

## 1. Agents are not isolated from each other or from the worker

How it works today (read from `main` on 2026-11-13):

- Every agent runs as a Claude Code process **inside the `worker` container**. There is no container per agent or per work item.
- The only barrier is Claude Code's own sandbox (bubblewrap). Inside Docker it runs in its weaker nested mode, which is why the
  `worker` service needs `seccomp=unconfined` and, on Ubuntu hosts, `apparmor=unconfined`.
- All agents of all works and all repositories share that container's filesystem. The container mounts the GitHub App's private
  key (`deploy/secrets`).
- An agent starts with the worker's environment, minus what shelf blanks for it: the session and webhook secrets and every
  `GITHUB_APP_*` setting. The model credential stays, because the agent needs it. Blanking hides the key's path from the agent; it
  does not stop an agent that finds the file.
- Every role has the full toolset, including `Bash`. A reviewer's changes are discarded because only producers' work is
  committed, but a reviewer runs commands like anyone.
- Only the implementer gets a GitHub token (`GH_TOKEN`). It is valid for one hour but covers **every repository the App is
  installed on**, with the App's permissions, not only the work's repository.
- Commands run by the agent in the sandbox may reach only an allowlist of sites: GitHub, the common package registries and the
  tool downloads, plus whatever the operator adds in `SHELF_ALLOWED_DOMAINS`. There is no log of what was reached, no admin
  page, and no way to ask for a site. `SHELF_SANDBOX_DISABLED` turns the sandbox, and so the allowlist, off.
- Each step works in a fresh clone, and the worker does the commit and the push. That keeps a step's files apart, but it is a
  convention, not a wall.

What this means for you:

- Treat agents as able to read what the worker can read, including the App key file and the other works' clones, until the
  isolation below ships. We have not demonstrated that attack; the sandbox may stop part of it, and we cannot promise it does.
- Install the App only on repositories, and let in only people and organisations, you would trust with the whole factory. Access
  is closed by default (`shelf.toml`), and the sign-in list is the first line of defence.
- A repository's `checks` (the commands in `.shelf/config.toml`) run **outside any sandbox**, in the worker, through a shell.
  They no longer see the worker's secrets or the model credential in their environment, but they still run on the worker's
  filesystem, where the App key file is mounted. Only configure repositories whose `checks` you trust.

### Warden checks every call, and is not a wall

Every agent now runs under Warden, a guard that is called before each command, file access and fetch (through Claude Code's
managed hooks, which a repository cannot override). It refuses what the active profile refuses (`shelf` by default: running
downloaded or decoded text, sending data away, reading credentials, tampering with the agents' own configuration, `sudo`,
destructive commands outside the clone, a credential on a command line), runs allowed commands so that secrets and personal data
in their output become tokens, and logs every decision in a hash chain you can verify (`warden audit verify`). The operator's
`config/warden.toml` is a locked layer: a repository can tighten it with its own `.warden/policy.toml` and never loosen it.

What it does not do, and you should not assume:

- It reads text. A program an agent writes and then runs can open any socket or read any file the worker can; Warden does not see
  inside it. The container, the sandbox and the allowlist above stay the perimeter, and the isolation plan below stays needed.
- A repository's `checks` run through the worker, outside any agent hook.
- Redaction is pattern-based. A short password, a key in a format nobody has seen and a name nobody listed go through; the
  operator's names and patterns in `config/warden.toml` are how you cover your own data.
- Warden has been run inside Shelf's image through the Agent SDK against a mock of the model API (not a real model): the managed
  hook refused a dangerous command and the model was told why, and an allowed command's output reached the model redacted. The
  sandbox lets a command write only in `$TMPDIR` and its working directory, so the token files and the pending audit records live
  in `/tmp/claude-1000/warden` and the next hook moves the records into the log. The first real task is the real test: set
  `SHELF_WARDEN_PROFILE=observe` for a first week to see what it would refuse without refusing anything.
- Warden's Codex hook was checked against the real Codex CLI 0.167 with a mock of the model API (`warden/live/check_codex.py`),
  not against a real model or a person at the keyboard. Codex runs a hook only once it trusts it (`/hooks`, or
  `--dangerously-bypass-hook-trust` in automation): until then every command runs unguarded and nothing says so. A hook cannot
  ask in Codex (an `ask` is ignored and the command runs), so what a profile would ask about is refused there. Shell commands and
  `apply_patch` reach the hook, and a rewritten command is honoured; hosted tools such as web search never reach it. The
  OpenCode and Copilot adapters have not been run against the real agents.

### The plan

Proposed in a [decision record](adr/) on running each agent step in its own container (not yet accepted). In order:

1. Run the repository `checks` with a scrubbed environment. Done: the environment is scrubbed, the filesystem is not.
2. Narrow the installation token to the work's repository.
3. Run each agent step, and the `checks`, in its own short-lived container that mounts only its own clone. The worker stays the
   orchestrator and does the commit, the push and the pull request comments. Opt-in at first.
4. Move container start-up to a small runner service, so the worker no longer holds the Docker socket (which is root on the host).
5. Build on today's site allowlist: log every outbound request per work and repository, add an admin pane of allowed sites, and
   a waiting state in the workflow when an agent needs a site nobody has allowed yet.

What will stay true even then:

- The Claude credential and a repository-scoped token are inside the step container. A site allowlist reduces ways to send them
  out but cannot close all of them: an allowed host such as a code host or a package registry can still receive data.
- The network layer sees host names, not URLs, because it does not decrypt traffic.
- A step container costs about a second or two to start, and a first step on a repository starts with a cold dependency cache.
  These are estimates until stage 3 is measured.

## 2. The review loop is long

A spec writer writes, a critic reviews, the writer fixes, and so on until the critic is satisfied or the round limit is reached.
Compared with asking Claude Code directly on your machine, which usually carries on alone and asks one question, this takes more
rounds and more tokens. It also finds holes a single agent would not.

Why it is hard to shorten:

- The critic starts cold every round, and the writer restarts without its own reasoning, so both re-read.
- A fix to one point can contradict an older spec. A critic that does not re-read the whole set will miss it.
- Whether an issue is a blocker or a nit is a judgement. We have no reliable way to label it automatically, and a model's own
  label would be confident noise.
- Where the human is needed is therefore often exactly where the agents disagree.

What we plan, in this order, each as its own small change:

1. **Measure** how many rounds each phase takes and which kinds of issue come back, on real works, before changing anything.
2. **Resume the writer, keep the critic fresh.** The writer keeps its own history on a revision. The critic re-reads the whole
   spec set every round, so contradictions are still caught.
3. **Hand over to a person when the same issue comes back** after the writer's fix. This is a plain rule, not a score. A blocker
   must also quote the sentence it contradicts or name the missing behaviour from the request; an issue without that is a note.
4. **A decisions file.** When a person settles a question at a gate, the answer can be recorded in a plain, versioned file in the
   repository (for example `.shelf/decisions.md`), which agents read like `AGENTS.md`, so settled questions are not asked again.

How the decisions file is meant to work, so that it cannot silently harden:

- Recording is a choice made in the interface for each decision (a "remember this for the repository" option, off by default),
  never automatic.
- A recorded decision carries who decided, when and why, and can be edited or revoked. It lives in the repository, so changes go
  through a pull request and are reviewed.
- Agents treat it as a team decision, not an unbreakable rule: a request that goes against one is flagged to a person instead of
  being followed or ignored silently.
- It informs; it does not approve. The approval screen can show "last time you decided X", but a person still clicks.

What we do not plan: approving automatically from a similarity score on past decisions. It fails quietly in the cases where the
context differs a little, and a wrong approval costs more than one more click.

## 3. Not verified against real services

The tests run against fakes, local git repositories and recorded shapes. They never call GitHub, Temporal Cloud or Claude for
real. These parts are therefore specified and tested, but not proven against the real services:

- Organisation sign-in. Private membership needs the App allowed to read members (the optional "Members: read" permission, accepted
  on the organisation's installation), or the membership must be public, or the person is listed under `users`.
- Creating the first commit of an empty repository, and refusing a missing base branch.
- The one-approval flow end to end on a live repository.

## 4. Smaller known limits

- Work started before a protocol change keeps its old behaviour. Restart the work to get the new flow.
- Two steps started at the very same moment on a brand-new empty repository could collide on the first push.
- The request shown above the conversation appears only once the pull request exists.
- `shelf.toml` reloads without a restart, but the `mode` is read at start only.
- Updating from an older install needs `sh deploy/install.sh <url>` once, which moves `shelf.toml` into `deploy/config/`.

## Reporting a problem

A gap that is not listed here, or a way around a guarantee we describe, is worth a report. See `SECURITY.md` for vulnerabilities and
the issue tracker for the rest.
