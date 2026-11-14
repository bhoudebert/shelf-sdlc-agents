//! OpenAI Codex CLI.
//!
//! Codex sends the same payload as Claude Code and understands the same `hookSpecificOutput`, with three differences that
//! matter to a guard: a `PreToolUse` hook cannot ask (an `ask` marks the hook failed and the tool goes ahead, so a question
//! is only passed on as context and Codex's own approval flow runs), file changes arrive as an `apply_patch` call whose
//! patch text names the files, and hosted tools such as web search never reach a hook.

use serde_json::{Value, json};
use warden_policy::Decision;

use crate::claude::{output_of, text, tool_of};
use crate::{Adapter, Answer, Call, Event, Rendered, Tool};

/// The Codex CLI adapter.
#[derive(Debug, Clone, Copy)]
pub struct Codex;

/// The files a patch touches, from its `*** Add File:`, `*** Update File:`, `*** Delete File:` and `*** Move to:` lines.
fn patch_paths(patch: &str) -> Vec<String> {
    patch
        .lines()
        .filter_map(|line| {
            ["*** Add File:", "*** Update File:", "*** Delete File:", "*** Move to:"]
                .iter()
                .find_map(|prefix| line.strip_prefix(prefix))
        })
        .map(|path| path.trim().to_owned())
        .filter(|path| !path.is_empty())
        .collect()
}

fn codex_tool(name: &str, input: &Value) -> Option<Tool> {
    if matches!(name, "apply_patch" | "patch") {
        // The official page puts the patch in `command`; adapters written by others use `patch`: read both.
        let patch = text(input, "command").or_else(|| text(input, "patch")).or_else(|| text(input, "input"))?;
        return Some(Tool::Patch { paths: patch_paths(patch), content: patch.to_owned() });
    }
    tool_of(name, input)
}

