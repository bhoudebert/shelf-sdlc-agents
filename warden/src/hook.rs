//! `warden hook <agent> <event>`: what an agent calls before it uses a tool.
//!
//! The hook reads the agent's payload, judges it against the policy, and answers in the agent's own format. An allowed
//! command is wrapped so that its output runs through the redactor; tokens the model writes into a file are put back;
//! a credential in a prompt, a file or a tool argument is refused. Every decision is logged. A policy that cannot be
//! loaded denies.

use std::path::{Path, PathBuf};

use serde_json::Value;
use warden_agents::{Answer, Call, Event, Rendered, Tool};
use warden_audit::{AuditLog, Entry, digest_of, shorten};
use warden_engine::{Context, Verdict, judge_command, judge_read, judge_text, judge_tool, judge_web, judge_write};
use warden_policy::{Category, Decision, Mode, OnError, Policy, PromptMode, ReadTool};
use warden_redact::{Counts, Kind, Redactor, Session};

use crate::load::{self, Sources};
use crate::run::{redactor_for, session_path};

/// Where the hook runs: who, from where, and with which binary.
pub struct Setting {
    /// The home directory.
    pub home: PathBuf,
    /// The working directory when the payload names none.
    pub cwd: PathBuf,
    /// Where the token maps of sessions are kept.
    pub session_dir: PathBuf,
    /// This binary, which wrapped commands call back.
    pub exe: PathBuf,
    /// A preset to start from, below the files.
    pub profile: Option<warden_policy::Profile>,
}

/// Quote text as one word for a POSIX shell.
fn quote(text: &str) -> String {
    format!("'{}'", text.replace('\'', "'\\''"))
}

/// Run the hook: `stdin` is what the agent sent.
pub fn run(agent: &str, event: &str, stdin: &str, setting: &Setting) -> Rendered {
    let Some(adapter) = warden_agents::adapter(agent) else {
        return Rendered {
            stderr: format!("warden: no adapter for the agent {agent:?}\n"),
            code: 2,
            ..Rendered::default()
        };
    };
    let sources = Sources {
        profile: setting.profile,
        files: true,
        global: None,
        operator: None,
        cwd: setting.cwd.clone(),
        home: setting.home.clone(),
    };
    let policy = match load::policy(&sources) {
        Ok(policy) => policy,
        Err(error) => {
            return adapter
                .refuse(&Event::parse(event), &format!("the policy cannot be loaded, so nothing is allowed: {error}"));
        }
    };
    let call = match adapter.parse(event, stdin) {
        Ok(call) => call,
        Err(error) => {
            return if policy.on_error == OnError::Closed {
                adapter.refuse(&Event::parse(event), &error)
            } else {
                Rendered { stderr: format!("warden: {error}\n"), ..Rendered::default() }
            };
        }
    };
    let redactor = match redactor_for(&policy) {
        Ok(redactor) => redactor,
        Err(error) => return adapter.refuse(&call.event, &format!("a redaction pattern is broken: {error}")),
    };
    let ctx = Context {
        home: setting.home.clone(),
        cwd: if call.cwd.is_empty() { setting.cwd.clone() } else { PathBuf::from(&call.cwd) },
    };
    if policy.audit.enabled {
        move_spooled_records(&policy, setting, &call.session, &ctx);
    }
    let path = session_path(&setting.session_dir, &call.session);
    let mut session = Session::open(&path).unwrap_or_default();
    let mut decided = Decided::default();
    let answer = decide(&policy, &ctx, &call, &redactor, &mut session, setting, &mut decided);
    if let Err(error) = session.save() {
        crate::spool::note(&format!("cannot save the session tokens: {error}"));
    }
    if policy.audit.enabled && decided.worth_logging(&call) {
        log(&policy, &ctx, setting, &call, &redactor, &decided, &answer);
    }
    adapter.render(&call, &answer)
}

/// Put the audit records that `warden run` left for this session, inside the sandbox, into the log.
fn move_spooled_records(policy: &Policy, setting: &Setting, session: &str, ctx: &Context) {
    let records = crate::spool::drain(&setting.session_dir, session);
    if records.is_empty() {
        return;
    }
    let log = AuditLog::new(crate::audit_dir(ctx, policy));
    for record in records {
        if let Err(error) = log.append(&record) {
            crate::spool::note(&format!("cannot write the audit log: {error}"));
        }
    }
}

/// What the judging found, for the log.
#[derive(Default)]
struct Decided {
    verdict: Option<Verdict>,
    note: Option<String>,
    redactions: Counts,
    prompt_chars: usize,
}

