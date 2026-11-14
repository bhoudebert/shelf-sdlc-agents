//! GitHub Copilot (the CLI, and agent mode where it runs hooks).
//!
//! Hooks are configured in `.github/hooks/*.json` (or by an organisation's policy files, which a user cannot remove). The
//! payload has two shapes: camelCase events (`preToolUse`, `toolName`, and `toolArgs` as a JSON *string*) and PascalCase
//! events (`PreToolUse`, `tool_name`, `tool_input` as an object) that follow Claude Code. The answer is a top-level
//! `permissionDecision`, not nested. What a guard cannot do here: a person's prompt cannot be blocked (a hook's output for it
//! is dropped); and no way to replace a tool's arguments is confirmed, so a command is judged but never wrapped: the result
//! the model sees is redacted afterwards, in `postToolUse`, with `modifiedResult`. An `ask` becomes a deny in the cloud agent
//! and in autopilot.

use serde_json::{Value, json};
use warden_policy::Decision;

use crate::claude::{output_of, path_of, strings, text, tool_of};
use crate::{Adapter, Answer, Call, Event, Rendered, Tool};

/// The GitHub Copilot adapter.
#[derive(Debug, Clone, Copy)]
pub struct Copilot;

/// The event named the way Copilot spells it, in either style.
fn event_of(name: &str) -> Event {
    match name {
        "preToolUse" | "PreToolUse" => Event::PreToolUse,
        "postToolUse" | "PostToolUse" => Event::PostToolUse,
        "userPromptSubmitted" | "UserPromptSubmit" | "UserPromptSubmitted" => Event::UserPromptSubmit,
        "sessionStart" | "SessionStart" => Event::SessionStart,
        "agentStop" | "AgentStop" | "Stop" => Event::Stop,
        "permissionRequest" | "PermissionRequest" => Event::PermissionRequest,
        other => Event::Other(other.to_owned()),
    }
}

fn arg<'a>(args: &'a Value, keys: &[&str]) -> Option<&'a str> {
    keys.iter().find_map(|key| text(args, key))
}

fn copilot_tool(name: &str, args: &Value) -> Option<Tool> {
    match name {
        "bash" | "powershell" | "Bash" | "shell" => {
            arg(args, &["command"]).map(|command| Tool::Bash { command: command.to_owned() })
        }
        "view" | "glob" | "grep" | "rg" | "Read" | "Glob" | "Grep" => path_of(args).map(|path| Tool::Read { path }),
        "create" | "Write" => Some(Tool::Write {
            path: path_of(args)?,
            content: arg(args, &["file_text", "content", "text"]).unwrap_or_default().to_owned(),
        }),
        "edit" | "str_replace_editor" | "Edit" => Some(Tool::Edit {
            path: path_of(args)?,
            new_text: arg(args, &["new_str", "new_string", "file_text", "content"]).unwrap_or_default().to_owned(),
        }),
        "web_fetch" | "WebFetch" => arg(args, &["url"]).map(|url| Tool::Web { url: url.to_owned() }),
        "task" | "Agent" => Some(Tool::Agent),
        other => tool_of(other, args).or_else(|| {
            // An MCP tool is not documented to reach a hook; if one does, its strings are what matters.
            other.starts_with("mcp").then(|| {
                let mut found = Vec::new();
                strings(args, &mut found);
                Tool::Mcp { server: String::new(), tool: other.to_owned(), strings: found }
            })
        }),
    }
}

/// The text of a tool result, in either spelling of its fields.
fn result_text(payload: &Value) -> Option<String> {
    let result = payload.get("toolResult").or_else(|| payload.get("tool_result"))?;
    result
        .get("textResultForLlm")
        .or_else(|| result.get("text_result_for_llm"))
        .and_then(Value::as_str)
        .map(str::to_owned)
        .or_else(|| output_of(result))
}

