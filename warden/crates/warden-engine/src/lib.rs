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

/// The longest address a fetch may use, and the longest query string or search: more than that is a payload, not a
/// question.
const MAX_URL: usize = 2048;
const MAX_QUERY: usize = 512;

/// Judge a fetch of a URL: what it reaches, and whether it carries something out in its address.
#[must_use]
pub fn judge_web(policy: &Policy, url: &str) -> Verdict {
    let mut findings = vec![Finding { category: Category::Network, detail: format!("fetches {url}") }];
    if let Some(scheme) = foreign_scheme(url) {
        findings
            .push(Finding { category: Category::Exfil, detail: format!("{scheme}: is not an http or https address") });
    }
    if let Some(host) = host_of(url) {
        if let Some(why) = internal_host(&host) {
            findings.push(Finding { category: Category::BlockedDomain, detail: why });
        }
        if let Some(why) = policy.network.denies(&host) {
            findings.push(Finding { category: Category::BlockedDomain, detail: why });
        }
    }
    if let Some(kind) = credential_in(url) {
        findings.push(Finding { category: Category::Exfil, detail: format!("the address contains {kind}") });
    }
    let query = url.split_once('?').map_or("", |(_, query)| query);
    if url.len() > MAX_URL || query.len() > MAX_QUERY {
        findings.push(Finding {
            category: Category::Exfil,
            detail: "the address is long enough to carry data out in it".to_owned(),
        });
    }
    conclude(policy, url.to_owned(), None, findings, None, false)
}

/// Judge a web search: what is searched for must not hold a credential or be a payload.
#[must_use]
pub fn judge_search(policy: &Policy, query: &str) -> Verdict {
    let mut findings = vec![Finding { category: Category::Network, detail: "searches the web".to_owned() }];
    if let Some(kind) = credential_in(query) {
        findings.push(Finding { category: Category::Exfil, detail: format!("the search contains {kind}") });
    }
    if query.len() > MAX_QUERY {
        findings.push(Finding {
            category: Category::Exfil,
            detail: "the search is long enough to carry data out in it".to_owned(),
        });
    }
    conclude(policy, shorten_subject(query), None, findings, None, false)
}

fn shorten_subject(text: &str) -> String {
    text.chars().take(80).collect()
}

/// The scheme of `url` when it is not http or https: a file, a data URL, an FTP or SSH address.
fn foreign_scheme(url: &str) -> Option<String> {
    let (scheme, rest) = url.split_once(':')?;
    let scheme = scheme.to_ascii_lowercase();
    let named = scheme.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '+' | '-' | '.'));
    let known = matches!(
        scheme.as_str(),
        "file" | "ftp" | "ftps" | "data" | "javascript" | "gopher" | "ssh" | "ldap" | "dict" | "jar"
    );
    let remote = rest.starts_with("//") && !matches!(scheme.as_str(), "http" | "https");
    (named && !scheme.is_empty() && (known || remote)).then_some(scheme)
}

/// Why `host` is not a place a fetch may go: this machine, a private network, or a name that is not on the internet.
fn internal_host(host: &str) -> Option<String> {
    let host = host.trim_end_matches('.').to_ascii_lowercase();
    let local_name = host == "localhost"
        || [".localhost", ".internal", ".local", ".localdomain", ".lan", ".home.arpa"]
            .iter()
            .any(|suffix| host.ends_with(suffix));
    if local_name {
        return Some(format!("{host} is a local or internal name"));
    }
    if let Ok(ip) = host.parse::<std::net::Ipv4Addr>() {
        let [a, b, ..] = ip.octets();
        let shared = a == 100 && (64..128).contains(&b);
        if ip.is_loopback()
            || ip.is_private()
            || ip.is_link_local()
            || ip.is_unspecified()
            || ip.is_broadcast()
            || shared
        {
            return Some(format!("{host} is a private or local address"));
        }
    }
    if let Ok(ip) = host.parse::<std::net::Ipv6Addr>() {
        let first = ip.segments()[0];
        let unique_local = first & 0xfe00 == 0xfc00;
        let link_local = first & 0xffc0 == 0xfe80;
        let mapped_private =
            ip.to_ipv4_mapped().is_some_and(|v4| v4.is_loopback() || v4.is_private() || v4.is_link_local());
        if ip.is_loopback() || ip.is_unspecified() || unique_local || link_local || mapped_private {
            return Some(format!("{host} is a private or local address"));
        }
    }
    // 2130706433 and 0x7f000001 are 127.0.0.1 to a resolver: a number for a host is a way round the checks above.
    let numeric = !host.is_empty() && host.chars().all(|c| c.is_ascii_digit());
    if numeric || host.starts_with("0x") {
        return Some(format!("{host} is a number written as a host name"));
    }
    None
}

/// Judge text that is about to be written, sent or typed: a credential in it is a finding of `category`
/// (`secret_write` for a file or a tool argument, `secret_prompt` for a person's prompt).
#[must_use]
pub fn judge_text(policy: &Policy, subject: &str, text: &str, category: Category) -> Verdict {
    let findings = credential_in(text)
        .map(|kind| vec![Finding { category, detail: format!("{subject} contains {kind}") }])
        .unwrap_or_default();
    conclude(policy, subject.to_owned(), None, findings, None, false)
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
    let hostport = authority.rsplit('@').next()?;
    let host = match hostport.strip_prefix('[') {
        Some(inside) => inside.split(']').next()?,
        None => hostport.split(':').next()?,
    };
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