impl Decided {
    fn worth_logging(&self, call: &Call) -> bool {
        !matches!(call.event, Event::PostToolUse | Event::PermissionRequest | Event::Other(_)) || self.note.is_some()
    }
}

fn from_verdict(verdict: &Verdict, call: &Call) -> Answer {
    let mut reason = verdict.reason.clone();
    if verdict.decision == Decision::Deny && matches!(call.tool, Some(Tool::Bash { .. })) {
        reason.push_str(
            " Choose a safer way. `warden explain '<command>'` shows how a command is judged. Do not try to get around this \
             (bash -c, base64, an interpreter): those are findings too.",
        );
    }
    match verdict.decision {
        Decision::Allow => Answer::default(),
        decision => Answer { decision: Some(decision), reason, ..Answer::default() },
    }
}

fn strictest(left: Option<Verdict>, right: Verdict) -> Verdict {
    match left {
        Some(left) if left.decision >= right.decision => left,
        _ => right,
    }
}

fn decide(
    policy: &Policy,
    ctx: &Context,
    call: &Call,
    redactor: &Redactor,
    session: &mut Session,
    setting: &Setting,
    decided: &mut Decided,
) -> Answer {
    match call.event {
        Event::PreToolUse => pre_tool(policy, ctx, call, redactor, session, setting, decided),
        Event::PostToolUse => post_tool(call, redactor, decided),
        Event::UserPromptSubmit => prompt(policy, call, redactor, decided),
        Event::SessionStart => Answer { context: Some(house_rules(policy)), ..Answer::default() },
        _ => Answer::default(),
    }
}

fn house_rules(policy: &Policy) -> String {
    let who = if policy.interactive { "A person can be asked" } else { "Nobody is there to answer a question" };
    format!(
        "Warden guards this session (profile {}). Every command, file access and fetch is checked before it runs, and a \
         refusal comes with its reason. {who}: when something is refused, do not retry it another way (bash -c, base64, \
         an interpreter); choose a safer approach or say what you need. Values such as <EMAIL_1> or <SECRET_2> stand \
         for real data you are not shown: use the token as it is, it is restored when you write a file. You may run \
         `warden explain '<command>'`, `warden status` and `warden doctor`.",
        policy.profile.name()
    )
}

fn pre_tool(
    policy: &Policy,
    ctx: &Context,
    call: &Call,
    redactor: &Redactor,
    session: &mut Session,
    setting: &Setting,
    decided: &mut Decided,
) -> Answer {
    let mut verdict = judge_tool(policy, &call.tool_name);
    let mut answer = Answer::default();
    match &call.tool {
        Some(Tool::Bash { command }) => {
            let judged = judge_command(policy, ctx, command);
            answer = bash_answer(policy, call, &judged, setting);
            verdict = Some(strictest(verdict, judged));
        }
        Some(Tool::Read { path }) => {
            let mut judged = judge_read(policy, ctx, path);
            if judged.decision == Decision::Allow && personal_data(policy, ctx, path) {
                judged = refuse_personal(policy, path);
            }
            verdict = Some(strictest(verdict, judged));
        }
        Some(Tool::Write { path, content }) => {
            let (judged, updated) =
                file_content(policy, ctx, redactor, session, call, path, content, "content", decided);
            answer.updated_input = updated;
            verdict = Some(strictest(verdict, judged));
        }
        Some(Tool::Edit { path, new_text }) => {
            let (judged, updated) =
                file_content(policy, ctx, redactor, session, call, path, new_text, "new_string", decided);
            answer.updated_input = updated;
            verdict = Some(strictest(verdict, judged));
        }
        Some(Tool::Web { url }) => verdict = Some(strictest(verdict, judge_web(policy, url))),
        Some(Tool::Mcp { strings, .. }) if policy.redact.mcp => {
            let (judged, updated) = mcp_arguments(policy, redactor, session, call, strings, decided);
            answer.updated_input = updated;
            verdict = Some(strictest(verdict, judged));
        }
        Some(Tool::Patch { .. } | Tool::Agent | Tool::Mcp { .. }) | None => {}
    }
    if let Some(verdict) = verdict.as_ref().filter(|v| v.decision != Decision::Allow) {
        answer = Answer { updated_input: None, ..from_verdict(verdict, call) };
    }
    decided.verdict = verdict;
    answer
}

