//! `warden init`, `warden uninstall` and `warden doctor`: wire Warden into an agent, take it out, check it is there.
//!
//! For Claude Code the hooks go into a `settings.json`: the user's, the repository's, or the managed settings an
//! organisation controls. Warden's entries are put first, so that other hooks see what Warden let through, and any
//! earlier Warden entry is replaced, so running `init` again is safe.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value, json};
use warden_policy::{OnError, Policy, Profile};

/// The hook events Warden listens to.
const EVENTS: [&str; 5] = ["PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart", "Stop"];

/// The events that name a tool, and so take a matcher.
const TOOL_EVENTS: [&str; 2] = ["PreToolUse", "PostToolUse"];

/// The companion skill, written next to the settings.
const SKILL: &str = include_str!("../skill/SKILL.md");

/// The OpenCode plugin that calls Warden.
const OPENCODE_PLUGIN: &str = include_str!("../skill/opencode-plugin.js");

/// The agents Warden can be wired into.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Agent {
    /// Claude Code: hooks in a `settings.json`.
    Claude,
    /// OpenCode: a plugin file.
    OpenCode,
    /// GitHub Copilot: a hooks file in `.github/hooks`.
    Copilot,
    /// Codex CLI: a snippet to put in `config.toml`.
    Codex,
}

/// Where Warden is wired.
#[derive(Debug, Clone)]
pub enum Scope {
    /// `~/.claude/settings.json`: every repository of this user.
    Global,
    /// `<repository>/.claude/settings.json`: shared with the team through the repository.
    Repo,
    /// A managed settings file an organisation controls, such as `/etc/claude-code/managed-settings.json`.
    Managed(PathBuf),
}

/// What `init` was asked.
#[derive(Debug, Clone)]
pub struct Init {
    /// Where to wire.
    pub scope: Scope,
    /// A profile to write into a new policy file.
    pub profile: Option<Profile>,
    /// Say what would change and change nothing.
    pub dry_run: bool,
}

/// Where things are.
#[derive(Debug, Clone)]
pub struct Places {
    /// The home directory.
    pub home: PathBuf,
    /// The working directory.
    pub cwd: PathBuf,
    /// This binary.
    pub exe: PathBuf,
}

impl Places {
    /// The root of the repository the working directory is in, or the working directory.
    #[must_use]
    pub fn repo_root(&self) -> PathBuf {
        self.cwd.ancestors().find(|dir| dir.join(".git").exists()).unwrap_or(&self.cwd).to_path_buf()
    }

    fn settings(&self, scope: &Scope) -> PathBuf {
        match scope {
            Scope::Global => self.home.join(".claude/settings.json"),
            Scope::Repo => self.repo_root().join(".claude/settings.json"),
            Scope::Managed(path) => path.clone(),
        }
    }

    fn skill(&self, scope: &Scope) -> Option<PathBuf> {
        match scope {
            Scope::Global => Some(self.home.join(".claude/skills/warden/SKILL.md")),
            Scope::Repo => Some(self.repo_root().join(".claude/skills/warden/SKILL.md")),
            Scope::Managed(_) => None,
        }
    }

    fn policy(&self, scope: &Scope) -> Option<PathBuf> {
        match scope {
            Scope::Global => Some(self.home.join(".config/warden/policy.toml")),
            Scope::Repo => Some(self.repo_root().join(".warden/policy.toml")),
            Scope::Managed(_) => None,
        }
    }

    /// How a hook calls Warden: by name in a repository (a teammate only needs it on their `PATH`), by path elsewhere.
    fn command(&self, scope: &Scope) -> String {
        match scope {
            Scope::Repo => "warden".to_owned(),
            Scope::Global | Scope::Managed(_) => {
                let path = self.exe.display().to_string();
                if path.contains(' ') { format!("\"{path}\"") } else { path }
            }
        }
    }
}

