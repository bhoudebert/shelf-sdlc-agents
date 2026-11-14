//! OpenCode.
//!
//! OpenCode has no external-command hooks: it loads plugins, in-process JavaScript. Warden ships a small plugin that calls
//! `warden hook opencode <event>` with one JSON object on standard input and acts on the JSON that comes back, so this
//! adapter speaks a format Warden owns. The plugin throws to refuse a call (the way OpenCode's own example does), replaces
//! the tool's arguments in place, and replaces the tool's output after it ran. Tool names are lowercase and the argument names
//! (`filePath`, `command`, `url`) are the ones OpenCode's built-in tools use; a guard reads several spellings.
//! Known gap: calls made through OpenCode's `batch` tool skip plugin hooks.

use serde_json::{Value, json};
use warden_policy::Decision;

use crate::claude::{path_of, strings, text};
use crate::{Adapter, Answer, Call, Event, Rendered, Tool};

/// The OpenCode adapter.
#[derive(Debug, Clone, Copy)]
pub struct OpenCode;

fn event_of(name: &str) -> Event {
    match name {
        "tool.before" => Event::PreToolUse,
        "tool.after" => Event::PostToolUse,
        "prompt" => Event::UserPromptSubmit,
        "session" => Event::SessionStart,
        other => Event::parse(other),
    }
}

fn opencode_tool(name: &str, args: &Value) -> Option<Tool> {
    match name {
        "bash" | "shell" => text(args, "command").map(|command| Tool::Bash { command: command.to_owned() }),
        "read" | "glob" | "grep" | "list" | "ls" => {
            path_of(args).or_else(|| text(args, "filePath").map(str::to_owned)).map(|path| Tool::Read { path })
        }
        "write" => Some(Tool::Write {
            path: path_of(args).or_else(|| text(args, "filePath").map(str::to_owned))?,
            content: text(args, "content").unwrap_or_default().to_owned(),
        }),
        "edit" | "patch" | "multiedit" => Some(Tool::Edit {
            path: path_of(args).or_else(|| text(args, "filePath").map(str::to_owned))?,
            new_text: text(args, "newString").or_else(|| text(args, "new_string")).unwrap_or_default().to_owned(),
        }),
        "webfetch" => text(args, "url").map(|url| Tool::Web { url: url.to_owned() }),
        "task" => Some(Tool::Agent),
        other if other.contains('_') && !matches!(other, "todo_write" | "todo_read") => {
            let (server, tool) = other.split_once('_').unwrap_or((other, ""));
            let mut found = Vec::new();
            strings(args, &mut found);
            Some(Tool::Mcp { server: server.to_owned(), tool: tool.to_owned(), strings: found })
        }
        _ => None,
    }
}