/// The answer for a shell command: refused, or allowed with its line rewritten and its output wrapped.
fn bash_answer(policy: &Policy, call: &Call, verdict: &Verdict, setting: &Setting) -> Answer {
    if verdict.decision != Decision::Allow {
        return Answer::default();
    }
    let wrapped = verdict.wrap_output && policy.redact.outputs;
    if !wrapped && verdict.rewritten.is_none() {
        return Answer::default();
    }
    let line = if wrapped {
        format!(
            "{} run --session {} -- {}",
            quote(&setting.exe.display().to_string()),
            quote(&call.session),
            quote(verdict.line())
        )
    } else {
        verdict.line().to_owned()
    };
    let mut input = call.input.clone();
    if let Some(map) = input.as_object_mut() {
        map.insert("command".to_owned(), Value::String(line));
    }
    Answer { updated_input: Some(input), ..Answer::default() }
}

fn personal_data(policy: &Policy, ctx: &Context, path: &str) -> bool {
    let word =
        warden_shell::Word { raw: path.to_owned(), value: Some(path.to_owned()), ..warden_shell::Word::default() };
    policy.redact.read_tool == ReadTool::Deny && policy.paths.pii.is_match(&ctx.candidates(&word))
}

fn refuse_personal(policy: &Policy, path: &str) -> Verdict {
    let mut verdict = judge_text(policy, path, "", Category::PiiRead);
    verdict.decision = policy.decision(Category::PiiRead);
    verdict.intended = verdict.decision;
    verdict.reason = format!(
        "{path} holds personal data, and the Read tool cannot redact it. Read it through the shell (cat, head, grep): \
         the output is redacted."
    );
    verdict
}

/// A file written or edited: the path, a credential in the content, and tokens to put back.
#[allow(clippy::too_many_arguments)]
fn file_content(
    policy: &Policy,
    ctx: &Context,
    redactor: &Redactor,
    session: &mut Session,
    call: &Call,
    path: &str,
    text: &str,
    key: &str,
    decided: &mut Decided,
) -> (Verdict, Option<Value>) {
    let (restored_text, restored) = redactor.restore(session, text);
    let mut verdict = judge_write(policy, ctx, path);
    verdict = strictest(Some(verdict), judge_text(policy, path, &restored_text, Category::SecretWrite));
    let updated = (restored > 0).then(|| {
        decided.note = Some(format!("{restored} token(s) restored in {path}"));
        let mut input = call.input.clone();
        if let Some(map) = input.as_object_mut() {
            map.insert(key.to_owned(), Value::String(restored_text));
        }
        input
    });
    (verdict, updated)
}

/// Arguments of an MCP tool: a credential refuses the call, personal data is replaced by tokens.
fn mcp_arguments(
    policy: &Policy,
    redactor: &Redactor,
    session: &mut Session,
    call: &Call,
    strings: &[String],
    decided: &mut Decided,
) -> (Verdict, Option<Value>) {
    let verdict = judge_text(policy, &call.tool_name, &strings.join("\n"), Category::SecretWrite);
    if verdict.decision != Decision::Allow {
        return (verdict, None);
    }
    let mut changed = Counts::new();
    let updated = map_strings(&call.input, &mut |text| {
        let (clean, found) = redactor.redact(session, text);
        changed.merge(&found);
        clean
    });
    if changed.is_empty() {
        return (verdict, None);
    }
    decided.redactions.merge(&changed);
    (verdict, Some(updated))
}

fn map_strings(value: &Value, f: &mut dyn FnMut(&str) -> String) -> Value {
    match value {
        Value::String(text) => Value::String(f(text)),
        Value::Array(items) => Value::Array(items.iter().map(|item| map_strings(item, f)).collect()),
        Value::Object(map) => {
            Value::Object(map.iter().map(|(key, item)| (key.clone(), map_strings(item, f))).collect())
        }
        other => other.clone(),
    }
}

fn post_tool(call: &Call, redactor: &Redactor, decided: &mut Decided) -> Answer {
    let Some(output) = &call.output else { return Answer::default() };
    let leaked = redactor.find(output).len();
    let has_tokens = output.contains("<SECRET_") || output.contains("<EMAIL_") || output.contains("_1>");
    let mut notes = Vec::new();
    if leaked > 0 {
        decided.note = Some(format!("{leaked} value(s) that look like credentials or personal data reached the model"));
        notes.push(
            "Warden: this output held values that look like credentials or personal data. Do not repeat them; refer to \
             them in general terms."
                .to_owned(),
        );
    } else if has_tokens {
        notes.push(
            "Warden: tokens such as <EMAIL_1> stand for real values you are not shown. Use them as they are; they are \
             restored when you write a file."
                .to_owned(),
        );
    }
    Answer { context: (!notes.is_empty()).then(|| notes.join(" ")), ..Answer::default() }
}