fn is_ours(entry: &Value) -> bool {
    entry.get("hooks").and_then(Value::as_array).is_some_and(|hooks| {
        hooks.iter().any(|h| h.get("command").and_then(Value::as_str).is_some_and(|c| c.contains(" hook claude ")))
    })
}

fn read_settings(path: &Path) -> Result<Value, String> {
    match fs::read_to_string(path) {
        Ok(text) if text.trim().is_empty() => Ok(json!({})),
        Ok(text) => serde_json::from_str(&text).map_err(|error| format!("{}: not valid JSON: {error}", path.display())),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(json!({})),
        Err(error) => Err(format!("{}: {error}", path.display())),
    }
}

fn write_file(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("{}: {error}", parent.display()))?;
    }
    let temp = path.with_extension("warden-tmp");
    fs::write(&temp, text).map_err(|error| format!("{}: {error}", temp.display()))?;
    fs::rename(&temp, path).map_err(|error| format!("{}: {error}", path.display()))
}

fn hook_entry(base: &str, event: &str, closed: bool) -> Value {
    let mut hook = json!({ "type": "command", "command": format!("{base} hook claude {event}"), "timeout": 20 });
    if closed && let Some(map) = hook.as_object_mut() {
        map.insert("onFailure".to_owned(), json!("block"));
    }
    let mut entry = Map::new();
    if TOOL_EVENTS.contains(&event) {
        entry.insert("matcher".to_owned(), json!("*"));
    }
    entry.insert("hooks".to_owned(), json!([hook]));
    Value::Object(entry)
}

/// Put Warden's entries first in each event of `settings`, replacing earlier ones.
fn wire(settings: &mut Value, base: &str, closed: bool) -> Result<(), String> {
    let root = settings.as_object_mut().ok_or("the settings file is not a JSON object")?;
    let hooks = root.entry("hooks").or_insert_with(|| json!({}));
    let hooks = hooks.as_object_mut().ok_or("\"hooks\" in the settings file is not an object")?;
    for event in EVENTS {
        let list = hooks.entry(event).or_insert_with(|| json!([]));
        let list = list.as_array_mut().ok_or_else(|| format!("\"hooks.{event}\" is not a list"))?;
        list.retain(|entry| !is_ours(entry));
        list.insert(0, hook_entry(base, event, closed));
    }
    Ok(())
}

/// Take Warden's entries out of `settings`; returns how many were removed.
fn unwire(settings: &mut Value) -> usize {
    let mut removed = 0;
    if let Some(hooks) = settings.get_mut("hooks").and_then(Value::as_object_mut) {
        for list in hooks.values_mut().filter_map(Value::as_array_mut) {
            let before = list.len();
            list.retain(|entry| !is_ours(entry));
            removed += before - list.len();
        }
        hooks.retain(|_, list| list.as_array().is_none_or(|l| !l.is_empty()));
    }
    if settings.get("hooks").and_then(Value::as_object).is_some_and(Map::is_empty)
        && let Some(root) = settings.as_object_mut()
    {
        root.remove("hooks");
    }
    removed
}

/// Whether a profile refuses calls it cannot read: then its hooks must block when Warden itself fails.
fn fails_closed(profile: Profile, home: &Path) -> bool {
    let layer = warden_policy::Layer::parse(&format!("profile = \"{}\"", profile.name()));
    layer
        .ok()
        .and_then(|layer| Policy::resolve(&[("profile".to_owned(), layer)], home).ok())
        .is_some_and(|policy| policy.on_error == OnError::Closed)
}

fn scope_name(scope: &Scope) -> String {
    match scope {
        Scope::Global => "global".to_owned(),
        Scope::Repo => "repository".to_owned(),
        Scope::Managed(path) => format!("managed ({})", path.display()),
    }
}

