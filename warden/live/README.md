# Live check against the real Claude Code

`check.py` runs the real `claude` binary with Warden's hooks, with a local mock of the Anthropic API in place of the model
(`mock_anthropic.py`): no credential, no cost. It confirms that Claude Code really calls the hooks, honours their answers
(`deny`, `updatedInput`, `additionalContext`, a blocked prompt) and passes the model what Warden says.

```sh
cd warden && cargo build
CLAUDE_BIN=/path/to/claude python3 live/check.py
```

Run it after upgrading Claude Code or changing the hook. It is not part of CI, which has no `claude` binary.
