//! Judges a tool call against a policy: what would it do, and is that allowed.
//!
//! [`judge_command`] is the whole path for a shell command: apply the policy's rewrites, read the line as bash,
//! classify it, decide. The other `judge_*` functions do the same for the doors that are not a shell: reading and
//! writing files and fetching a URL. Nothing here touches the disk or the network.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

mod classify;
pub mod corpus;
mod paths;
mod secrets;

use warden_policy::{Category, Decision, Mode, Policy};
use warden_shell::{Parsed, Via};

pub use classify::{Finding, classify};
pub use paths::Context;
pub use secrets::{credential_in, is_secret_name, looks_like_secret_value};

/// A finding with what the policy says about its category.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Judged {
    /// The kind of risk.
    pub category: Category,
    /// What shows it.
    pub detail: String,
    /// What the policy decides for that category.
    pub decision: Decision,
}

/// A rule that decided the verdict.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuleHit {
    /// The rule's name.
    pub id: String,
    /// What it decided.
    pub decision: Decision,
    /// Its reason.
    pub reason: String,
    /// The layer it came from.
    pub source: String,
}

/// A rewrite that changed the command before it was judged.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Rewritten {
    /// The command line that was judged and will run.
    pub line: String,
    /// The rewrites applied, by name.
    pub ids: Vec<String>,
}

/// What was decided about a tool call, and why.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Verdict {
    /// What was asked: the command line, a path or a URL.
    pub subject: String,
    /// The rewrite, when the policy changed the command.
    pub rewritten: Option<Rewritten>,
    /// Everything the classifier found.
    pub findings: Vec<Judged>,
    /// The rule that decided, when one did.
    pub rule: Option<RuleHit>,
    /// What happens to the call.
    pub decision: Decision,
    /// What the policy decided before audit mode and the lack of anyone to ask changed it.
    pub intended: Decision,
    /// How `decision` came to differ from `intended`.
    pub notes: Vec<String>,
    /// Why, for the model and for the log.
    pub reason: String,
    /// Whether the command should run through the redactor: allowed, and not a command that changes the shell.
    pub wrap_output: bool,
}

impl Verdict {
    /// The command line to run: the rewritten one when there is one.
    #[must_use]
    pub fn line(&self) -> &str {
        self.rewritten.as_ref().map_or(self.subject.as_str(), |r| r.line.as_str())
    }
}

/// Commands that change the shell they run in: run through a wrapper they would lose their effect.
const SHELL_STATE: [&str; 14] = [
    "cd", "export", "source", ".", "unset", "alias", "set", "pushd", "popd", "ulimit", "umask", "shopt", "declare",
    "read",
];

/// Judge a shell command line.
#[must_use]
pub fn judge_command(policy: &Policy, ctx: &Context, command: &str) -> Verdict {
    let (line, ids) = policy.rewrite(command);
    let rewritten = (!ids.is_empty()).then(|| Rewritten { line: line.clone(), ids });
    let (findings, changes_shell) = match warden_shell::parse(&line) {
        Ok(parsed) => (classify(&parsed, policy, ctx), changes_shell_state(&parsed)),
        Err(error) => (
            vec![Finding { category: Category::Obfuscation, detail: format!("the command cannot be read: {error}") }],
            true,
        ),
    };
    let rule = policy.rule_for(&line);
    conclude(policy, command.to_owned(), rewritten, findings, rule, !changes_shell && !line.starts_with("warden run"))
}

fn changes_shell_state(parsed: &Parsed) -> bool {
    parsed
        .invocations
        .iter()
        .filter(|inv| inv.via == Via::Direct)
        .any(|inv| inv.name().is_some_and(|name| SHELL_STATE.contains(&name)))
}

/// Judge the Read tool opening a file.
#[must_use]
pub fn judge_read(policy: &Policy, ctx: &Context, path: &str) -> Verdict {
    let word = word_of(path);
    let candidates = ctx.candidates(&word);
    let findings = if policy.paths.deny_read.is_match(&candidates) {
        vec![Finding { category: Category::SecretAccess, detail: format!("{path} is a credential file") }]
    } else {
        Vec::new()
    };
    conclude(policy, path.to_owned(), None, findings, None, false)
}