/// Wire Warden into Claude Code. Returns what was done, line by line.
pub fn init(options: &Init, places: &Places) -> Result<Vec<String>, String> {
    let mut report = Vec::new();
    let settings_path = places.settings(&options.scope);
    let mut settings = read_settings(&settings_path)?;
    let profile = options.profile.unwrap_or(Profile::Guarded);
    let closed = fails_closed(profile, &places.home);
    wire(&mut settings, &places.command(&options.scope), closed)?;
    let text = serde_json::to_string_pretty(&settings).map_err(|error| error.to_string())? + "\n";
    let verb = if options.dry_run { "would wire" } else { "wired" };
    report.push(format!("{verb} Claude Code hooks ({}) in {}", scope_name(&options.scope), settings_path.display()));
    if closed {
        report.push("  the hooks block when Warden itself fails (this profile fails closed)".to_owned());
    }
    if !options.dry_run {
        let backup = settings_path.with_extension("json.warden-backup");
        if settings_path.is_file() && !backup.exists() {
            fs::copy(&settings_path, &backup).map_err(|error| format!("{}: {error}", backup.display()))?;
            report.push(format!("  the original is kept as {}", backup.display()));
        }
        write_file(&settings_path, &text)?;
    }
    if let Some(skill) = places.skill(&options.scope) {
        report.push(format!(
            "{} the companion skill {}",
            if options.dry_run { "would write" } else { "wrote" },
            skill.display()
        ));
        if !options.dry_run {
            write_file(&skill, SKILL)?;
        }
    }
    if let (Some(policy), Some(profile)) = (places.policy(&options.scope), options.profile) {
        if policy.exists() {
            report.push(format!("the policy {} already exists and was left as it is", policy.display()));
        } else {
            report.push(format!(
                "{} the policy {} with the profile {}",
                if options.dry_run { "would write" } else { "wrote" },
                policy.display(),
                profile.name()
            ));
            if !options.dry_run {
                write_file(&policy, &format!("version = 1\nprofile = \"{}\"\n", profile.name()))?;
            }
        }
    }
    Ok(report)
}

/// Take Warden out of Claude Code. With `purge`, also delete the policy, the sessions and the audit log.
pub fn uninstall(scope: &Scope, purge: bool, state_dir: &Path, places: &Places) -> Result<Vec<String>, String> {
    let mut report = Vec::new();
    let settings_path = places.settings(scope);
    if settings_path.is_file() {
        let mut settings = read_settings(&settings_path)?;
        let removed = unwire(&mut settings);
        let text = serde_json::to_string_pretty(&settings).map_err(|error| error.to_string())? + "\n";
        write_file(&settings_path, &text)?;
        report.push(format!("removed {removed} Warden hook entries from {}", settings_path.display()));
    } else {
        report.push(format!("{} does not exist: nothing to unwire", settings_path.display()));
    }
    if let Some(skill) = places.skill(scope)
        && let Some(dir) = skill.parent().filter(|d| d.exists())
    {
        fs::remove_dir_all(dir).map_err(|error| format!("{}: {error}", dir.display()))?;
        report.push(format!("removed {}", dir.display()));
    }
    if purge {
        if let Some(policy) = places.policy(scope).filter(|p| p.exists()) {
            fs::remove_file(&policy).map_err(|error| format!("{}: {error}", policy.display()))?;
            report.push(format!("removed {}", policy.display()));
        }
        if matches!(scope, Scope::Global) && state_dir.exists() {
            fs::remove_dir_all(state_dir).map_err(|error| format!("{}: {error}", state_dir.display()))?;
            report.push(format!("removed {} (sessions and audit log)", state_dir.display()));
        }
    }
    Ok(report)
}

/// One line of the doctor's report.
pub struct Check {
    /// `ok`, `warn` or `FAIL`.
    pub level: &'static str,
    /// What was checked and what was found.
    pub text: String,
}

fn check(level: &'static str, text: impl Into<String>) -> Check {
    Check { level, text: text.into() }
}