impl Adapter for Codex {
    fn name(&self) -> &'static str {
        "codex"
    }

    fn parse(&self, event: &str, stdin: &str) -> Result<Call, String> {
        let payload: Value =
            serde_json::from_str(stdin).map_err(|error| format!("the hook input is not JSON: {error}"))?;
        let event =
            payload.get("hook_event_name").and_then(Value::as_str).map_or_else(|| Event::parse(event), Event::parse);
        let tool_name = text(&payload, "tool_name").unwrap_or_default().to_owned();
        let input = payload.get("tool_input").cloned().unwrap_or(Value::Null);
        Ok(Call {
            agent: "codex".to_owned(),
            session: text(&payload, "session_id").unwrap_or_default().to_owned(),
            cwd: text(&payload, "cwd").unwrap_or_default().to_owned(),
            tool: codex_tool(&tool_name, &input),
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
    let (decision, reason) = match answer.decision {
        Some(Decision::Deny) => ("deny", Some(answer.reason.clone())),
        // Codex cannot ask from a PreToolUse hook: say why and let its own approval flow decide.
        Some(Decision::Ask) => {
            let context = if answer.reason.is_empty() {
                None
            } else {
                Some(format!("Warden would ask about this: {}", answer.reason))
            };
            return context.map(|context| {
                json!({ "hookSpecificOutput": { "hookEventName": "PreToolUse", "additionalContext": context } })
            });
        }
        Some(Decision::Allow) => ("allow", None),
        None if answer.updated_input.is_some() => ("allow", None),
        None => {
            return answer.context.as_ref().map(|context| {
                json!({ "hookSpecificOutput": { "hookEventName": "PreToolUse", "additionalContext": context } })
            });
        }
    };
    let mut output = json!({ "hookEventName": "PreToolUse", "permissionDecision": decision });
    if let Some(map) = output.as_object_mut() {
        if let Some(reason) = reason.filter(|r| !r.is_empty()) {
            map.insert("permissionDecisionReason".to_owned(), Value::String(reason));
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
        Codex.parse(event, &payload.to_string()).expect("parses")
    }

    #[test]
    fn a_shell_call_is_read_like_claudes() {
        let call = parse(
            "PreToolUse",
            &json!({ "session_id": "s", "cwd": "/w", "hook_event_name": "PreToolUse",
            "tool_name": "Bash", "tool_input": { "command": "ls" } }),
        );
        assert_eq!(call.agent, "codex");
        assert_eq!(call.tool, Some(Tool::Bash { command: "ls".into() }));
    }

    #[test]
    fn a_patch_names_the_files_it_touches_whichever_field_holds_it() {
        let patch = "*** Begin Patch\n*** Update File: src/a.rs\n@@\n-x\n+y\n*** Add File: docs/new.md\n+hi\n*** Delete File: old.txt\n*** End Patch";
        for field in ["command", "patch"] {
            let call = parse("PreToolUse", &json!({ "tool_name": "apply_patch", "tool_input": { field: patch } }));
            assert_eq!(
                call.tool,
                Some(Tool::Patch {
                    paths: vec!["src/a.rs".into(), "docs/new.md".into(), "old.txt".into()],
                    content: patch.into()
                }),
                "{field}"
            );
        }
    }

    #[test]
    fn a_deny_and_a_rewrite_are_claudes_shape() {
        let call = parse("PreToolUse", &json!({ "tool_name": "Bash", "tool_input": { "command": "ls" } }));
        let deny = Answer { decision: Some(Decision::Deny), reason: "no".into(), ..Answer::default() };
        let out: Value = serde_json::from_str(&Codex.render(&call, &deny).stdout).expect("json");
        assert_eq!(out["hookSpecificOutput"]["permissionDecision"], "deny");
        let rewrite = Answer { updated_input: Some(json!({ "command": "warden run -- ls" })), ..Answer::default() };
        let out: Value = serde_json::from_str(&Codex.render(&call, &rewrite).stdout).expect("json");
        assert_eq!(out["hookSpecificOutput"]["permissionDecision"], "allow");
        assert_eq!(out["hookSpecificOutput"]["updatedInput"]["command"], "warden run -- ls");
    }

    #[test]
    fn an_ask_is_never_sent_because_codex_would_fail_open_and_goes_as_context() {
        let call =
            parse("PreToolUse", &json!({ "tool_name": "Bash", "tool_input": { "command": "git reset --hard" } }));
        let ask =
            Answer { decision: Some(Decision::Ask), reason: "it throws changes away".into(), ..Answer::default() };
        let out: Value = serde_json::from_str(&Codex.render(&call, &ask).stdout).expect("json");
        assert!(out["hookSpecificOutput"].get("permissionDecision").is_none(), "{out}");
        assert!(
            out["hookSpecificOutput"]["additionalContext"]
                .as_str()
                .expect("context")
                .contains("it throws changes away")
        );
    }

    #[test]
    fn a_prompt_is_blocked_and_context_follows_a_tool() {
        let call = parse("UserPromptSubmit", &json!({ "prompt": "x" }));
        let block = Answer { block_prompt: true, reason: "a credential".into(), ..Answer::default() };
        assert!(Codex.render(&call, &block).stdout.contains("\"decision\":\"block\""));
        let after = parse("PostToolUse", &json!({ "tool_name": "Bash", "tool_response": "out" }));
        let note = Answer { context: Some("careful".into()), ..Answer::default() };
        assert!(Codex.render(&after, &note).stdout.contains("\"additionalContext\":\"careful\""));
    }

    #[test]
    fn unreadable_input_is_refused_and_codex_can_rewrite_input_but_not_output() {
        assert!(Codex.refuse(&Event::PreToolUse, "unreadable").stdout.contains("\"deny\""));
        assert_eq!(Codex.refuse(&Event::Stop, "unreadable").code, 2);
        assert!(Codex.can_rewrite_input() && !Codex.can_rewrite_output());
    }
}