/// Judge the Write or Edit tool changing a file.
#[must_use]
pub fn judge_write(policy: &Policy, ctx: &Context, path: &str) -> Verdict {
    let word = word_of(path);
    let candidates = ctx.candidates(&word);
    let mut findings = Vec::new();
    if policy.paths.protected.is_match(&candidates) {
        findings.push(Finding {
            category: Category::Tamper,
            detail: format!("{path} is a protected agent or Warden file"),
        });
    }
    if policy.paths.deny_write.is_match(&candidates) {
        findings.push(Finding { category: Category::Destructive, detail: format!("{path} is never written") });
    }
    if let Some(scope) = &policy.paths.scope {
        let absolute = ctx.absolute(path);
        if !paths::is_temporary(&absolute) && !ctx.in_scope(&absolute, scope) {
            findings.push(Finding {
                category: Category::OutOfScope,
                detail: format!("{path} is outside the working scope"),
            });
        }
    }
    conclude(policy, path.to_owned(), None, findings, None, false)
}

/// Judge a fetch of a URL.
#[must_use]
pub fn judge_web(policy: &Policy, url: &str) -> Verdict {
    let mut findings = vec![Finding { category: Category::Network, detail: format!("fetches {url}") }];
    if let Some(host) = host_of(url)
        && let Some(why) = policy.network.denies(&host)
    {
        findings.push(Finding { category: Category::BlockedDomain, detail: why });
    }
    conclude(policy, url.to_owned(), None, findings, None, false)
}

/// What the policy says about an agent tool by name (`tools.deny` and `tools.ask`), if anything.
#[must_use]
pub fn judge_tool(policy: &Policy, tool: &str) -> Option<Verdict> {
    let decision = policy.tool_decision(tool)?;
    let reason =
        format!("the policy {} the tool {tool}", if decision == Decision::Deny { "refuses" } else { "asks about" });
    Some(finish(policy, tool.to_owned(), None, Vec::new(), None, decision, reason, false))
}

fn word_of(text: &str) -> warden_shell::Word {
    warden_shell::Word { raw: text.to_owned(), value: Some(text.to_owned()), ..warden_shell::Word::default() }
}

fn host_of(url: &str) -> Option<String> {
    let rest = url.split_once("://").map_or(url, |(_, rest)| rest);
    let authority = rest.split(['/', '?', '#']).next()?;
    let host = authority.rsplit('@').next()?.split(':').next()?;
    (!host.is_empty()).then(|| host.to_owned())
}

fn conclude(
    policy: &Policy,
    subject: String,
    rewritten: Option<Rewritten>,
    findings: Vec<Finding>,
    rule: Option<&warden_policy::Rule>,
    wrappable: bool,
) -> Verdict {
    let judged: Vec<Judged> = findings
        .into_iter()
        .map(|f| Judged { decision: policy.decision(f.category), category: f.category, detail: f.detail })
        .collect();
    let strictest = judged.iter().map(|j| j.decision).max().unwrap_or(Decision::Allow);
    let fixed = judged.iter().any(|j| j.category.always_denied());
    let rule_hit = rule.map(|r| RuleHit {
        id: r.id.clone(),
        decision: r.decision,
        reason: r.reason.clone(),
        source: r.source.clone(),
    });
    let (decision, reason) = match (&rule_hit, fixed) {
        (Some(hit), false) => {
            let why = if hit.reason.is_empty() {
                format!("rule {}", hit.id)
            } else {
                format!("rule {}: {}", hit.id, hit.reason)
            };
            (hit.decision, why)
        }
        _ => (strictest, reason_of(&judged, strictest)),
    };
    finish(policy, subject, rewritten, judged, rule_hit, decision, reason, wrappable)
}

fn reason_of(judged: &[Judged], strictest: Decision) -> String {
    if strictest == Decision::Allow {
        return if judged.is_empty() { "no risky pattern" } else { "nothing the policy refuses" }.to_owned();
    }
    let causes: Vec<String> =
        judged.iter().filter(|j| j.decision == strictest).map(|j| format!("{} ({})", j.detail, j.category)).collect();
    if causes.is_empty() { "no risky pattern".to_owned() } else { causes.join("; ") }
}

#[allow(clippy::too_many_arguments)]
fn finish(
    policy: &Policy,
    subject: String,
    rewritten: Option<Rewritten>,
    findings: Vec<Judged>,
    rule: Option<RuleHit>,
    intended: Decision,
    reason: String,
    wrappable: bool,
) -> Verdict {
    let mut decision = intended;
    let mut notes = Vec::new();
    if decision == Decision::Ask && !policy.interactive {
        decision = Decision::Deny;
        notes.push("an ask is a deny here: nobody is there to answer it".to_owned());
    }
    if policy.mode == Mode::Audit && decision != Decision::Allow {
        notes.push(format!("audit mode: would {decision}"));
        decision = Decision::Allow;
    }
    let wrap_output = decision == Decision::Allow && wrappable;
    Verdict { subject, rewritten, findings, rule, decision, intended, notes, reason, wrap_output }
}