/// What is wired in a settings file: the events Warden has an entry for, and the commands that do not exist.
fn wired(settings: &Value) -> (Vec<&'static str>, Vec<String>) {
    let mut present = Vec::new();
    let mut dead = Vec::new();
    for event in EVENTS {
        let Some(list) = settings.pointer(&format!("/hooks/{event}")).and_then(Value::as_array) else { continue };
        let Some(entry) = list.iter().find(|entry| is_ours(entry)) else { continue };
        present.push(event);
        let command = entry.pointer("/hooks/0/command").and_then(Value::as_str).unwrap_or_default();
        let program = command.split(" hook claude ").next().unwrap_or_default().trim_matches('"');
        if program.starts_with('/') && !Path::new(program).exists() && !dead.contains(&program.to_owned()) {
            dead.push(program.to_owned());
        }
    }
    (present, dead)
}

/// Check that Warden is wired and healthy.
pub fn doctor(
    policy: &Result<Policy, String>,
    audit_dir: &Path,
    state_dir: &Path,
    places: &Places,
    extra_managed: Option<&Path>,
) -> Vec<Check> {
    let mut checks = Vec::new();
    checks.push(check("ok", format!("warden {} at {}", crate::VERSION, places.exe.display())));
    let on_path = std::env::var_os("PATH")
        .is_some_and(|paths| std::env::split_paths(&paths).any(|dir| dir.join("warden").is_file()));
    checks.push(if on_path {
        check("ok", "warden is on the PATH")
    } else {
        check("warn", "warden is not on the PATH: a repository's hooks call it by name, so teammates need it there")
    });
    match policy {
        Ok(policy) => {
            checks.push(check(
                "ok",
                format!("the policy loads: profile {} from {}", policy.profile.name(), policy.sources.join(", ")),
            ));
            for warning in &policy.warnings {
                checks.push(check("warn", format!("policy: {warning}")));
            }
        }
        Err(error) => {
            checks.push(check("FAIL", format!("the policy cannot be loaded, so every call is denied: {error}")));
        }
    }
    let log = warden_audit::AuditLog::new(audit_dir);
    match log.verify() {
        Ok(v) if v.problem.is_none() => checks
            .push(check("ok", format!("the audit log at {} is intact ({} records)", audit_dir.display(), v.records))),
        Ok(v) => {
            let p = v.problem.map(|p| format!("{} line {}: {}", p.file, p.line, p.what)).unwrap_or_default();
            checks.push(check("FAIL", format!("the audit chain is broken: {p}")));
        }
        Err(error) => checks.push(check("FAIL", format!("the audit log cannot be read: {error}"))),
    }
    let writable = fs::create_dir_all(state_dir).is_ok() && fs::write(state_dir.join(".doctor"), "").is_ok();
    let _ = fs::remove_file(state_dir.join(".doctor"));
    checks.push(if writable {
        check("ok", format!("the state directory {} is writable", state_dir.display()))
    } else {
        check(
            "FAIL",
            format!("the state directory {} is not writable: sessions and the log cannot be kept", state_dir.display()),
        )
    });
    let mut any = false;
    let mut files: Vec<(String, PathBuf)> = vec![
        ("global".to_owned(), places.settings(&Scope::Global)),
        ("repository".to_owned(), places.settings(&Scope::Repo)),
        ("managed".to_owned(), PathBuf::from("/etc/claude-code/managed-settings.json")),
    ];
    if let Some(extra) = extra_managed {
        files.push(("managed".to_owned(), extra.to_path_buf()));
    }
    for (name, path) in files {
        let Ok(settings) = read_settings(&path) else {
            if path.is_file() {
                checks.push(check("FAIL", format!("{name} settings {} cannot be read as JSON", path.display())));
            }
            continue;
        };
        let (present, dead) = wired(&settings);
        if present.is_empty() {
            continue;
        }
        any = true;
        let missing: Vec<&str> = EVENTS.iter().copied().filter(|e| !present.contains(e)).collect();
        if missing.is_empty() && dead.is_empty() {
            checks.push(check("ok", format!("Claude Code is wired in the {name} settings ({})", path.display())));
        } else {
            if !missing.is_empty() {
                checks.push(check(
                    "warn",
                    format!("{name} settings lack hooks for {}: run warden init", missing.join(", ")),
                ));
            }
            for program in dead {
                checks.push(check("FAIL", format!("{name} settings call {program}, which does not exist")));
            }
        }
    }
    if !any {
        checks.push(check("warn", "Claude Code is not wired in any settings file: run warden init"));
    }
    checks
}

