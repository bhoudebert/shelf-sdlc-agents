//! Warden: a policy engine for coding agents. See `docs/adr/0014-guard-agents-with-warden-a-policy-engine-in-rust.md`.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

mod hook;
mod load;
mod report;
mod run;

use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use warden_engine::{Context, corpus, judge_command};
use warden_policy::Profile;

use crate::load::Sources;

/// The version of this build, as `warden version` prints it.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Parser)]
#[command(name = "warden", about = "A policy engine for coding agents", disable_version_flag = true)]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
}

/// Where the policy comes from, for the commands that judge or show it.
#[derive(clap::Args)]
struct Where {
    /// Start from this preset: observe, guarded, strict, unattended or shelf.
    #[arg(long, value_parser = parse_profile)]
    profile: Option<Profile>,
    /// Also read the global file and the repository's `.warden/policy.toml`.
    #[arg(long)]
    files: bool,
    /// Read this file as the global policy.
    #[arg(long)]
    policy: Option<PathBuf>,
    /// The working directory commands are judged from.
    #[arg(long)]
    cwd: Option<PathBuf>,
}

#[derive(Subcommand)]
enum Command {
    /// Print the version.
    #[command(visible_aliases = ["--version", "-V"])]
    Version,
    /// Show how one command line is judged, and why.
    Explain {
        /// The command line.
        command: String,
        #[command(flatten)]
        from: Where,
    },
    /// Run a corpus of command lines against a policy and report what differs from what it expects.
    Test {
        /// A corpus file.
        corpus: PathBuf,
        #[command(flatten)]
        from: Where,
    },
    /// Print the merged policy and the files it came from.
    Policy {
        #[command(flatten)]
        from: Where,
    },
    /// Show what the audit log holds: the interventions and the redactions.
    Status {
        /// Show every record, not only the interventions.
        #[arg(long)]
        all: bool,
        /// How many records to show.
        #[arg(short, default_value_t = 20)]
        n: usize,
        /// Only this session.
        #[arg(long)]
        session: Option<String>,
        /// The log directory, in place of the policy's.
        #[arg(long)]
        dir: Option<PathBuf>,
        #[command(flatten)]
        from: Where,
    },
    /// Run a command and redact what it prints (the agents' hooks call this).
    Run {
        /// The session whose tokens to use, so the same value gets the same token.
        #[arg(long, default_value = "default")]
        session: String,
        /// The command, run through `bash -c`.
        #[arg(last = true, required = true)]
        command: Vec<String>,
        #[command(flatten)]
        from: Where,
    },
    /// What an agent calls before it uses a tool: reads its payload on standard input, answers on standard output.
    #[command(hide = true)]
    Hook {
        /// The agent: `claude`.
        agent: String,
        /// The event: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionStart`, `Stop`.
        event: String,
    },
    /// Work with the audit log.
    Audit {
        #[command(subcommand)]
        action: AuditAction,
    },
}

#[derive(Subcommand)]
enum AuditAction {
    /// Walk the hash chain and name the first record that was changed or removed.
    Verify {
        /// The log directory, in place of the policy's.
        #[arg(long)]
        dir: Option<PathBuf>,
        #[command(flatten)]
        from: Where,
    },
}

fn parse_profile(text: &str) -> Result<Profile, String> {
    match text {
        "observe" => Ok(Profile::Observe),
        "guarded" => Ok(Profile::Guarded),
        "strict" => Ok(Profile::Strict),
        "unattended" => Ok(Profile::Unattended),
        "shelf" => Ok(Profile::Shelf),
        other => Err(format!("unknown profile {other:?}: observe, guarded, strict, unattended or shelf")),
    }
}

fn context(from: &Where) -> Context {
    let mut ctx = Context::from_env();
    if let Some(cwd) = &from.cwd {
        ctx.cwd.clone_from(cwd);
    }
    ctx
}

fn sources(from: &Where, ctx: &Context, default_profile: Option<Profile>) -> Sources {
    Sources {
        profile: from.profile.or(default_profile),
        files: from.files || from.policy.is_some(),
        global: from.policy.clone(),
        cwd: ctx.cwd.clone(),
        home: ctx.home.clone(),
    }
}

/// Where Warden keeps its state: `$WARDEN_STATE_DIR`, or `~/.local/share/warden`.
fn state_dir(ctx: &Context) -> PathBuf {
    std::env::var_os("WARDEN_STATE_DIR").map_or_else(|| ctx.home.join(".local/share/warden"), PathBuf::from)
}

/// The audit log's directory: the flag, `$WARDEN_STATE_DIR/audit`, or what the policy says.
fn audit_log(from: &Where, dir: Option<PathBuf>) -> Result<warden_audit::AuditLog, String> {
    let ctx = context(from);
    let policy = load::policy(&Sources { files: true, ..sources(from, &ctx, None) })?;
    Ok(warden_audit::AuditLog::new(dir.unwrap_or_else(|| audit_dir(&ctx, &policy))))
}

/// `$WARDEN_STATE_DIR/audit` when that is set, or the directory the policy names.
fn audit_dir(ctx: &Context, policy: &warden_policy::Policy) -> PathBuf {
    std::env::var_os("WARDEN_STATE_DIR")
        .map_or_else(|| PathBuf::from(ctx.expand(&policy.audit.dir)), |base| PathBuf::from(base).join("audit"))
}