impl Adapter for Copilot {
    fn name(&self) -> &'static str {
        "copilot"
    }

    fn parse(&self, event: &str, stdin: &str) -> Result<Call, String> {
        let payload: Value =
            serde_json::from_str(stdin).map_err(|error| format!("the hook input is not JSON: {error}"))?;
        let name = payload.get("hook_event_name").and_then(Value::as_str).unwrap_or(event);
        let tool_name =
            text(&payload, "toolName").or_else(|| text(&payload, "tool_name")).unwrap_or_default().to_owned();
        // `toolArgs` is a JSON string in the camelCase style and an object in the other.
        let args = match payload.get("toolArgs").or_else(|| payload.get("tool_input")) {
            Some(Value::String(raw)) => serde_json::from_str(raw).unwrap_or(Value::String(raw.clone())),
            Some(other) => other.clone(),
            None => Value::Null,
        };
        Ok(Call {
            agent: "copilot".to_owned(),
            session: text(&payload, "sessionId")
                .or_else(|| text(&payload, "session_id"))
                .unwrap_or_default()
                .to_owned(),
            cwd: text(&payload, "cwd").unwrap_or_default().to_owned(),
            tool: copilot_tool(&tool_name, &args),
            output: result_text(&payload),
            prompt: text(&payload, "prompt").map(str::to_owned),
            event: event_of(name),
            tool_name,
            input: args,
        })
    }

    fn render(&self, call: &Call, answer: &Answer) -> Rendered {
        let body = match &call.event {
            Event::PreToolUse => match answer.decision {
                Some(Decision::Deny) => {
                    Some(json!({ "permissionDecision": "deny", "permissionDecisionReason": answer.reason }))
                }
                Some(Decision::Ask) => {
                    Some(json!({ "permissionDecision": "ask", "permissionDecisionReason": answer.reason }))
                }
                // `{}` is no decision, and an allow would approve what the person's own settings might ask about.
                _ => None,
            },
            Event::PostToolUse => {
                let mut map = serde_json::Map::new();
                if let Some(output) = &answer.updated_output {
                    map.insert(
                        "modifiedResult".to_owned(),
                        json!({ "resultType": "success", "textResultForLlm": output }),
                    );
                }
                if let Some(context) = &answer.context {
                    map.insert("additionalContext".to_owned(), Value::String(context.clone()));
                }
                (!map.is_empty()).then_some(Value::Object(map))
            }
            Event::SessionStart => answer.context.as_ref().map(|context| json!({ "additionalContext": context })),
            _ => None,
        };
        Rendered { stdout: body.map(|value| value.to_string()).unwrap_or_default(), stderr: String::new(), code: 0 }
    }

    fn refuse(&self, event: &Event, reason: &str) -> Rendered {
        match event {
            Event::PreToolUse => Rendered {
                stdout: json!({ "permissionDecision": "deny", "permissionDecisionReason": reason }).to_string(),
                stderr: format!("warden: {reason}\n"),
                code: 2,
            },
            _ => Rendered { stdout: String::new(), stderr: format!("warden: {reason}\n"), code: 0 },
        }
    }

    fn can_rewrite_input(&self) -> bool {
        false
    }

    fn can_rewrite_output(&self) -> bool {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(event: &str, payload: &Value) -> Call {
        Copilot.parse(event, &payload.to_string()).expect("parses")
    }

    #[test]
    fn the_camel_case_payload_carries_its_arguments_as_a_json_string() {
        let call = parse(
            "preToolUse",
            &json!({ "sessionId": "s", "timestamp": 1, "cwd": "/w", "toolName": "bash", "toolArgs": "{\"command\":\"ls -la\"}" }),
        );
        assert_eq!(call.event, Event::PreToolUse);
        assert_eq!((call.session.as_str(), call.cwd.as_str()), ("s", "/w"));
        assert_eq!(call.tool, Some(Tool::Bash { command: "ls -la".into() }));
    }

    #[test]
    fn the_pascal_case_payload_follows_claude() {
        let call = parse(
            "PreToolUse",
            &json!({ "hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/w", "tool_name": "Bash", "tool_input": { "command": "ls" } }),
        );
        assert_eq!(call.tool, Some(Tool::Bash { command: "ls".into() }));
    }

    #[test]
    fn files_and_fetches_are_read_whatever_the_field_spelling() {
        let cases = [
            ("view", json!({ "path": "/etc/hosts" }), Tool::Read { path: "/etc/hosts".into() }),
            (
                "create",
                json!({ "path": "a.md", "file_text": "hi" }),
                Tool::Write { path: "a.md".into(), content: "hi".into() },
            ),
            (
                "edit",
                json!({ "path": "a.rs", "old_str": "a", "new_str": "b" }),
                Tool::Edit { path: "a.rs".into(), new_text: "b".into() },
            ),
            ("web_fetch", json!({ "url": "https://docs.rs" }), Tool::Web { url: "https://docs.rs".into() }),
            ("task", json!({}), Tool::Agent),
        ];
        for (name, args, expected) in cases {
            let call = parse("preToolUse", &json!({ "toolName": name, "toolArgs": args.to_string() }));
            assert_eq!(call.tool, Some(expected), "{name}");
        }
    }

    #[test]
    fn decisions_are_top_level_and_an_allow_says_nothing() {
        let call = parse("preToolUse", &json!({ "toolName": "bash", "toolArgs": "{\"command\":\"ls\"}" }));
        let deny = Answer { decision: Some(Decision::Deny), reason: "no".into(), ..Answer::default() };
        let out: Value = serde_json::from_str(&Copilot.render(&call, &deny).stdout).expect("json");
        assert_eq!(
            (out["permissionDecision"].as_str(), out["permissionDecisionReason"].as_str()),
            (Some("deny"), Some("no"))
        );
        let ask = Answer { decision: Some(Decision::Ask), reason: "sure?".into(), ..Answer::default() };
        assert!(Copilot.render(&call, &ask).stdout.contains("\"ask\""));
        assert_eq!(Copilot.render(&call, &Answer::default()), Rendered::default());
    }

    #[test]
    fn the_result_the_model_sees_is_replaced_after_the_tool_ran() {
        let call = parse(
            "postToolUse",
            &json!({ "toolName": "bash", "toolArgs": "{}", "toolResult": { "resultType": "success", "textResultForLlm": "owner=a@b.fr" } }),
        );
        assert_eq!(call.output.as_deref(), Some("owner=a@b.fr"));
        let answer = Answer {
            updated_output: Some("owner=<EMAIL_1>".into()),
            context: Some("tokens".into()),
            ..Answer::default()
        };
        let out: Value = serde_json::from_str(&Copilot.render(&call, &answer).stdout).expect("json");
        assert_eq!(out["modifiedResult"]["textResultForLlm"], "owner=<EMAIL_1>");
        assert_eq!(out["additionalContext"], "tokens");
    }

    #[test]
    fn a_prompt_cannot_be_blocked_so_nothing_is_printed_for_it() {
        let call = parse("userPromptSubmitted", &json!({ "prompt": "my key AKIA..." }));
        let block = Answer { block_prompt: true, reason: "a credential".into(), ..Answer::default() };
        assert_eq!(Copilot.render(&call, &block), Rendered::default());
    }

    #[test]
    fn capabilities_and_refusals() {
        assert!(!Copilot.can_rewrite_input() && Copilot.can_rewrite_output());
        let refused = Copilot.refuse(&Event::PreToolUse, "unreadable");
        assert_eq!(refused.code, 2);
        assert!(refused.stdout.contains("\"deny\""));
        assert_eq!(Copilot.refuse(&Event::Stop, "unreadable").code, 0);
    }
}
