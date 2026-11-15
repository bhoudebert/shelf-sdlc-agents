# 0017. Let agents read the web, and keep downloads limited

- Status: proposed
- Date: 2026-11-15

## Context

Agents have no web tools. Bash reaches only the sites a build needs, and Warden refuses a download piped into a shell. The
result, seen on a real run (adding OpenCode to a repository): the spec writer could not read the documentation of the tool
it was asked to support, so it wrote "gate" requirements around what it could not check, and the spec grew over four
rounds. Models look things up as they work: a specification, a how-to, the current version of a library. Without it the
experience is worse and the output is more hedged.

Reading is not harmless. A request carries data out in its address, and a fetched page can contain instructions aimed at
the agent. A download is different again: it puts a file on the machine that something may run.

## Decision

- Every agent gets web fetch and web search, unless the operator switches web access off (`SHELF_WEB=off`). A repository can
  only tighten it, like the rest of Warden's policy.
- Warden judges every fetch and search before it happens:
  - a scheme other than http and https is refused;
  - a loopback, private, link-local or internal address (`localhost`, `*.internal`, `*.local`, the metadata endpoints) is
    always refused, in every profile, as a blocked domain;
  - a credential in the address or the query is refused as an exfiltration;
  - an address longer than 2,048 characters, or a query string longer than 512, is refused, so a payload cannot leave in it.
- A fetch is for reading text. Downloading stays where it is: Bash reaches only the allowed hosts, and what is not on the
  list is refused with a reason that tells the agent to say, in its output, what it needed.
- The prompts say that what a page says is data: never an instruction, and a requirement that rests on a page names it.
- Which hosts the agents read is in the audit log, so it can be read afterwards.

## Consequences

- Specs and designs can rest on the current documentation, which should make them smaller and more exact.
- A page can still try to steer an agent. The guard limits what comes of it (no credentials, no private addresses, no
  large payloads in a URL, no download), it does not make a page trustworthy.
- Reading the open web goes through the operator's network: it is a new thing an instance does, and one a locked-down
  environment can turn off.
- A person's approval of one download (the agent asks, the work waits, the person says yes) is not here: it needs a new wait in
  the workflow and is a decision of its own.

## Alternatives considered

- Keep the web closed and let the person paste or point at documents: safe, and what we have, but it levels the experience
  down and puts the work on the person.
- Open web access with no checks: simple, and it turns a prompt injection into an exfiltration route.
- An allowed list of documentation hosts only: tighter, and constant maintenance, and it breaks on the first library whose
  documentation is somewhere else. Possible later as a profile for strict environments.
