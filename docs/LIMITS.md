# Limits

What shelf-sdlc does not do yet, what we know is weak, and what we plan to do about it. Read this before you point it at a
repository you care about.

The project is in early development and has had no external audit. Statements about the code come from reading it, not from
attacking it. Last reviewed 2026-11-13.

## 1. Agents are not isolated from each other or from the worker

How it works today:

- Every agent runs as a Claude Code process **inside the `worker` container**. There is no container per agent or per work item.
- The only barrier is Claude Code's own sandbox (bubblewrap). Inside Docker it runs in its weaker nested mode, which is why the
  `worker` service needs `seccomp=unconfined`.
- All agents of all works and all repositories share that container's filesystem and environment. The container also mounts the
  GitHub App's private key and receives the credentials from `.env`.
- The installation token an agent receives (`GH_TOKEN`) is valid for one hour but covers **every repository the App is installed
  on**, not only the work's repository.
- Each step works in a fresh clone, and the worker does the commit and the push. That keeps a step's files apart, but it is a
  convention, not a wall.

What this means for you:

- Treat agents as able to read what the worker can read, including the App key and the other works' clones, until the isolation
  below ships. We have not demonstrated that attack; the sandbox may stop part of it, and we cannot promise it does.
- Install the App only on repositories, and let in only people and organisations, you would trust with the whole factory. Access
  is closed by default (`shelf.toml`), and the sign-in list is the first line of defence.
- A repository's `checks` (the commands in `.shelf/config.toml`) run **outside any sandbox**, in the worker, with the worker's
  full environment. Only configure repositories whose `checks` you trust.

### The plan

Decided in [ADR 0012](adr/) (proposed), refining [ADR 0011](adr/):

1. Run the repository `checks` with a scrubbed environment.
2. Narrow the installation token to the work's repository.
3. Run each agent step, and the `checks`, in its own short-lived container that mounts only its own clone. The worker stays the
   orchestrator and does the commit, the push and the pull request comments. Opt-in at first.
4. Move container start-up to a small runner service, so the worker no longer holds the Docker socket (which is root on the host).
5. Control the network: an egress proxy that logs every outbound request per work and repository, an admin pane of allowed
   domains, and a waiting state in the workflow when an agent needs a domain nobody has allowed yet.

What will stay true even then:

- The Claude credential and a repository-scoped token are inside the step container. A network allowlist reduces ways to send
  them out but cannot close all of them: an allowed host such as a code host or a package registry can still receive data.
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
