//! Claude Code.
//!
//! Hooks are configured in `settings.json` (user, project, or the managed settings an organisation controls) and called
//! with one JSON object on standard input. A hook that prints nothing and exits 0 gives no decision, so the agent's
//! own permission flow goes on. A decision is printed as `hookSpecificOutput` with `permissionDecision` (`allow`,
//! `deny`, `ask`); `updatedInput` replaces the arguments of the tool; `additionalContext` is shown to the model.

use serde_json::{Value, json};
use warden_policy::Decision;

use crate::{Adapter, Answer, Call, Event, Rendered, Tool};

/// The Claude Code adapter.
#[derive(Debug, Clone, Copy)]
pub struct Claude;

pub(crate) fn text<'a>(input: &'a Value, key: &str) -> Option<&'a str> {
    input.get(key)?.as_str()
}

pub(crate) fn strings(value: &Value, into: &mut Vec<String>) {
    match value {
        Value::String(s) => into.push(s.clone()),
        Value::Array(items) => items.iter().for_each(|item| strings(item, into)),
        Value::Object(map) => map.values().for_each(|item| strings(item, into)),
        _ => {}
    }
}

pub(crate) fn path_of(input: &Value) -> Option<String> {
    ["file_path", "notebook_path", "path"].iter().find_map(|key| text(input, key)).map(str::to_owned)
}

pub(crate) fn tool_of(name: &str, input: &Value) -> Option<Tool> {
    match name {
        "Bash" => text(input, "command").map(|command| Tool::Bash { command: command.to_owned() }),
        "Read" | "NotebookRead" | "Glob" | "Grep" | "LS" => path_of(input).map(|path| Tool::Read { path }),
        "Write" | "NotebookEdit" => Some(Tool::Write {
            path: path_of(input)?,
            content: text(input, "content").or_else(|| text(input, "new_source")).unwrap_or_default().to_owned(),
        }),
        "Edit" => Some(Tool::Edit {
            path: path_of(input)?,
            new_text: text(input, "new_string").unwrap_or_default().to_owned(),
        }),
        "MultiEdit" => {
            let edits: Vec<String> = input
                .get("edits")
                .and_then(Value::as_array)
                .map(|list| list.iter().filter_map(|e| text(e, "new_string")).map(str::to_owned).collect())
                .unwrap_or_default();
            Some(Tool::Edit { path: path_of(input)?, new_text: edits.join("\n") })
        }
        "WebFetch" => text(input, "url").map(|url| Tool::Web { url: url.to_owned() }),
        "Task" | "Agent" => Some(Tool::Agent),
        _ => {
            let rest = name.strip_prefix("mcp__")?;
            let (server, tool) = rest.split_once("__").unwrap_or((rest, ""));
            let mut found = Vec::new();
            strings(input, &mut found);
            Some(Tool::Mcp { server: server.to_owned(), tool: tool.to_owned(), strings: found })
        }
    }
}

/// The text a tool printed, from the `tool_response` of a `PostToolUse` payload.
pub(crate) fn output_of(response: &Value) -> Option<String> {
    match response {
        Value::String(text) => Some(text.clone()),
        Value::Object(map) => {
            let parts: Vec<&str> =
                ["stdout", "stderr", "output", "content"].iter().filter_map(|k| map.get(*k)?.as_str()).collect();
            if parts.is_empty() {
                let mut found = Vec::new();
                strings(response, &mut found);
                (!found.is_empty()).then(|| found.join("\n"))
            } else {
                Some(parts.join("\n"))
            }
        }
        Value::Null => None,
        other => Some(other.to_string()),
    }
}