/// The audit record of a command whose output was redacted: counts only, and the command line with its own secrets
/// replaced.
fn record_run(
    policy: &warden_policy::Policy,
    redactor: &warden_redact::Redactor,
    ctx: &Context,
    session: &str,
    line: &str,
    counts: &warden_redact::Counts,
) {
    let mut scratch = warden_redact::Session::in_memory();
    let (summary, _) = redactor.redact(&mut scratch, line);
    let entry = warden_audit::Entry {
        agent: "run".to_owned(),
        session: session.to_owned(),
        event: "Run".to_owned(),
        tool: "Bash".to_owned(),
        kind: "bash".to_owned(),
        cwd: ctx.cwd.display().to_string(),
        input_sha256: warden_audit::digest_of(line),
        summary: warden_audit::shorten(&summary),
        decision: "redacted".to_owned(),
        reason: "the output of the command was redacted".to_owned(),
        policy: policy.sources.join(","),
        mode: if policy.mode == warden_policy::Mode::Enforce { "enforce" } else { "audit" }.to_owned(),
        redactions: counts.iter().map(|(kind, count)| (kind.to_owned(), count)).collect(),
        ..warden_audit::Entry::default()
    };
    let log = warden_audit::AuditLog::new(audit_dir(ctx, policy));
    if let Err(error) = log.append(&entry) {
        eprintln!("warden: cannot write the audit log: {error}");
    }
}

fn run(cli: Cli) -> Result<ExitCode, String> {
    match cli.command {
        None => {
            println!("{}", <Cli as clap::CommandFactory>::command().render_help());
            Ok(ExitCode::SUCCESS)
        }
        Some(Command::Version) => {
            println!("warden {VERSION}");
            Ok(ExitCode::SUCCESS)
        }
        Some(Command::Explain { command, from }) => {
            let ctx = context(&from);
            let policy = load::policy(&sources(&from, &ctx, None))?;
            let verdict = judge_command(&policy, &ctx, &command);
            print!("{}", report::explain(&policy, &verdict));
            Ok(ExitCode::SUCCESS)
        }
        Some(Command::Policy { from }) => {
            let ctx = context(&from);
            let policy = load::policy(&sources(&from, &ctx, None))?;
            print!("{}", report::policy(&policy));
            Ok(ExitCode::SUCCESS)
        }
        Some(Command::Status { all, n, session, dir, from }) => {
            let log = audit_log(&from, dir)?;
            let records = log
                .read(&warden_audit::Filter { session, last: None })
                .map_err(|error| format!("{}: {error}", log.dir().display()))?;
            print!("{}", report::status(&records, all, n));
            Ok(ExitCode::SUCCESS)
        }
        Some(Command::Hook { agent, event }) => {
            let mut stdin = String::new();
            std::io::Read::read_to_string(&mut std::io::stdin(), &mut stdin).map_err(|error| error.to_string())?;
            let ctx = Context::from_env();
            let setting = hook::Setting {
                state_dir: state_dir(&ctx),
                exe: std::env::current_exe().unwrap_or_else(|_| PathBuf::from("warden")),
                profile: std::env::var("WARDEN_PROFILE").ok().and_then(|name| parse_profile(&name).ok()),
                home: ctx.home,
                cwd: ctx.cwd,
            };
            let rendered = hook::run(&agent, &event, &stdin, &setting);
            print!("{}", rendered.stdout);
            eprint!("{}", rendered.stderr);
            Ok(ExitCode::from(u8::try_from(rendered.code).unwrap_or(2)))
        }
        Some(Command::Run { session, command, from }) => {
            let ctx = context(&from);
            let policy = load::policy(&Sources { files: true, ..sources(&from, &ctx, None) })?;
            let redactor = run::redactor_for(&policy)?;
            let path = run::session_path(&state_dir(&ctx), &session);
            let tokens = warden_redact::Session::open(&path).unwrap_or_else(|error| {
                eprintln!("warden: starting the session over: {error}");
                warden_redact::Session::default()
            });
            let line = command.join(" ");
            let (outcome, tokens) = run::run(&policy, &redactor, tokens, &line);
            if let Err(error) = tokens.save() {
                eprintln!("warden: cannot save the session tokens: {error}");
            }
            if !outcome.counts.is_empty() && policy.audit.enabled {
                record_run(&policy, &redactor, &ctx, &session, &line, &outcome.counts);
            }
            Ok(ExitCode::from(u8::try_from(outcome.code.clamp(0, 255)).unwrap_or(1)))
        }
        Some(Command::Audit { action: AuditAction::Verify { dir, from } }) => {
            let log = audit_log(&from, dir)?;
            let verification = log.verify().map_err(|error| format!("{}: {error}", log.dir().display()))?;
            print!("{}", report::verification(&verification));
            Ok(if verification.problem.is_none() { ExitCode::SUCCESS } else { ExitCode::FAILURE })
        }
        Some(Command::Test { corpus: path, from }) => {
            let text = std::fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
            let file = corpus::Corpus::parse(&text).map_err(|error| format!("{}: {error}", path.display()))?;
            let ctx = Context { home: "/home/dev".into(), cwd: "/work/app".into() };
            let policy = load::policy(&sources(&from, &ctx, file.profile))?;
            let mismatches = corpus::run(&policy, &ctx, &file);
            print!("{}", report::test(file.cases.len(), &mismatches));
            Ok(if mismatches.is_empty() { ExitCode::SUCCESS } else { ExitCode::FAILURE })
        }
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    // `warden --version` and `warden -V` are the same as `warden version`.
    let args = match args.get(1).map(String::as_str) {
        Some("--version" | "-V") => vec![args[0].clone(), "version".to_owned()],
        _ => args,
    };
    match Cli::try_parse_from(args) {
        Ok(cli) => match run(cli) {
            Ok(code) => code,
            Err(message) => {
                eprintln!("warden: {message}");
                ExitCode::from(2)
            }
        },
        Err(error) => {
            let code = if error.use_stderr() { 2 } else { 0 };
            let _ = error.print();
            ExitCode::from(code)
        }
    }
}
