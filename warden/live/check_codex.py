"""A live check of Warden against the real Codex CLI, with a mock in place of the model.

It needs the `codex` binary (CODEX_BIN, or on the PATH) and a built `warden` (WARDEN_BIN, or target/debug/warden). It starts a local
mock of the OpenAI Responses API (`mock_openai.py`), so there is no model, no credential and no cost, and it gives Codex a throwaway
CODEX_HOME and HOME, so your own ~/.codex is never read. The hooks come from `warden init --agent codex` itself. Codex does not run
a hook it has not been told to trust (see check 0), so the runs pass `--dangerously-bypass-hook-trust`, which exists for automation.

  0. a hook that is not trusted is not run at all (what a person who skips /hooks gets);
  1. the PreToolUse and PostToolUse payloads carry the fields the adapter reads;
  2. a dangerous command is refused and the model is told why;
  3. an ordinary command runs;
  4. an `ask` is not honoured by Codex (the tool goes ahead), so Warden answers a question with a refusal that carries it;
  5. a rewrite of the command (`updatedInput`) is honoured, so a wrapped command runs and its output reaches the model redacted;
  6. PostToolUse is called with the result; `decision: block` replaces what the model sees, `updatedMCPToolOutput` does not for a shell;
  7. an `apply_patch` that names a protected file is refused.

Run it after upgrading Codex or Warden:  python3 warden/live/check_codex.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = "gpt-5.5"  # any slug Codex has bundled metadata for; it is what makes Codex offer its `apply_patch` tool
RESULTS = ("function_call_output", "custom_tool_call_output")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def snippet(warden: str, tee: Path | None) -> str:
    """The hooks Warden prints for Codex, as they would be pasted into config.toml (comments dropped)."""
    out = subprocess.run([warden, "init", "--global", "--agent", "codex"], capture_output=True, text=True, check=True,
                         env={**os.environ, "HOME": tempfile.mkdtemp(prefix="warden-live-home-")}).stdout
    text = "".join(line + "\n" for line in out.splitlines() if not line.startswith("#"))
    return text.replace(f'"{warden} hook', f'"{tee} {warden} hook') if tee else text


def stub_hooks(root: Path, answers: dict[str, dict]) -> str:
    """Hooks that record their input and answer with a fixed JSON, to see what Codex does with an answer Warden would not send."""
    script = root / "stub.sh"
    script.write_text(f'#!/bin/sh\ncat >> "{root}/stub-$1.in"; echo >> "{root}/stub-$1.in"\n[ -f "{root}/stub-$1.out" ] && cat "{root}/stub-$1.out"\nexit 0\n')
    script.chmod(0o755)
    text = ""
    for event, answer in answers.items():
        (root / f"stub-{event}.out").write_text(json.dumps(answer))
        text += f'\n[[hooks.{event}]]\nmatcher = ".*"\n\n[[hooks.{event}.hooks]]\ntype = "command"\ncommand = "{script} {event}"\ntimeout = 20\n'
    return text


def outputs(log: Path) -> list[str]:
    found = []
    for line in log.read_text().splitlines() if log.exists() else []:
        for item in json.loads(line)["req"].get("input", []):
            if isinstance(item, dict) and item.get("type") in RESULTS:
                found.append(str(item.get("output")))
    return found


def developer_texts(log: Path) -> str:
    text = ""
    for line in log.read_text().splitlines() if log.exists() else []:
        for item in json.loads(line)["req"].get("input", []):
            if isinstance(item, dict) and item.get("role") == "developer":
                text += json.dumps(item.get("content"))
    return text


class Run:
    def __init__(self, codex: str, warden: str, command: str, hooks: str, profile: str = "guarded", trust: bool = True) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="warden-live-codex-"))
        self.log = self.root / "mock.log"
        self.payloads = self.root / "payloads.log"
        port = free_port()
        mock = subprocess.Popen([sys.executable, str(HERE / "mock_openai.py"), str(port), command, str(self.log)])
        try:
            time.sleep(0.7)
            home, work, codex_home = self.root / "home", self.root / "work", self.root / "codex"
            for directory in (home, work, codex_home):
                directory.mkdir()
            (codex_home / "config.toml").write_text(
                f'model_provider = "mock"\nmodel = "{MODEL}"\n\n[model_providers.mock]\nname = "mock"\n'
                f'base_url = "http://127.0.0.1:{port}/v1"\nwire_api = "responses"\nenv_key = "MOCK_KEY"\n'
                f"request_max_retries = 0\nstream_max_retries = 0\n" + hooks)
            env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(codex_home), "MOCK_KEY": "dummy-key-for-the-local-mock",
                   "WARDEN_PROFILE": profile, "WARDEN_LIVE_PAYLOADS": str(self.payloads), "WARDEN_STATE_DIR": str(self.root / "state")}
            args = [codex, "exec", "--skip-git-repo-check", "-s", "workspace-write"] + (["--dangerously-bypass-hook-trust"] if trust else [])
            result = subprocess.run(args + ["run it"], cwd=work, env=env, capture_output=True, text=True, timeout=120, check=False,
                                    stdin=subprocess.DEVNULL)
            self.stdout, self.stderr, self.code = result.stdout, result.stderr, result.returncode
        finally:
            mock.terminate()
        self.state = self.root / "state" / "audit"
        self.warden = warden

    def decisions(self) -> str:
        out = subprocess.run([self.warden, "status", "--all", "--dir", str(self.state)], capture_output=True, text=True, check=False)
        return out.stdout

    def payload(self, event: str) -> dict:
        """The first payload Codex sent for this event (the tee writes them one after the other, with no newline between)."""
        text, decoder, at = (self.payloads.read_text() if self.payloads.exists() else ""), json.JSONDecoder(), 0
        while at < len(text):
            try:
                data, at = decoder.raw_decode(text, at)
            except ValueError:
                at += 1
                continue
            if isinstance(data, dict) and data.get("hook_event_name") == event:
                return data
        return {}


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    return ok


def main() -> int:
    codex = os.environ.get("CODEX_BIN") or shutil.which("codex")
    warden = os.environ.get("WARDEN_BIN") or str(HERE.parent / "target" / "debug" / "warden")
    if not codex or not Path(warden).is_file():
        print("needs the codex binary (CODEX_BIN) and a built warden (WARDEN_BIN); build with `cargo build` in warden/", file=sys.stderr)
        return 2
    results = []
    root = Path(tempfile.mkdtemp(prefix="warden-live-tee-"))
    tee = root / "tee.sh"
    tee.write_text('#!/bin/sh\ntee -a "$WARDEN_LIVE_PAYLOADS" | exec "$@"\n')
    tee.chmod(0o755)
    hooks = snippet(warden, tee)

    untrusted = Run(codex, warden, "echo untrusted-ran", snippet(warden, None), trust=False)
    results.append(check("0. a hook that is not trusted is not run, and the command runs unguarded",
                         bool(outputs(untrusted.log)) and "untrusted-ran" in outputs(untrusted.log)[0] and "codex" not in untrusted.decisions(),
                         untrusted.decisions()))

    refused = Run(codex, warden, "kubectl delete ns prod", hooks, profile="unattended")
    pre, post = refused.payload("PreToolUse"), refused.payload("PostToolUse")
    seen = outputs(refused.log)
    fields = ("session_id", "cwd", "hook_event_name", "tool_name", "tool_input")
    results.append(check("1. the PreToolUse payload has the fields the adapter reads (and the tool is called Bash)",
                         all(f in pre for f in fields) and pre.get("tool_name") == "Bash" and pre["tool_input"].get("command") == "kubectl delete ns prod",
                         json.dumps(pre)[:300]))
    results.append(check("2. a dangerous command is refused and the model is told why",
                         bool(seen) and "blocked by PreToolUse hook" in seen[0] and "kubectl" in seen[0] and "Chunk ID" not in seen[0], str(seen)))
    results.append(check("2. the refusal is in the audit log as a codex call", "deny" in refused.decisions() and "codex" in refused.decisions(), refused.decisions()))

    ordinary = Run(codex, warden, "echo ordinary", hooks)
    seen = outputs(ordinary.log)
    results.append(check("3. an ordinary command runs", bool(seen) and "ordinary" in seen[0] and "Chunk ID" in seen[0], str(seen)))

    ask = Run(codex, warden, "echo went-ahead", stub_hooks(Path(tempfile.mkdtemp(prefix="warden-live-stub-")), {
        "PreToolUse": {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "ASK-REASON"}}}))
    seen = outputs(ask.log)
    results.append(check("4. a raw `ask` is not honoured: Codex marks the hook failed and the command still runs",
                         bool(seen) and "went-ahead" in seen[0] and "PreToolUse Failed" in ask.stdout + ask.stderr, str(seen) + ask.stderr[-300:]))
    question = Run(codex, warden, "kubectl delete ns prod", hooks, profile="guarded")
    seen = outputs(question.log)
    results.append(check("4. a question Codex cannot ask is a refusal that carries it: the model sees why and the command does not run",
                         bool(seen) and "Warden would ask" in seen[0] and "Chunk ID" not in seen[0], str(seen)))

    wrapped = Run(codex, warden, "echo owner=marie.curie@client.fr", hooks)
    seen = outputs(wrapped.log)
    results.append(check("5. a rewrite is honoured: the wrapped command ran and the model sees a token, not the address",
                         bool(seen) and "<EMAIL_1>" in seen[0] and "marie.curie" not in seen[0], str(seen)))
    status = wrapped.decisions()
    results.append(check("5. the redaction is in the audit log without the address", "redacted" in status and "marie.curie" not in status, status))

    post = wrapped.payload("PostToolUse")
    results.append(check("6. PostToolUse is called with the tool's result", "tool_response" in post and "tool_use_id" in post, json.dumps(post)[:300]))
    replaced = Run(codex, warden, "echo the-real-output", stub_hooks(Path(tempfile.mkdtemp(prefix="warden-live-stub-")), {
        "PostToolUse": {"decision": "block", "reason": "REPLACED-BY-HOOK"}}))
    seen = outputs(replaced.log)
    results.append(check("6. a PostToolUse `decision: block` replaces what the model sees with the reason",
                         seen == ["REPLACED-BY-HOOK"], str(seen)))
    mcp = Run(codex, warden, "echo the-real-output", stub_hooks(Path(tempfile.mkdtemp(prefix="warden-live-stub-")), {
        "PostToolUse": {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedMCPToolOutput": "REPLACED"}}}))
    seen = outputs(mcp.log)
    results.append(check("6. `updatedMCPToolOutput` does not replace a shell result (it is for MCP tools)",
                         bool(seen) and "the-real-output" in seen[0] and "REPLACED" not in seen[0], str(seen)))

    patch = "*** Begin Patch\n*** Add File: .claude/settings.json\n+{}\n*** End Patch"
    patched = Run(codex, warden, patch, hooks, profile="unattended")
    pre = patched.payload("PreToolUse")
    seen = outputs(patched.log)
    results.append(check("7. an apply_patch that names a protected file is refused, and the payload names the tool apply_patch",
                         pre.get("tool_name") == "apply_patch" and bool(seen) and "blocked by PreToolUse" in seen[0], f"{pre.get('tool_name')} {seen}"))

    print(f"{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
