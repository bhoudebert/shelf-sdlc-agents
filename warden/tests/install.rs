#![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use serde_json::Value;

fn temp_dir(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("warden-install-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("temp dir");
    dir
}

struct Machine {
    home: PathBuf,
    repo: PathBuf,
    state: PathBuf,
}

impl Machine {
    fn new(name: &str) -> Self {
        let root = temp_dir(name);
        let (home, repo, state) = (root.join("home"), root.join("repo"), root.join("state"));
        std::fs::create_dir_all(home.join(".claude")).expect("home");
        std::fs::create_dir_all(repo.join(".git")).expect("repo");
        Self { home, repo, state }
    }

    fn warden(&self, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_warden"))
            .args(args)
            .current_dir(&self.repo)
            .env("HOME", &self.home)
            .env("WARDEN_STATE_DIR", &self.state)
            .env_remove("WARDEN_POLICY")
            .env_remove("WARDEN_PROFILE")
            .output()
            .expect("runs")
    }
}

fn out(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned() + &String::from_utf8_lossy(&output.stderr)
}

fn json(path: &Path) -> Value {
    serde_json::from_str(&std::fs::read_to_string(path).expect("file")).expect("json")
}

#[test]
fn init_wires_the_users_settings_keeps_what_is_there_and_backs_the_original_up() {
    let m = Machine::new("global");
    let settings = m.home.join(".claude/settings.json");
    std::fs::write(&settings, r#"{ "model": "opus", "hooks": { "PreToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "rtk hook" }] }] } }"#)
        .expect("settings");
    let output = m.warden(&["init", "--global", "--profile", "guarded"]);
    assert!(output.status.success(), "{}", out(&output));
    let written = json(&settings);
    assert_eq!(written["model"], "opus");
    let pre = written["hooks"]["PreToolUse"].as_array().expect("list");
    assert_eq!(pre.len(), 2);
    assert!(pre[0]["hooks"][0]["command"].as_str().expect("command").ends_with(" hook claude PreToolUse"));
    assert_eq!(pre[1]["hooks"][0]["command"], "rtk hook", "other hooks stay, after Warden's");
    for event in ["PostToolUse", "UserPromptSubmit", "SessionStart", "Stop"] {
        assert!(written["hooks"][event][0]["hooks"][0]["command"].as_str().expect("command").contains(event));
    }
    assert!(settings.with_extension("json.warden-backup").is_file());
    assert!(m.home.join(".claude/skills/warden/SKILL.md").is_file());
    let policy = std::fs::read_to_string(m.home.join(".config/warden/policy.toml")).expect("policy");
    assert!(policy.contains("profile = \"guarded\""));
    assert!(pre[0]["hooks"][0].get("onFailure").is_none(), "guarded fails open");
}

#[test]
fn init_twice_changes_nothing_and_a_fail_closed_profile_makes_the_hooks_block() {
    let m = Machine::new("twice");
    assert!(m.warden(&["init", "--global", "--profile", "unattended"]).status.success());
    let first = std::fs::read_to_string(m.home.join(".claude/settings.json")).expect("settings");
    let second_run = m.warden(&["init", "--global", "--profile", "unattended"]);
    assert!(out(&second_run).contains("already exists and was left as it is"), "{}", out(&second_run));
    assert_eq!(std::fs::read_to_string(m.home.join(".claude/settings.json")).expect("settings"), first);
    let written: Value = serde_json::from_str(&first).expect("json");
    assert_eq!(written["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"], "block");
    assert_eq!(written["hooks"]["PreToolUse"].as_array().expect("list").len(), 1);
}

#[test]
fn in_a_repository_init_wires_the_repository_by_name_and_the_policy_lives_in_it() {
    let m = Machine::new("repo");
    let output = m.warden(&["init", "--profile", "strict"]);
    assert!(output.status.success(), "{}", out(&output));
    let written = json(&m.repo.join(".claude/settings.json"));
    assert_eq!(written["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "warden hook claude PreToolUse");
    assert!(m.repo.join(".warden/policy.toml").is_file());
    assert!(m.repo.join(".claude/skills/warden/SKILL.md").is_file());
    assert!(!m.home.join(".claude/settings.json").exists(), "the user's settings are untouched");
}

#[test]
fn init_can_wire_a_managed_settings_file_without_a_skill_or_a_policy() {
    let m = Machine::new("managed");
    let managed = m.home.join("managed-settings.json");
    let output = m.warden(&["init", "--managed", &managed.display().to_string(), "--profile", "shelf"]);
    assert!(output.status.success(), "{}", out(&output));
    let written = json(&managed);
    assert_eq!(written["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"], "block");
    assert!(!m.repo.join(".warden").exists());
}

#[test]
fn a_dry_run_says_what_it_would_do_and_does_nothing() {
    let m = Machine::new("dry");
    let output = m.warden(&["init", "--global", "--profile", "guarded", "--dry-run"]);
    let text = out(&output);
    assert!(text.contains("would wire") && text.contains("would write"), "{text}");
    assert!(!m.home.join(".claude/settings.json").exists());
    assert!(!m.home.join(".claude/skills").exists());
}

#[test]
fn a_settings_file_that_is_not_json_is_refused_and_left_alone() {
    let m = Machine::new("bad");
    let settings = m.home.join(".claude/settings.json");
    std::fs::write(&settings, "{ not json").expect("settings");
    let output = m.warden(&["init", "--global"]);
    assert_eq!(output.status.code(), Some(2));
    assert!(out(&output).contains("not valid JSON"), "{}", out(&output));
    assert_eq!(std::fs::read_to_string(&settings).expect("settings"), "{ not json");
}

#[test]
fn uninstall_removes_warden_and_only_warden_and_purge_removes_its_files() {
    let m = Machine::new("uninstall");
    let settings = m.home.join(".claude/settings.json");
    std::fs::write(
        &settings,
        r#"{ "hooks": { "PreToolUse": [{ "hooks": [{ "type": "command", "command": "rtk hook" }] }] } }"#,
    )
    .expect("settings");
    assert!(m.warden(&["init", "--global", "--profile", "guarded"]).status.success());
    std::fs::create_dir_all(m.state.join("sessions")).expect("state");
    let output = m.warden(&["uninstall", "--global"]);
    assert!(output.status.success(), "{}", out(&output));
    let after = json(&settings);
    assert_eq!(after["hooks"]["PreToolUse"].as_array().expect("list").len(), 1);
    assert!(after["hooks"].get("Stop").is_none());
    assert!(!m.home.join(".claude/skills/warden").exists());
    assert!(m.home.join(".config/warden/policy.toml").is_file(), "the policy stays without --purge");
    assert!(m.warden(&["uninstall", "--global", "--purge"]).status.success());
    assert!(!m.home.join(".config/warden/policy.toml").exists());
    assert!(!m.state.exists());
}

#[test]
fn doctor_passes_when_wired_and_names_what_is_wrong_when_not() {
    let m = Machine::new("doctor");
    let before = m.warden(&["doctor"]);
    assert!(out(&before).contains("not wired in any settings file"), "{}", out(&before));
    assert!(m.warden(&["init", "--global", "--profile", "guarded"]).status.success());
    let after = m.warden(&["doctor"]);
    let text = out(&after);
    assert!(after.status.success(), "{text}");
    assert!(text.contains("Claude Code is wired in the global settings"), "{text}");
    assert!(text.contains("the audit log") && text.contains("is intact"), "{text}");

    std::fs::write(m.home.join(".config/warden/policy.toml"), "colour = 1").expect("policy");
    let broken = m.warden(&["doctor"]);
    assert_eq!(broken.status.code(), Some(1));
    assert!(out(&broken).contains("every call is denied"), "{}", out(&broken));
}

#[test]
fn doctor_fails_on_a_hook_that_calls_a_program_that_is_gone_and_on_a_tampered_log() {
    let m = Machine::new("doctor-dead");
    let settings = m.home.join(".claude/settings.json");
    assert!(m.warden(&["init", "--global"]).status.success());
    let text = std::fs::read_to_string(&settings)
        .expect("settings")
        .replace(env!("CARGO_BIN_EXE_warden"), "/nonexistent/warden");
    std::fs::write(&settings, text).expect("settings");
    let dead = m.warden(&["doctor"]);
    assert_eq!(dead.status.code(), Some(1));
    assert!(out(&dead).contains("/nonexistent/warden, which does not exist"), "{}", out(&dead));

    let log = warden_audit::AuditLog::new(m.state.join("audit"));
    for decision in ["allow", "deny"] {
        log.append(&warden_audit::Entry {
            decision: decision.into(),
            mode: "enforce".into(),
            ..warden_audit::Entry::default()
        })
        .expect("append");
    }
    let file = std::fs::read_dir(m.state.join("audit"))
        .expect("dir")
        .filter_map(Result::ok)
        .map(|e| e.path())
        .find(|p| p.extension().is_some_and(|e| e == "jsonl"))
        .expect("log");
    let content = std::fs::read_to_string(&file).expect("log");
    std::fs::write(&file, content.replacen("\"deny\"", "\"allow\"", 1)).expect("tamper");
    assert!(out(&m.warden(&["doctor"])).contains("the audit chain is broken"));
}
