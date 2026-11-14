//! What the commands print.

use std::fmt::Write;

use warden_engine::Verdict;
use warden_engine::corpus::Mismatch;
use warden_policy::{Category, Policy};

/// `warden explain`: the whole chain for one command.
pub fn explain(policy: &Policy, verdict: &Verdict) -> String {
    let mut out = String::new();
    let _ = writeln!(out, "command:   {}", verdict.subject);
    if let Some(rewritten) = &verdict.rewritten {
        let _ = writeln!(out, "rewritten: {}  ({})", rewritten.line, rewritten.ids.join(", "));
    }
    let _ = writeln!(
        out,
        "policy:    profile={} mode={} interactive={}",
        policy.profile.name(),
        if policy.mode == warden_policy::Mode::Enforce { "enforce" } else { "audit" },
        policy.interactive
    );
    if verdict.findings.is_empty() {
        let _ = writeln!(out, "findings:  none");
    } else {
        let _ = writeln!(out, "findings:");
        for found in &verdict.findings {
            let _ = writeln!(out, "  - {:<16} {:<5} {}", found.category.name(), found.decision, found.detail);
        }
    }
    if let Some(rule) = &verdict.rule {
        let _ = writeln!(out, "rule:      {} -> {} ({})", rule.id, rule.decision, rule.source);
    }
    for note in &verdict.notes {
        let _ = writeln!(out, "note:      {note}");
    }
    let _ = writeln!(out, "decision:  {}  {}", verdict.decision.to_string().to_uppercase(), verdict.reason);
    if verdict.wrap_output {
        let _ = writeln!(out, "wrapped:   yes (the output would run through the redactor)");
    }
    out
}

/// `warden policy`: the merged result.
pub fn policy(policy: &Policy) -> String {
    let mut out = String::new();
    let _ = writeln!(out, "profile:     {}", policy.profile.name());
    let _ =
        writeln!(out, "mode:        {}", if policy.mode == warden_policy::Mode::Enforce { "enforce" } else { "audit" });
    let _ = writeln!(out, "interactive: {}", policy.interactive);
    let _ = writeln!(
        out,
        "on_error:    {}",
        if policy.on_error == warden_policy::OnError::Closed { "closed" } else { "open" }
    );
    let _ = writeln!(out, "locked:      {}", policy.locked);
    let _ = writeln!(out, "sources:     {}", policy.sources.join(", "));
    for warning in &policy.warnings {
        let _ = writeln!(out, "warning:     {warning}");
    }
    let _ = writeln!(out, "\ncategories:");
    for category in Category::ALL {
        let decision = policy.decision(*category);
        let _ = writeln!(out, "  {:<18} {decision}", category.name());
    }
    let _ = writeln!(out, "\nrules ({}):", policy.rules.len());
    for rule in &policy.rules {
        let _ = writeln!(out, "  {:<20} {} ({})", rule.id, rule.decision, rule.source);
    }
    let _ = writeln!(out, "rewrites ({}):", policy.rewrites.len());
    for rewrite in &policy.rewrites {
        let _ = writeln!(out, "  {}", rewrite.id);
    }
    let _ = writeln!(
        out,
        "\npaths:       {} credential globs, {} protected, {} personal data, scope {}",
        policy.paths.deny_read.patterns().len(),
        policy.paths.protected.patterns().len(),
        policy.paths.pii.patterns().len(),
        policy.paths.scope.as_ref().map_or_else(|| "none".to_owned(), |scope| scope.join(", "))
    );
    let _ = writeln!(
        out,
        "network:     {} denied domains, allow list {}",
        policy.network.deny_domains.len(),
        policy.network.allow_domains.as_ref().map_or_else(|| "off".to_owned(), |allowed| allowed.join(", "))
    );
    out
}

/// `warden test`: what differs.
pub fn test(total: usize, mismatches: &[Mismatch]) -> String {
    let mut out = String::new();
    for m in mismatches {
        let _ = writeln!(out, "FAIL  {}\n      expected {}, got {}: {}", m.cmd, m.expected, m.actual, m.reason);
    }
    let passed = total - mismatches.len();
    let _ =
        writeln!(out, "{passed} of {total} cases as expected{}", if mismatches.is_empty() { "" } else { ": FAILED" });
    out
}

