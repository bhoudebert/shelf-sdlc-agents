---
name: warden
description: How to work when Warden guards this session: what its tokens mean, how to read a refusal, and which warden commands you may run.
---

# Working under Warden

Warden checks every command, file access and fetch before it runs. It is on for a reason: do not look for ways around it.

## Tokens

Output you see may hold tokens such as `<EMAIL_1>`, `<PHONE_2>` or `<SECRET_3>`. Each stands for a real value that you are not shown.

- Use a token exactly as it is. Do not guess the value behind it and do not try to decode it.
- When you write a token into a file, Warden puts the real value there. The file is correct; you never saw the value.
- The same value always has the same token in a session, so you can compare and group by token.
- Never write a token into your reasoning as if it were a real value (for example, do not say an address "looks like" something).

## When something is refused

A refusal comes with a reason. Read it, then:

1. Choose a safer way to reach the same goal (read the file through `cat` or `head` instead of the Read tool for personal data, use a tool that does not send data away, work inside the repository).
2. If the goal itself needs what was refused, stop and say exactly what you need and why. A person decides.
3. Do not try again with a variant: `bash -c`, `sh -c`, `eval`, base64, hex escapes, an inline `python -c` or `node -e`, a script that does the same thing. Warden reads those too, and each attempt is recorded.

Never edit what protects you: the agent settings (`.claude`, `.codex`, `.opencode`), `.warden/`, git hooks, shell startup files. Writing to them is always refused.

## Commands you may run

- `warden explain '<command>'` shows how a command line would be judged, before you run it.
- `warden status` shows what Warden recorded in this session: what it refused and what it redacted.
- `warden doctor` checks that Warden is wired correctly.

You may not change a policy file to make a command pass.

## Secrets in your own work

Do not type a credential into a command, a file, a prompt or a tool argument. If a task seems to need one, ask for it to be provided through the environment of the command that needs it, never through your output.
