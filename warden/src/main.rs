//! Warden: a policy engine for coding agents. See `docs/adr/0014-guard-agents-with-warden-a-policy-engine-in-rust.md`.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

mod load;
mod report;

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

/// The audit log's directory: the flag, `$WARDEN_STATE_DIR/audit`, or what the policy says.
fn audit_log(from: &Where, dir: Option<PathBuf>) -> Result<warden_audit::AuditLog, String> {
    let ctx = context(from);
    let policy = load::policy(&Sources { files: true, ..sources(from, &ctx, None) })?;
    let dir = dir
        .or_else(|| std::env::var_os("WARDEN_STATE_DIR").map(|base| PathBuf::from(base).join("audit")))
        .unwrap_or_else(|| PathBuf::from(ctx.expand(&policy.audit.dir)));
    Ok(warden_audit::AuditLog::new(dir))
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