/// `warden status`: the counts, then the records worth a look.
pub fn status(records: &[warden_audit::Record], all: bool, last: usize) -> String {
    use warden_audit::{label, summarize};
    let mut out = String::new();
    let summary = summarize(records);
    let decisions: Vec<String> = summary.decisions.iter().map(|(name, count)| format!("{name}={count}")).collect();
    let _ = writeln!(out, "records: {}   {}", summary.total, decisions.join(" "));
    if !summary.redactions.is_empty() {
        let kinds: Vec<String> = summary.redactions.iter().map(|(kind, count)| format!("{kind}={count}")).collect();
        let _ = writeln!(out, "redactions: {}", kinds.join(" "));
    }
    let shown: Vec<&warden_audit::Record> = records.iter().filter(|r| all || label(r) != "allow").collect();
    let skip = shown.len().saturating_sub(last);
    let _ = writeln!(out);
    for record in shown.into_iter().skip(skip) {
        let entry = &record.entry;
        let when = record.ts.get(..19).unwrap_or(&record.ts);
        let _ = writeln!(out, "{when}  {:<12}  {:<7} {:<6} {}", label(record), entry.agent, entry.kind, entry.summary);
        let categories = entry.categories.join(",");
        let _ = writeln!(out, "      {categories} {}", entry.reason);
    }
    out
}

/// `warden report`: what a stricter profile would have stopped among the calls that audit mode let through.
pub fn adoption(records: &[warden_audit::Record]) -> String {
    use std::collections::BTreeMap;
    let mut out = String::new();
    if records.is_empty() {
        let _ = writeln!(out, "nothing to report yet: the log holds no record");
        return out;
    }
    let calls: Vec<&warden_audit::Record> = records.iter().filter(|r| r.entry.kind != "run").collect();
    let mut stopped = 0_usize;
    let mut by_category: BTreeMap<&str, usize> = BTreeMap::new();
    let mut by_command: BTreeMap<(&str, &str), usize> = BTreeMap::new();
    for record in &calls {
        let entry = &record.entry;
        let intended = if entry.intended.is_empty() { entry.decision.as_str() } else { entry.intended.as_str() };
        if intended == "ask" || intended == "deny" {
            stopped += 1;
            for category in &entry.categories {
                *by_category.entry(category.as_str()).or_default() += 1;
            }
            *by_command.entry((intended, entry.summary.as_str())).or_default() += 1;
        }
    }
    let total = calls.len();
    let _ = writeln!(out, "calls: {total}   would be stopped: {stopped}");
    if !by_category.is_empty() {
        let _ = writeln!(out, "\nby category:");
        let mut rows: Vec<_> = by_category.into_iter().collect();
        rows.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(b.0)));
        for (category, count) in rows {
            let _ = writeln!(out, "  {category:<18} {count}");
        }
    }
    if !by_command.is_empty() {
        let _ = writeln!(out, "\nstopped most often:");
        let mut rows: Vec<_> = by_command.into_iter().collect();
        rows.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        for ((intended, summary), count) in rows.into_iter().take(10) {
            let _ = writeln!(out, "  {count:>4}x {intended:<5} {summary}");
        }
    }
    let share = (stopped * 100).checked_div(total).unwrap_or(0);
    let _ = writeln!(out, "\n{stopped} of {total} calls ({share}%) would have been stopped by the policy as written.");
    out
}

/// `warden report --json`: the same counts, for a program.
pub fn adoption_json(records: &[warden_audit::Record]) -> String {
    use std::collections::BTreeMap;
    let calls: Vec<&warden_audit::Record> = records.iter().filter(|r| r.entry.kind != "run").collect();
    let mut would_stop = 0_usize;
    let mut by_category: BTreeMap<&str, usize> = BTreeMap::new();
    for record in &calls {
        let entry = &record.entry;
        let intended = if entry.intended.is_empty() { entry.decision.as_str() } else { entry.intended.as_str() };
        if intended == "ask" || intended == "deny" {
            would_stop += 1;
            for category in &entry.categories {
                *by_category.entry(category.as_str()).or_default() += 1;
            }
        }
    }
    let summary = warden_audit::summarize(records);
    let object = serde_json::json!({
        "records": summary.total,
        "calls": calls.len(),
        "would_stop": would_stop,
        "by_category": by_category,
        "by_decision": summary.decisions,
        "redactions": summary.redactions,
    });
    format!("{object}\n")
}

/// `warden audit verify`.
pub fn verification(result: &warden_audit::Verification) -> String {
    match &result.problem {
        None => format!("the chain is intact: {} records in {} files\n", result.records, result.files),
        Some(problem) => format!(
            "the chain is BROKEN at {} line {}: {}\n({} records were read before it)\n",
            problem.file, problem.line, problem.what, result.records
        ),
    }
}