/// The Copilot hooks file: every event calls `warden hook copilot <event>`.
fn copilot_hooks(base: &str) -> String {
    let events = ["preToolUse", "postToolUse", "userPromptSubmitted", "sessionStart", "agentStop"];
    let hooks: Map<String, Value> = events
        .iter()
        .map(|event| {
            (
                (*event).to_owned(),
                json!([{ "type": "command", "bash": format!("{base} hook copilot {event}"), "timeoutSec": 20 }]),
            )
        })
        .collect();
    serde_json::to_string_pretty(&json!({ "version": 1, "hooks": hooks })).unwrap_or_default() + "\n"
}

/// The Codex `config.toml` snippet: every event calls `warden hook codex <event>`.
fn codex_snippet(base: &str) -> String {
    use std::fmt::Write as _;
    let mut out =
        String::from("# Add this to ~/.codex/config.toml, then review and trust the hooks with /hooks in Codex.\n");
    for event in EVENTS {
        let _ = write!(out, "\n[[hooks.{event}]]\n");
        if TOOL_EVENTS.contains(&event) {
            out.push_str("matcher = \".*\"\n");
        }
        let _ = write!(
            out,
            "\n[[hooks.{event}.hooks]]\ntype = \"command\"\ncommand = \"{base} hook codex {event}\"\ntimeout = 20\n"
        );
    }
    out
}

/// Wire Warden into an agent other than Claude Code. Returns what was done, line by line.
pub fn init_other(agent: Agent, scope: &Scope, dry_run: bool, places: &Places) -> Result<Vec<String>, String> {
    let base = places.command(scope);
    let verb = if dry_run { "would write" } else { "wrote" };
    match agent {
        Agent::OpenCode => {
            let path = match scope {
                Scope::Global => places.home.join(".config/opencode/plugins/warden.js"),
                Scope::Repo => places.repo_root().join(".opencode/plugins/warden.js"),
                Scope::Managed(_) => {
                    return Err("OpenCode's managed configuration is not wired by warden init".to_owned());
                }
            };
            if !dry_run {
                write_file(&path, OPENCODE_PLUGIN)?;
            }
            Ok(vec![
                format!("{verb} the OpenCode plugin {}", path.display()),
                "  it calls `warden hook opencode` for every tool call, and refuses the call if warden cannot be run".to_owned(),
                "  the plugin uses OpenCode's v1 plugin API; calls made through OpenCode's batch tool skip plugin hooks".to_owned(),
            ])
        }
        Agent::Copilot => {
            let path = match scope {
                Scope::Global => places.home.join(".copilot/hooks/warden.json"),
                Scope::Repo => places.repo_root().join(".github/hooks/warden.json"),
                Scope::Managed(_) => {
                    return Err(
                        "Copilot's policy hooks are installed by an administrator, not by warden init".to_owned()
                    );
                }
            };
            if !dry_run {
                write_file(&path, &copilot_hooks(&base))?;
            }
            Ok(vec![
                format!("{verb} the Copilot hooks {}", path.display()),
                "  Copilot cannot block a prompt, and an ask is a deny in its cloud agent; Warden redacts results after the tool ran".to_owned(),
            ])
        }
        Agent::Codex => Ok(codex_snippet(&base).lines().map(str::to_owned).collect()),
        Agent::Claude => Err("Claude Code is wired by init itself".to_owned()),
    }
}