impl Adapter for Claude {
    fn name(&self) -> &'static str {
        "claude"
    }

    fn parse(&self, event: &str, stdin: &str) -> Result<Call, String> {
        let payload: Value =
            serde_json::from_str(stdin).map_err(|error| format!("the hook input is not JSON: {error}"))?;
        let event =
            payload.get("hook_event_name").and_then(Value::as_str).map_or_else(|| Event::parse(event), Event::parse);
        let tool_name = text(&payload, "tool_name").unwrap_or_default().to_owned();
        let input = payload.get("tool_input").cloned().unwrap_or(Value::Null);
        Ok(Call {
            agent: "claude".to_owned(),
            session: text(&payload, "session_id").unwrap_or_default().to_owned(),
            cwd: text(&payload, "cwd").unwrap_or_default().to_owned(),
            tool: tool_of(&tool_name, &input),
            output: payload.get("tool_response").and_then(output_of),
            prompt: text(&payload, "prompt").map(str::to_owned),
            event,
            tool_name,
            input,
        })
    }

    fn render(&self, call: &Call, answer: &Answer) -> Rendered {
        let event = call.event.name();
        let body = match &call.event {
            Event::PreToolUse => pre_tool_use(answer),
            Event::UserPromptSubmit if answer.block_prompt => {
                Some(json!({ "decision": "block", "reason": answer.reason }))
            }
            Event::PostToolUse | Event::UserPromptSubmit | Event::SessionStart => answer.context.as_ref().map(
                |context| json!({ "hookSpecificOutput": { "hookEventName": event, "additionalContext": context } }),
            ),
            _ => None,
        };
        Rendered { stdout: body.map(|value| value.to_string()).unwrap_or_default(), stderr: String::new(), code: 0 }
    }

    fn refuse(&self, event: &Event, reason: &str) -> Rendered {
        let body = match event {
            Event::PreToolUse => json!({ "hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason } }),
            Event::UserPromptSubmit => json!({ "decision": "block", "reason": reason }),
            _ => return Rendered { stdout: String::new(), stderr: format!("warden: {reason}\n"), code: 2 },
        };
        Rendered { stdout: body.to_string(), stderr: String::new(), code: 0 }
    }
}

fn pre_tool_use(answer: &Answer) -> Option<Value> {
    let decision = match answer.decision {
        Some(Decision::Deny) => "deny",
        Some(Decision::Ask) => "ask",
        Some(Decision::Allow) => "allow",
        None if answer.updated_input.is_some() => "allow",
        None => return answer.context.as_ref().map(
            |context| json!({ "hookSpecificOutput": { "hookEventName": "PreToolUse", "additionalContext": context } }),
        ),
    };
    let mut output = json!({ "hookEventName": "PreToolUse", "permissionDecision": decision });
    if let Some(map) = output.as_object_mut() {
        if !answer.reason.is_empty() {
            map.insert("permissionDecisionReason".to_owned(), Value::String(answer.reason.clone()));
        }
        if let Some(updated) = &answer.updated_input {
            map.insert("updatedInput".to_owned(), updated.clone());
        }
        if let Some(context) = &answer.context {
            map.insert("additionalContext".to_owned(), Value::String(context.clone()));
        }
    }
    Some(json!({ "hookSpecificOutput": output }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(event: &str, payload: &Value) -> Call {
        Claude.parse(event, &payload.to_string()).expect("parses")
    }

    #[test]
    fn a_bash_call_is_read_with_its_session_and_directory() {
        let call = parse(
            "PreToolUse",
            &json!({ "session_id": "s1", "cwd": "/work/app", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": { "command": "npm test", "description": "Run tests" } }),
        );
        assert_eq!(call.event, Event::PreToolUse);
        assert_eq!((call.session.as_str(), call.cwd.as_str()), ("s1", "/work/app"));
        assert_eq!(call.tool, Some(Tool::Bash { command: "npm test".into() }));
    }

    #[test]
    fn the_event_argument_is_used_when_the_payload_names_none() {
        let call = parse("UserPromptSubmit", &json!({ "prompt": "fix the bug" }));
        assert_eq!(call.event, Event::UserPromptSubmit);
        assert_eq!(call.prompt.as_deref(), Some("fix the bug"));
    }

    #[test]
    fn files_urls_and_subagents_are_read() {
        let cases = [
            ("Read", json!({ "file_path": "/etc/hosts" }), Tool::Read { path: "/etc/hosts".into() }),
            ("Grep", json!({ "pattern": "x", "path": "src" }), Tool::Read { path: "src".into() }),
            (
                "Write",
                json!({ "file_path": "a.md", "content": "hello" }),
                Tool::Write { path: "a.md".into(), content: "hello".into() },
            ),
            (
                "Edit",
                json!({ "file_path": "a.rs", "old_string": "a", "new_string": "b" }),
                Tool::Edit { path: "a.rs".into(), new_text: "b".into() },
            ),
            (
                "MultiEdit",
                json!({ "file_path": "a.rs", "edits": [{ "old_string": "a", "new_string": "b" }, { "old_string": "c", "new_string": "d" }] }),
                Tool::Edit { path: "a.rs".into(), new_text: "b\nd".into() },
            ),
            (
                "WebFetch",
                json!({ "url": "https://docs.rs", "prompt": "p" }),
                Tool::Web { url: "https://docs.rs".into() },
            ),
            ("Task", json!({ "prompt": "go" }), Tool::Agent),
        ];
        for (name, input, expected) in cases {
            let call = parse("PreToolUse", &json!({ "tool_name": name, "tool_input": input }));
            assert_eq!(call.tool, Some(expected), "{name}");
        }
    }

    #[test]
    fn an_mcp_call_carries_every_string_of_its_arguments() {
        let call = parse(
            "PreToolUse",
            &json!({ "tool_name": "mcp__slack__post_message", "tool_input": { "channel": "#ops", "blocks": [{ "text": "hi" }], "n": 3 } }),
        );
        let Some(Tool::Mcp { server, tool, mut strings }) = call.tool else { panic!("not an mcp call") };
        strings.sort();
        assert_eq!((server.as_str(), tool.as_str()), ("slack", "post_message"));
        assert_eq!(strings, ["#ops", "hi"]);
    }

    #[test]
    fn an_unknown_tool_has_no_kind_and_a_response_becomes_text() {
        let call = parse(
            "PostToolUse",
            &json!({ "tool_name": "TodoWrite", "tool_input": {}, "tool_response": { "stdout": "out", "stderr": "err" } }),
        );
        assert_eq!(call.tool, None);
        assert_eq!(call.output.as_deref(), Some("out\nerr"));
        let call = parse("PostToolUse", &json!({ "tool_name": "Bash", "tool_response": "plain" }));
        assert_eq!(call.output.as_deref(), Some("plain"));
    }

    #[test]
    fn input_that_is_not_json_is_an_error() {
        assert!(Claude.parse("PreToolUse", "not json").is_err());
    }

    fn pre() -> Call {
        parse("PreToolUse", &json!({ "tool_name": "Bash", "tool_input": { "command": "ls" } }))
    }

    #[test]
    fn no_decision_prints_nothing_so_the_agents_own_flow_goes_on() {
        assert_eq!(Claude.render(&pre(), &Answer::default()), Rendered::default());
    }

    #[test]
    fn a_deny_carries_the_reason() {
        let answer = Answer { decision: Some(Decision::Deny), reason: "no".into(), ..Answer::default() };
        let out: Value = serde_json::from_str(&Claude.render(&pre(), &answer).stdout).expect("json");
        assert_eq!(out["hookSpecificOutput"]["hookEventName"], "PreToolUse");
        assert_eq!(out["hookSpecificOutput"]["permissionDecision"], "deny");
        assert_eq!(out["hookSpecificOutput"]["permissionDecisionReason"], "no");
    }

    #[test]
    fn an_ask_is_an_ask() {
        let answer = Answer { decision: Some(Decision::Ask), reason: "sure?".into(), ..Answer::default() };
        let out: Value = serde_json::from_str(&Claude.render(&pre(), &answer).stdout).expect("json");
        assert_eq!(out["hookSpecificOutput"]["permissionDecision"], "ask");
    }

    #[test]
    fn replaced_arguments_are_sent_with_an_allow() {
        let answer = Answer { updated_input: Some(json!({ "command": "warden run -- ls" })), ..Answer::default() };
        let out: Value = serde_json::from_str(&Claude.render(&pre(), &answer).stdout).expect("json");
        assert_eq!(out["hookSpecificOutput"]["permissionDecision"], "allow");
        assert_eq!(out["hookSpecificOutput"]["updatedInput"]["command"], "warden run -- ls");
    }

    #[test]
    fn context_alone_is_not_a_decision() {
        let answer = Answer { context: Some("remember the tokens".into()), ..Answer::default() };
        let out: Value = serde_json::from_str(&Claude.render(&pre(), &answer).stdout).expect("json");
        assert!(out["hookSpecificOutput"].get("permissionDecision").is_none());
        assert_eq!(out["hookSpecificOutput"]["additionalContext"], "remember the tokens");
    }

    #[test]
    fn a_prompt_is_blocked_with_a_top_level_decision() {
        let call = parse("UserPromptSubmit", &json!({ "prompt": "my key is ghp_x" }));
        let answer = Answer { block_prompt: true, reason: "a credential".into(), ..Answer::default() };
        let out: Value = serde_json::from_str(&Claude.render(&call, &answer).stdout).expect("json");
        assert_eq!((out["decision"].as_str(), out["reason"].as_str()), (Some("block"), Some("a credential")));
    }

    #[test]
    fn context_is_added_after_a_tool_and_at_the_start_of_a_session() {
        for event in ["PostToolUse", "SessionStart"] {
            let call = parse(event, &json!({ "tool_name": "Bash" }));
            let answer = Answer { context: Some("hello".into()), ..Answer::default() };
            let out: Value = serde_json::from_str(&Claude.render(&call, &answer).stdout).expect("json");
            assert_eq!(out["hookSpecificOutput"]["hookEventName"], event);
            assert_eq!(out["hookSpecificOutput"]["additionalContext"], "hello");
        }
    }

    #[test]
    fn a_hook_that_cannot_read_its_input_refuses_in_the_agents_own_way() {
        let tool = Claude.refuse(&Event::PreToolUse, "unreadable");
        let out: Value = serde_json::from_str(&tool.stdout).expect("json");
        assert_eq!(out["hookSpecificOutput"]["permissionDecision"], "deny");
        let prompt = Claude.refuse(&Event::UserPromptSubmit, "unreadable");
        assert!(prompt.stdout.contains("\"decision\":\"block\""));
        let other = Claude.refuse(&Event::Stop, "unreadable");
        assert_eq!((other.code, other.stdout.as_str()), (2, ""));
    }

    #[test]
    fn the_adapter_is_found_by_name() {
        assert_eq!(crate::adapter("claude").map(|a| a.name()), Some("claude"));
        assert!(crate::adapter("nope").is_none());
    }
}