fn prompt(policy: &Policy, call: &Call, redactor: &Redactor, decided: &mut Decided) -> Answer {
    let Some(text) = &call.prompt else { return Answer::default() };
    decided.prompt_chars = text.chars().count();
    let verdict = judge_text(policy, "the prompt", text, Category::SecretPrompt);
    if verdict.decision != Decision::Allow {
        let reason = format!(
            "{} Remove the credential and say what it is for; the agent never needs its value.",
            verdict.reason
        );
        decided.verdict = Some(verdict);
        return Answer { block_prompt: true, reason, ..Answer::default() };
    }
    let personal: Vec<_> = redactor.find(text).into_iter().filter(|hit| hit.kind != Kind::Secret).collect();
    decided.verdict = Some(verdict);
    if personal.is_empty() || policy.redact.prompts == PromptMode::Off {
        return Answer::default();
    }
    let reason = format!("the prompt holds {} personal data value(s); Warden keeps them off the model", personal.len());
    match policy.redact.prompts {
        PromptMode::Block => Answer { block_prompt: true, reason, ..Answer::default() },
        _ => Answer { context: Some(format!("Warden: {reason}. Do not repeat them.")), ..Answer::default() },
    }
}

/// Append the decision to the audit log. A failure to write is reported and never stops the hook.
fn log(
    policy: &Policy,
    ctx: &Context,
    setting: &Setting,
    call: &Call,
    redactor: &Redactor,
    decided: &Decided,
    answer: &Answer,
) {
    let mut scratch = Session::in_memory();
    let subject = match (&call.tool, &call.prompt) {
        (Some(Tool::Bash { command }), _) => command.clone(),
        (Some(Tool::Read { path } | Tool::Write { path, .. } | Tool::Edit { path, .. }), _) => path.clone(),
        (Some(Tool::Web { url }), _) => url.clone(),
        (_, Some(_)) => format!("prompt({} chars)", decided.prompt_chars),
        _ => call.tool_name.clone(),
    };
    let (summary, _) = redactor.redact(&mut scratch, &subject);
    let verdict = decided.verdict.as_ref();
    let decision = match (answer.block_prompt, verdict) {
        (true, _) => "deny".to_owned(),
        (false, Some(v)) => v.decision.to_string(),
        (false, None) => "allow".to_owned(),
    };
    let intended = verdict.filter(|v| v.intended != v.decision).map(|v| v.intended.to_string()).unwrap_or_default();
    let entry = Entry {
        agent: call.agent.clone(),
        session: call.session.clone(),
        event: call.event.name().to_owned(),
        tool: call.tool_name.clone(),
        kind: kind_of(call.tool.as_ref()).to_owned(),
        cwd: ctx.cwd.display().to_string(),
        input_sha256: digest_of(&subject),
        summary: shorten(&summary),
        categories: verdict
            .map(|v| v.findings.iter().map(|f| f.category.name().to_owned()).collect())
            .unwrap_or_default(),
        decision,
        intended,
        reason: shorten(&decided.note.clone().or_else(|| verdict.map(|v| v.reason.clone())).unwrap_or_default()),
        policy: policy.sources.join(","),
        mode: if policy.mode == Mode::Enforce { "enforce" } else { "audit" }.to_owned(),
        redactions: decided.redactions.iter().map(|(kind, count)| (kind.to_owned(), count)).collect(),
    };
    let dir = std::env::var_os("WARDEN_STATE_DIR")
        .map_or_else(|| PathBuf::from(ctx.expand(&policy.audit.dir)), |base| Path::new(&base).join("audit"));
    if let Err(error) = AuditLog::new(dir).append(&entry) {
        crate::spool::note(&format!("cannot write the audit log: {error}"));
    }
    let _ = setting;
}

fn kind_of(tool: Option<&Tool>) -> &'static str {
    match tool {
        Some(Tool::Bash { .. }) => "bash",
        Some(Tool::Read { .. }) => "read",
        Some(Tool::Write { .. } | Tool::Edit { .. } | Tool::Patch { .. }) => "write",
        Some(Tool::Web { .. }) => "web",
        Some(Tool::Mcp { .. }) => "mcp",
        Some(Tool::Agent) => "agent",
        None => "other",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_word_is_quoted_for_a_shell() {
        assert_eq!(quote("ls -la"), "'ls -la'");
        assert_eq!(quote("echo 'hi'"), "'echo '\\''hi'\\'''");
    }
}