/// Take Warden out of an agent other than Claude Code.
pub fn uninstall_other(agent: Agent, scope: &Scope, places: &Places) -> Result<Vec<String>, String> {
    let path = match (agent, scope) {
        (Agent::OpenCode, Scope::Global) => places.home.join(".config/opencode/plugins/warden.js"),
        (Agent::OpenCode, Scope::Repo) => places.repo_root().join(".opencode/plugins/warden.js"),
        (Agent::Copilot, Scope::Global) => places.home.join(".copilot/hooks/warden.json"),
        (Agent::Copilot, Scope::Repo) => places.repo_root().join(".github/hooks/warden.json"),
        _ => return Ok(vec!["nothing to remove: this agent's configuration is not written by warden init".to_owned()]),
    };
    if path.is_file() {
        fs::remove_file(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        Ok(vec![format!("removed {}", path.display())])
    } else {
        Ok(vec![format!("{} does not exist: nothing to remove", path.display())])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wiring_puts_warden_first_replaces_its_own_entries_and_keeps_the_rest() {
        let mut settings = json!({
            "model": "opus",
            "hooks": { "PreToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "rtk hook claude" }] }] }
        });
        wire(&mut settings, "warden", false).expect("wires");
        wire(&mut settings, "warden", false).expect("wires again");
        let pre = settings["hooks"]["PreToolUse"].as_array().expect("list");
        assert_eq!(pre.len(), 2, "one of ours, one of theirs: {pre:?}");
        assert!(is_ours(&pre[0]) && !is_ours(&pre[1]));
        assert_eq!(settings["model"], "opus");
        for event in EVENTS {
            assert!(settings["hooks"][event].as_array().is_some_and(|l| l.iter().any(is_ours)), "{event}");
        }
        assert!(settings["hooks"]["SessionStart"][0].get("matcher").is_none());
        assert_eq!(settings["hooks"]["PreToolUse"][0]["matcher"], "*");
    }

    #[test]
    fn a_fail_closed_profile_makes_the_hooks_block_when_warden_fails() {
        let mut settings = json!({});
        wire(&mut settings, "/usr/bin/warden", true).expect("wires");
        assert_eq!(settings["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"], "block");
        assert_eq!(settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "/usr/bin/warden hook claude PreToolUse");
    }

    #[test]
    fn unwiring_removes_only_warden_and_tidies_empty_lists() {
        let mut settings = json!({ "hooks": { "PreToolUse": [{ "hooks": [{ "command": "other" }] }] } });
        wire(&mut settings, "warden", false).expect("wires");
        assert_eq!(unwire(&mut settings), 5);
        assert_eq!(settings, json!({ "hooks": { "PreToolUse": [{ "hooks": [{ "command": "other" }] }] } }));
        let mut only_ours = json!({});
        wire(&mut only_ours, "warden", false).expect("wires");
        unwire(&mut only_ours);
        assert_eq!(only_ours, json!({}));
    }

    #[test]
    fn a_settings_file_that_is_not_an_object_is_refused() {
        assert!(wire(&mut json!([]), "warden", false).is_err());
        assert!(wire(&mut json!({ "hooks": 3 }), "warden", false).is_err());
    }

    #[test]
    fn only_the_profiles_that_fail_closed_make_the_hooks_block() {
        let home = Path::new("/home/dev");
        assert!(!fails_closed(Profile::Guarded, home) && !fails_closed(Profile::Observe, home));
        assert!(
            fails_closed(Profile::Strict, home)
                && fails_closed(Profile::Unattended, home)
                && fails_closed(Profile::Shelf, home)
        );
    }

    #[test]
    fn a_missing_program_is_found() {
        let mut settings = json!({});
        wire(&mut settings, "/nonexistent/warden", false).expect("wires");
        let (present, dead) = wired(&settings);
        assert_eq!(present.len(), 5);
        assert_eq!(dead, ["/nonexistent/warden"]);
    }
}