impl Adapter for OpenCode {
    fn name(&self) -> &'static str {
        "opencode"
    }

    fn parse(&self, event: &str, stdin: &str) -> Result<Call, String> {
        let payload: Value =
            serde_json::from_str(stdin).map_err(|error| format!("the hook input is not JSON: {error}"))?;
        let tool_name = text(&payload, "tool").unwrap_or_default().to_owned();
        let args = payload.get("args").cloned().unwrap_or(Value::Null);
        Ok(Call {
            agent: "opencode".to_owned(),
            session: text(&payload, "sessionID").unwrap_or_default().to_owned(),
            cwd: text(&payload, "cwd").unwrap_or_default().to_owned(),
            tool: opencode_tool(&tool_name, &args),
            output: text(&payload, "output").map(str::to_owned),
            prompt: text(&payload, "prompt").map(str::to_owned),
            event: event_of(text(&payload, "event").unwrap_or(event)),
            tool_name,
            input: args,
        })
    }

    fn render(&self, _call: &Call, answer: &Answer) -> Rendered {
        let decision = match answer.decision {
            Some(Decision::Deny) => "deny",
            Some(Decision::Ask) => "ask",
            _ => "allow",
        };
        let body = json!({
            "decision": decision,
            "reason": answer.reason,
            "args": answer.updated_input,
            "output": answer.updated_output,
            "context": answer.context,
            "block": answer.block_prompt,
        });
        Rendered { stdout: body.to_string(), stderr: String::new(), code: 0 }
    }

    fn refuse(&self, _event: &Event, reason: &str) -> Rendered {
        Rendered {
            stdout: json!({ "decision": "deny", "reason": reason, "block": true }).to_string(),
            stderr: String::new(),
            code: 0,
        }
    }

    fn can_rewrite_input(&self) -> bool {
        true
    }

    fn can_rewrite_output(&self) -> bool {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(event: &str, payload: &Value) -> Call {
        OpenCode.parse(event, &payload.to_string()).expect("parses")
    }

    #[test]
    fn the_plugins_events_are_mapped_and_lowercase_tools_are_read() {
        let call = parse(
            "tool.before",
            &json!({ "tool": "bash", "args": { "command": "ls" }, "sessionID": "s", "cwd": "/w" }),
        );
        assert_eq!(call.event, Event::PreToolUse);
        assert_eq!(call.tool, Some(Tool::Bash { command: "ls".into() }));
        assert_eq!((call.session.as_str(), call.cwd.as_str()), ("s", "/w"));
        assert_eq!(parse("tool.after", &json!({ "tool": "bash", "output": "x" })).event, Event::PostToolUse);
        assert_eq!(parse("prompt", &json!({ "prompt": "hi" })).prompt.as_deref(), Some("hi"));
    }

    #[test]
    fn files_use_file_path_and_fetches_use_url() {
        let cases = [
            ("read", json!({ "filePath": "/etc/hosts" }), Tool::Read { path: "/etc/hosts".into() }),
            (
                "write",
                json!({ "filePath": "a.md", "content": "hi" }),
                Tool::Write { path: "a.md".into(), content: "hi".into() },
            ),
            (
                "edit",
                json!({ "filePath": "a.rs", "oldString": "a", "newString": "b" }),
                Tool::Edit { path: "a.rs".into(), new_text: "b".into() },
            ),
            ("webfetch", json!({ "url": "https://docs.rs" }), Tool::Web { url: "https://docs.rs".into() }),
        ];
        for (name, args, expected) in cases {
            assert_eq!(parse("tool.before", &json!({ "tool": name, "args": args })).tool, Some(expected), "{name}");
        }
    }

    #[test]
    fn a_tool_with_a_server_prefix_is_an_mcp_call() {
        let call = parse("tool.before", &json!({ "tool": "slack_post", "args": { "text": "hi" } }));
        assert_eq!(
            call.tool,
            Some(Tool::Mcp { server: "slack".into(), tool: "post".into(), strings: vec!["hi".into()] })
        );
    }

    #[test]
    fn the_answer_is_json_the_plugin_acts_on() {
        let call = parse("tool.before", &json!({ "tool": "bash", "args": {} }));
        let answer = Answer {
            decision: Some(Decision::Deny),
            reason: "no".into(),
            updated_input: Some(json!({ "command": "x" })),
            updated_output: Some("y".into()),
            ..Answer::default()
        };
        let out: Value = serde_json::from_str(&OpenCode.render(&call, &answer).stdout).expect("json");
        assert_eq!((out["decision"].as_str(), out["reason"].as_str()), (Some("deny"), Some("no")));
        assert_eq!((out["args"]["command"].as_str(), out["output"].as_str()), (Some("x"), Some("y")));
        let nothing: Value = serde_json::from_str(&OpenCode.render(&call, &Answer::default()).stdout).expect("json");
        assert_eq!(nothing["decision"], "allow");
    }

    #[test]
    fn a_failure_denies_and_both_directions_can_be_rewritten() {
        let refused: Value =
            serde_json::from_str(&OpenCode.refuse(&Event::PreToolUse, "unreadable").stdout).expect("json");
        assert_eq!((refused["decision"].as_str(), refused["block"].as_bool()), (Some("deny"), Some(true)));
        assert!(OpenCode.can_rewrite_input() && OpenCode.can_rewrite_output());
    }
}
