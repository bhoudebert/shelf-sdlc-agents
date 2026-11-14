//! What a command line would do, as risk categories: one finding per risky thing, each with the words that show it.

use std::sync::LazyLock;

use regex::Regex;
use warden_policy::{Category, Policy};
use warden_shell::{Invocation, Parsed, RedirectKind, Word};

use crate::paths::{Context, is_system_directory, is_temporary};
use crate::secrets::{credential_in, is_secret_name, literal, looks_like_secret_value};

/// One risky thing a command would do.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    /// The kind of risk.
    pub category: Category,
    /// What shows it, in words a person can read.
    pub detail: String,
}

struct Cx<'a> {
    policy: &'a Policy,
    ctx: &'a Context,
    parsed: &'a Parsed,
    out: Vec<Finding>,
}

impl Cx<'_> {
    fn add(&mut self, category: Category, detail: impl Into<String>) {
        let detail = detail.into();
        if !self.out.iter().any(|f| f.category == category && f.detail == detail) {
            self.out.push(Finding { category, detail });
        }
    }
}

static URL_HOST: LazyLock<Regex> =
    LazyLock::new(|| literal(r"(?i)\b[a-z][a-z0-9+.-]*://(?:[^/@\s'\x22]*@)?([^/:\s?#'\x22]+)"));
static SQL_DESTRUCTIVE: LazyLock<Regex> =
    LazyLock::new(|| literal(r"(?i)\b(?:drop\s+(?:table|database|schema|index|view)|truncate(?:\s+table)?\s+\w)"));
static SPAWNS_SHELL: LazyLock<Regex> = LazyLock::new(|| {
    literal(
        r"(?i)(os\.system|subprocess|child_process|popen|execSync|spawnSync|\bexec\(|\bsystem\(|Runtime\.getRuntime|pty\.spawn|`[^`]+`)",
    )
});
static REMOTE_ARG: LazyLock<Regex> = LazyLock::new(|| literal(r"^(?:[\w.-]+@)?[\w.-]+\.[\w.-]+:|^[\w.-]+@[\w.-]+:"));
static SECRET_COMMAND: LazyLock<Regex> = LazyLock::new(|| {
    literal(
        r"(?i)\b(?:get-secret-value|get-session-token|print-access-token|print-identity-token|get-access-token|find-generic-password|find-internet-password|export-secret-keys)\b",
    )
});

const SHELLS: [&str; 7] = ["sh", "bash", "zsh", "dash", "ksh", "ash", "fish"];
const INTERPRETERS: [&str; 7] = ["python", "node", "nodejs", "perl", "ruby", "php", "deno"];
const FETCHERS: [&str; 5] = ["curl", "wget", "fetch", "aria2c", "http"];
/// Commands that do not read the content of the files named in their arguments.
const NON_READERS: [&str; 33] = [
    "echo", "printf", "ls", "stat", "chmod", "chown", "chgrp", "rm", "rmdir", "unlink", "mv", "mkdir", "touch", "cd",
    "pwd", "which", "type", "test", "true", "false", "ln", "truncate", "tee", "git", "npm", "yarn", "pnpm", "pip",
    "pip3", "cargo", "make", "docker", "kubectl",
];
const KEY_OPTION_COMMANDS: [&str; 6] = ["ssh", "scp", "sftp", "ssh-add", "ssh-keygen", "rsync"];

/// Classify everything a parsed command line would run.
#[must_use]
pub fn classify(parsed: &Parsed, policy: &Policy, ctx: &Context) -> Vec<Finding> {
    let mut cx = Cx { policy, ctx, parsed, out: Vec::new() };
    for inv in &parsed.invocations {
        invocation(&mut cx, inv);
    }
    pipelines(&mut cx);
    cx.out
}

fn texts(inv: &Invocation) -> Vec<String> {
    inv.args().iter().map(|w| w.text().to_owned()).collect()
}

fn base_name(name: &str) -> &str {
    if name.starts_with("python") {
        "python"
    } else if name.starts_with("mkfs") {
        "mkfs"
    } else {
        name
    }
}

fn has_short(args: &[String], letter: char) -> bool {
    args.iter().any(|a| {
        a.starts_with('-') && !a.starts_with("--") && a.chars().skip(1).all(char::is_alphabetic) && a.contains(letter)
    })
}

fn has_long(args: &[String], name: &str) -> bool {
    let flag = format!("--{name}");
    args.iter().any(|a| *a == flag || a.starts_with(&format!("{flag}=")))
}

fn has_any(args: &[String], names: &[&str]) -> bool {
    args.iter().any(|a| names.iter().any(|n| a == n || a.starts_with(&format!("{n}="))))
}

fn operands(inv: &Invocation) -> Vec<&Word> {
    inv.args().iter().filter(|w| !w.text().starts_with('-') || w.text() == "-").collect()
}

fn invocation(cx: &mut Cx<'_>, inv: &Invocation) {
    let Some(name) = inv.name().map(str::to_owned) else {
        if inv.dynamic_name {
            cx.add(Category::DynamicExec, "the command name comes from an expansion");
        }
        redirects(cx, inv, "the command");
        assignments(cx, inv);
        return;
    };
    let name = base_name(&name).to_owned();
    if inv.dynamic_name {
        cx.add(Category::DynamicExec, format!("{name} is run from an expansion"));
    }
    let args = texts(inv);
    assignments(cx, inv);
    generic_arguments(cx, inv, &name);
    redirects(cx, inv, &name);
    writes(cx, inv, &name, &args);
    reads(cx, inv, &name);
    by_command(cx, inv, &name, &args);
    sinks(cx, inv, &name);
}

/// Findings that depend only on what the words are: credentials, secret variables, URLs.
fn generic_arguments(cx: &mut Cx<'_>, inv: &Invocation, name: &str) {
    for word in inv.args() {
        let text = word.text();
        if let Some(kind) = credential_in(text) {
            cx.add(Category::SecretWrite, format!("{name} is given {kind}"));
        }
        for parameter in &word.parameters {
            let bare = parameter.trim_start_matches('$').trim_matches(|c| c == '{' || c == '}');
            let variable = bare.split(|c: char| !(c.is_alphanumeric() || c == '_')).next().unwrap_or(bare);
            if is_secret_name(variable) && name != "export" && name != "unset" {
                cx.add(Category::EnvDump, format!("{name} expands the secret variable {variable}"));
            }
        }
        for capture in URL_HOST.captures_iter(text) {
            if let Some(host) = capture.get(1)
                && let Some(why) = cx.policy.network.denies(host.as_str())
            {
                cx.add(Category::BlockedDomain, why);
            }
        }
        if matches!(name, "export" | "declare" | "env")
            && let Some((variable, value)) = text.split_once('=')
            && is_secret_name(variable)
            && looks_like_secret_value(value)
        {
            cx.add(Category::SecretWrite, format!("{name} sets {variable} to a literal secret"));
        }
    }
}

fn assignments(cx: &mut Cx<'_>, inv: &Invocation) {
    for (variable, value) in &inv.assignments {
        let text = value.text();
        match variable.as_str() {
            "HUSKY" if text == "0" => cx.add(Category::BypassChecks, "HUSKY=0 turns the git hooks off"),
            "SKIP" | "SKIP_HOOKS" | "PRE_COMMIT_ALLOW_NO_CONFIG" if !text.is_empty() => {
                cx.add(Category::BypassChecks, format!("{variable} skips checks"));
            }
            "GIT_SSL_NO_VERIFY" | "NODE_TLS_REJECT_UNAUTHORIZED" if text == "0" || text == "true" || text == "1" => {
                cx.add(Category::BypassChecks, format!("{variable} turns TLS verification off"));
            }
            _ => {}
        }
        if is_secret_name(variable) && looks_like_secret_value(text) {
            cx.add(Category::SecretWrite, format!("{variable} is set to a literal secret"));
        }
    }
}

fn redirects(cx: &mut Cx<'_>, inv: &Invocation, name: &str) {
    for redirect in &inv.redirects {
        match redirect.kind {
            RedirectKind::Read => read_path(cx, name, &redirect.target),
            RedirectKind::Write | RedirectKind::Append => write_path(cx, name, &redirect.target, "redirects output to"),
            RedirectKind::Other => {}
        }
    }
}

fn read_path(cx: &mut Cx<'_>, name: &str, word: &Word) {
    let candidates = cx.ctx.candidates(word);
    if !candidates.is_empty() && cx.policy.paths.deny_read.is_match(&candidates) {
        cx.add(Category::SecretAccess, format!("{name} reads {}, a credential file", word.text()));
    }
}

fn write_path(cx: &mut Cx<'_>, name: &str, word: &Word, verb: &str) {
    let candidates = cx.ctx.candidates(word);
    if candidates.is_empty() {
        return;
    }
    let shown = word.text();
    if cx.policy.paths.protected.is_match(&candidates) {
        cx.add(Category::Tamper, format!("{name} {verb} {shown}, a protected agent or Warden file"));
    }
    if cx.policy.paths.deny_write.is_match(&candidates) {
        cx.add(Category::Destructive, format!("{name} {verb} {shown}, a file that is never written"));
    }
    let absolute = cx.ctx.absolute(word.text());
    if absolute.starts_with("/dev/sd") || absolute.starts_with("/dev/nvme") || absolute.starts_with("/dev/disk") {
        cx.add(Category::Destructive, format!("{name} {verb} the block device {shown}"));
    }
    if let Some(scope) = &cx.policy.paths.scope
        && !is_temporary(&absolute)
        && !cx.ctx.in_scope(&absolute, scope)
    {
        cx.add(Category::OutOfScope, format!("{name} {verb} {shown}, outside the working scope"));
    }
}

/// The files a command changes, by what the command is.
fn written_words<'a>(inv: &'a Invocation, name: &str, args: &[String]) -> Vec<&'a Word> {
    let operands = operands(inv);
    match name {
        "rm" | "rmdir" | "unlink" | "shred" | "touch" | "truncate" | "mkdir" | "tee" | "mv" => operands,
        "chmod" | "chown" | "chgrp" => operands.into_iter().skip(1).collect(),
        "cp" | "install" | "ln" | "rsync" => operands.last().copied().into_iter().collect(),
        "sed" | "perl" if has_short(args, 'i') || has_long(args, "in-place") => {
            let skip = usize::from(!has_short(args, 'e'));
            operands.into_iter().skip(skip).collect()
        }
        "dd" => inv.args().iter().filter(|w| w.text().starts_with("of=")).collect(),
        _ => Vec::new(),
    }
}

fn writes(cx: &mut Cx<'_>, inv: &Invocation, name: &str, args: &[String]) {
    for word in written_words(inv, name, args) {
        let target = if name == "dd" {
            Word {
                raw: word.raw.clone(),
                value: word.value.as_ref().map(|v| v.trim_start_matches("of=").to_owned()),
                ..Word::default()
            }
        } else {
            word.clone()
        };
        write_path(cx, name, &target, "writes");
    }
}

fn reads(cx: &mut Cx<'_>, inv: &Invocation, name: &str) {
    if NON_READERS.contains(&name) {
        return;
    }
    let mut skip_next = false;
    for word in inv.args() {
        if skip_next {
            skip_next = false;
            continue;
        }
        let text = word.text();
        if KEY_OPTION_COMMANDS.contains(&name) {
            if text == "-i" || text == "-F" {
                skip_next = true;
                continue;
            }
            continue;
        }
        if text.starts_with('-') {
            continue;
        }
        read_path(cx, name, word);
    }
}

fn by_command(cx: &mut Cx<'_>, inv: &Invocation, name: &str, args: &[String]) {
    let operands = operands(inv);
    let first = operands.first().map(|w| w.text().to_owned()).unwrap_or_default();
    match name {
        "rm" => remove(cx, inv, args),
        "find" if has_any(args, &["-delete"]) => cx.add(Category::Delete, "find -delete removes the files it finds"),
        "dd" if args.iter().any(|a| a.starts_with("of=/dev/")) => {
            cx.add(Category::Destructive, "dd writes straight to a device");
        }
        "mkfs" | "wipefs" | "fdisk" | "parted" | "sfdisk" => {
            cx.add(Category::Destructive, format!("{name} changes a disk"));
        }
        "crontab" if has_short(args, 'r') => cx.add(Category::Destructive, "crontab -r removes every scheduled job"),
        "chmod" | "chown" | "chgrp" => permissions(cx, inv, name, args),
        "git" => git(cx, args),
        "curl" => curl(cx, args),
        "wget" => wget(cx, args),
        "nc" | "ncat" | "netcat" | "socat" | "telnet" => {
            cx.add(Category::Exfil, format!("{name} opens a raw connection that can carry any data"));
            cx.add(Category::Network, name);
        }
        "scp" | "rsync" | "sftp" | "ftp" => transfer(cx, name, &operands),
        "ssh" | "ping" | "dig" | "nslookup" | "host" | "traceroute" | "gh" | "gcloud" | "az" | "helm" | "heroku"
        | "vercel" | "fly" | "flyctl" | "terraform" | "kubectl" | "docker" => {
            cx.add(Category::Network, name);
            cloud_and_tools(cx, name, args, &first);
        }
        "aws" => {
            cx.add(Category::Network, "aws");
            cloud_and_tools(cx, name, args, &first);
        }
        "mail" | "mailx" | "mutt" | "sendmail" | "swaks" => {
            cx.add(Category::Exfil, format!("{name} sends data to a remote address"));
        }
        "gsutil" | "rclone" | "az-copy" | "azcopy" => cloud_and_tools(cx, name, args, &first),
        "sudo" | "su" | "doas" | "pkexec" => cx.add(Category::Privilege, format!("{name} runs with other privileges")),
        "launchctl" | "systemctl" | "service" | "mount" | "umount" | "iptables" | "useradd" | "usermod" | "passwd" => {
            cx.add(Category::Privilege, format!("{name} changes the system"));
        }
        "env" | "printenv" | "set" if (name != "env" || operands.is_empty()) && (name != "set" || args.is_empty()) => {
            cx.add(Category::EnvDump, format!("{name} prints the environment, secrets included"));
        }
        "export" if has_short(args, 'p') => cx.add(Category::EnvDump, "export -p prints the environment"),
        "npm" | "yarn" | "pnpm" | "bun" => node_packages(cx, name, args, &first, &operands),
        "pip" | "pip3" | "pipx" | "uv" | "poetry" | "gem" | "go" | "cargo" | "brew" | "apt" | "apt-get" | "dnf"
        | "yum" | "apk" | "pacman" | "mise" | "npx" | "uvx" | "bunx" | "pnpx" => {
            other_packages(cx, name, args, &first);
        }
        "twine" if first == "upload" => cx.add(Category::Publish, "twine upload publishes a package"),
        "eval" => {
            if inv.dynamic_string {
                cx.add(Category::Eval, "eval runs text that is only known when it runs");
            }
        }
        "source" | "." => {}
        _ if INTERPRETERS.contains(&name) => interpreter(cx, name, args),
        _ => {}
    }
    if SECRET_COMMAND.is_match(&args.join(" ")) && name != "echo" {
        cx.add(Category::SecretAccess, format!("{name} prints or exports a secret"));
    }
    if has_any(args, &["--registry", "--index-url", "--extra-index-url"]) {
        cx.add(Category::SupplyChain, format!("{name} uses a registry other than the default"));
    }
    let text = args.join(" ");
    if matches!(name, "psql" | "mysql" | "mariadb" | "sqlite3" | "mongosh" | "redis-cli")
        && SQL_DESTRUCTIVE.is_match(&text)
    {
        cx.add(Category::Destructive, format!("{name} runs SQL that drops or empties data"));
    }
}

fn remove(cx: &mut Cx<'_>, inv: &Invocation, args: &[String]) {
    let recursive = has_short(args, 'r') || has_short(args, 'R') || has_long(args, "recursive");
    if !recursive {
        return;
    }
    for word in operands(inv) {
        let shown = word.text();
        let Some(resolved) = cx.ctx.resolved(word) else {
            cx.add(Category::Delete, format!("rm -r of {shown}, a path only known when it runs"));
            continue;
        };
        let absolute = cx.ctx.absolute(resolved.trim_end_matches('*'));
        if is_temporary(&absolute) {
            continue;
        }
        if is_system_directory(&absolute, &cx.ctx.home) || !cx.ctx.in_workspace(&absolute) {
            cx.add(Category::Destructive, format!("rm -r of {shown} reaches outside the workspace"));
        } else {
            cx.add(Category::Delete, format!("rm -r of {shown} inside the workspace"));
        }
    }
}

fn permissions(cx: &mut Cx<'_>, inv: &Invocation, name: &str, args: &[String]) {
    let operands = operands(inv);
    let mode = operands.first().map(|w| w.text()).unwrap_or_default();
    if name == "chmod" && (mode == "777" || mode == "0777" || mode.contains("+s") || mode.starts_with('4')) {
        cx.add(Category::Privilege, format!("chmod {mode} opens a file to everyone or sets a privilege bit"));
    }
    if has_short(args, 'R') || has_long(args, "recursive") {
        for word in operands.iter().skip(1) {
            let absolute = cx.ctx.absolute(word.text().trim_end_matches('*'));
            if is_system_directory(&absolute, &cx.ctx.home) {
                cx.add(Category::Destructive, format!("{name} -R of {} changes a system directory", word.text()));
            }
        }
    }
}

fn git(cx: &mut Cx<'_>, args: &[String]) {
    let mut subcommand_at = None;
    let mut skip = false;
    for (at, arg) in args.iter().enumerate() {
        if skip {
            skip = false;
            continue;
        }
        if arg == "-c" || arg == "-C" {
            skip = true;
            if arg == "-c" && args.get(at + 1).is_some_and(|v| v.starts_with("core.hooksPath")) {
                cx.add(Category::BypassChecks, "git -c core.hooksPath replaces the git hooks");
            }
            continue;
        }
        if arg.starts_with('-') {
            continue;
        }
        subcommand_at = Some(at);
        break;
    }
    let Some(at) = subcommand_at else { return };
    let sub = args[at].as_str();
    let rest = &args[at + 1..];
    let operands: Vec<&String> = rest.iter().filter(|a| !a.starts_with('-')).collect();
    match sub {
        "push" => {
            cx.add(Category::Network, "git push");
            let lease = has_long(rest, "force-with-lease") || has_long(rest, "force-if-includes");
            if (has_long(rest, "force") || has_short(rest, 'f')) && !lease {
                cx.add(Category::VcsForce, "git push --force can overwrite the work of others");
            }
            if has_long(rest, "delete") || has_short(rest, 'd') || operands.iter().any(|a| a.starts_with(':')) {
                cx.add(Category::VcsDestructive, "git push deletes a remote branch");
            }
            if has_long(rest, "mirror") {
                cx.add(Category::VcsDestructive, "git push --mirror overwrites the remote");
            }
            if has_long(rest, "no-verify") {
                cx.add(Category::BypassChecks, "git push --no-verify skips the hooks");
            }
        }
        "fetch" | "pull" | "clone" | "ls-remote" | "submodule" => cx.add(Category::Network, format!("git {sub}")),
        "commit" | "merge" | "rebase" | "cherry-pick" | "am" => {
            if has_long(rest, "no-verify") || (sub == "commit" && has_short(rest, 'n')) {
                cx.add(Category::BypassChecks, format!("git {sub} --no-verify skips the hooks"));
            }
        }
        "reset" if has_long(rest, "hard") => {
            cx.add(Category::VcsDestructive, "git reset --hard throws away changes");
        }
        "clean" if has_short(rest, 'f') || has_long(rest, "force") => {
            cx.add(Category::VcsDestructive, "git clean deletes untracked files");
        }
        "checkout" | "restore" if operands.iter().any(|a| *a == ".") || rest.iter().any(|a| a == "--force") => {
            cx.add(Category::VcsDestructive, format!("git {sub} discards changes"));
        }
        "branch" if has_short(rest, 'D') => cx.add(Category::VcsDestructive, "git branch -D deletes a branch"),
        "stash" if operands.first().is_some_and(|a| *a == "drop" || *a == "clear") => {
            cx.add(Category::VcsDestructive, "git stash drop loses stashed work");
        }
        "reflog" | "filter-branch" | "filter-repo" | "gc" | "update-ref" | "prune" => {
            if sub != "gc" || has_any(rest, &["--prune=now"]) {
                cx.add(Category::VcsDestructive, format!("git {sub} rewrites or erases history"));
            }
        }
        "config" => {
            if has_long(rest, "global") || has_long(rest, "system") {
                cx.add(Category::Privilege, "git config changes the configuration of every repository");
            }
            if rest.iter().any(|a| a.starts_with("core.hooksPath")) {
                cx.add(Category::BypassChecks, "git config core.hooksPath replaces the git hooks");
            }
        }
        _ => {}
    }
}

fn curl(cx: &mut Cx<'_>, args: &[String]) {
    cx.add(Category::Network, "curl");
    let sends = has_any(
        args,
        &[
            "-d",
            "--data",
            "--data-raw",
            "--data-binary",
            "--data-ascii",
            "--data-urlencode",
            "-F",
            "--form",
            "--form-string",
            "-T",
            "--upload-file",
            "--json",
        ],
    ) || has_short(args, 'd')
        || has_short(args, 'F')
        || has_short(args, 'T');
    if sends {
        cx.add(Category::Exfil, "curl sends data to a remote host");
    }
    if has_short(args, 'k') || has_long(args, "insecure") {
        cx.add(Category::BypassChecks, "curl -k turns TLS verification off");
    }
}

fn wget(cx: &mut Cx<'_>, args: &[String]) {
    cx.add(Category::Network, "wget");
    if has_any(args, &["--post-data", "--post-file", "--body-data", "--body-file"]) {
        cx.add(Category::Exfil, "wget sends data to a remote host");
    }
    if has_long(args, "no-check-certificate") {
        cx.add(Category::BypassChecks, "wget --no-check-certificate turns TLS verification off");
    }
}

fn transfer(cx: &mut Cx<'_>, name: &str, operands: &[&Word]) {
    cx.add(Category::Network, name);
    if let Some(last) = operands.last()
        && REMOTE_ARG.is_match(last.text())
    {
        cx.add(Category::Exfil, format!("{name} copies files to the remote {}", last.text()));
    }
}

fn cloud_and_tools(cx: &mut Cx<'_>, name: &str, args: &[String], first: &str) {
    let joined = args.join(" ");
    match name {
        "aws" => {
            if args.iter().any(|a| matches!(a.as_str(), "cp" | "mv" | "sync"))
                && args.last().is_some_and(|a| a.starts_with("s3://"))
            {
                cx.add(Category::Exfil, "aws s3 uploads files to a bucket");
            }
            if args.iter().any(|a| a == "rb" || a.starts_with("delete") || a.starts_with("terminate") || a == "rm") {
                cx.add(Category::Destructive, "aws deletes cloud resources");
            }
            if joined.contains("configure get") && joined.to_ascii_lowercase().contains("secret") {
                cx.add(Category::SecretAccess, "aws configure get reads a secret key");
            }
        }
        "gcloud" | "az" | "heroku" | "helm" | "fly" | "flyctl" | "vercel" => {
            if args.iter().any(|a| a == "delete" || a == "destroy" || a == "uninstall") {
                cx.add(Category::Destructive, format!("{name} deletes cloud resources"));
            }
            if args.iter().any(|a| a == "deploy") {
                cx.add(Category::Publish, format!("{name} deploys"));
            }
        }
        "terraform" => match first {
            "destroy" => cx.add(Category::Destructive, "terraform destroy tears infrastructure down"),
            "apply" => cx.add(Category::Publish, "terraform apply changes infrastructure"),
            _ => {}
        },
        "kubectl" => {
            if first == "delete" {
                cx.add(Category::Destructive, "kubectl delete removes cluster resources");
            }
            if first == "get" && args.iter().any(|a| a == "secret" || a == "secrets") {
                cx.add(Category::SecretAccess, "kubectl get secret reads cluster secrets");
            }
        }
        "docker" => {
            if args.iter().any(|a| a == "prune") {
                cx.add(Category::Destructive, "docker prune removes images, containers or volumes");
            }
            if first == "push" {
                cx.add(Category::Publish, "docker push publishes an image");
            }
            if matches!(first, "pull" | "run" | "build" | "compose") {
                cx.add(Category::PackageInstall, format!("docker {first} fetches images"));
            }
            if has_long(args, "privileged") || args.iter().any(|a| a.starts_with("/:") || a == "-v/:/host") {
                cx.add(Category::Privilege, "docker gives the container the host's privileges or root");
            }
        }
        "gh" => {
            if first == "auth" && args.iter().any(|a| a == "token") {
                cx.add(Category::SecretAccess, "gh auth token prints the GitHub token");
            }
            if first == "gist" {
                cx.add(Category::Exfil, "gh gist publishes text to a public place");
            }
            if first == "release" && args.iter().any(|a| a == "create") {
                cx.add(Category::Publish, "gh release create publishes a release");
            }
        }
        "gsutil" | "azcopy" | "az-copy" => {
            if args.last().is_some_and(|a| a.starts_with("gs://") || a.starts_with("https://"))
                && matches!(first, "cp" | "rsync" | "mv" | "copy" | "sync")
            {
                cx.add(Category::Exfil, format!("{name} uploads files to cloud storage"));
            }
        }
        "rclone"
            if matches!(first, "copy" | "sync" | "move" | "copyto" | "moveto")
                && args.last().is_some_and(|a| a.contains(':') && !a.starts_with('/')) =>
        {
            cx.add(Category::Exfil, "rclone copies files to a remote");
        }
        _ => {}
    }
}

fn node_packages(cx: &mut Cx<'_>, name: &str, args: &[String], first: &str, operands: &[&Word]) {
    match first {
        "publish" => cx.add(Category::Publish, format!("{name} publish releases a package")),
        "install" | "i" | "add" if operands.len() > 1 => {
            cx.add(Category::PackageInstall, format!("{name} {first} adds a new dependency"));
        }
        "config" if args.iter().any(|a| a == "registry") => {
            cx.add(Category::SupplyChain, format!("{name} config changes the registry"));
        }
        _ => {}
    }
}

fn other_packages(cx: &mut Cx<'_>, name: &str, args: &[String], first: &str) {
    let installs = match name {
        "pip" | "pip3" | "pipx" | "gem" | "apt" | "apt-get" | "dnf" | "yum" | "apk" | "brew" | "mise" => {
            first == "install"
        }
        "uv" => first == "add" || args.iter().take(2).any(|a| a == "install"),
        "poetry" => first == "add",
        "cargo" => first == "install",
        "go" => first == "install" || first == "get",
        "pacman" => args.iter().any(|a| a.starts_with("-S")),
        _ => name.ends_with('x'),
    };
    if installs {
        cx.add(Category::PackageInstall, format!("{name} installs software"));
    }
    if name == "cargo" && first == "publish" {
        cx.add(Category::Publish, "cargo publish releases a crate");
    }
}

fn interpreter(cx: &mut Cx<'_>, name: &str, args: &[String]) {
    let flags: &[&str] = match name {
        "python" => &["-c"],
        "node" | "nodejs" => &["-e", "--eval", "-p", "--print"],
        "perl" => &["-e", "-E"],
        "ruby" => &["-e"],
        "php" => &["-r"],
        "deno" => &["eval"],
        _ => &[],
    };
    let Some(at) = args.iter().position(|a| flags.contains(&a.as_str())) else { return };
    cx.add(Category::InterpreterExec, format!("{name} runs inline code"));
    if args.get(at + 1).is_some_and(|code| SPAWNS_SHELL.is_match(code)) {
        cx.add(Category::InterpreterShell, format!("the inline {name} code starts a shell command"));
    }
}

fn is_fetch(inv: &Invocation) -> bool {
    inv.name().is_some_and(|n| FETCHERS.contains(&n))
}

fn is_decoder(inv: &Invocation) -> bool {
    let args = texts(inv);
    match inv.name() {
        Some("base64") => has_short(&args, 'd') || has_short(&args, 'D') || has_long(&args, "decode"),
        Some("xxd") => has_short(&args, 'r'),
        Some("openssl") => args.iter().any(|a| a == "-d") && args.iter().any(|a| a == "enc" || a == "base64"),
        Some("uudecode" | "basenc") => true,
        Some("printf" | "echo") => inv.args().iter().any(|w| w.raw.contains("\\x") || w.raw.contains("\\0")),
        _ => false,
    }
}

/// Whether the invocation runs text it is given: a shell or interpreter reading its input, `eval`, `source`.
fn runs_given_text(inv: &Invocation) -> bool {
    let Some(name) = inv.name() else { return false };
    let name = base_name(name);
    let args = texts(inv);
    if SHELLS.contains(&name) {
        return !args.iter().any(|a| !a.starts_with('-') || a == "-") || has_short(&args, 'c');
    }
    if INTERPRETERS.contains(&name) {
        return args.is_empty() || args == ["-"];
    }
    matches!(name, "eval" | "source" | ".")
}

fn stage_has(cx: &Cx<'_>, stage: &[usize], test: impl Fn(&Invocation) -> bool) -> bool {
    stage.iter().filter_map(|i| cx.parsed.invocations.get(*i)).any(test)
}

fn pipelines(cx: &mut Cx<'_>) {
    let pipelines = cx.parsed.pipelines.clone();
    for stages in pipelines {
        for (earlier, stage) in stages.iter().enumerate() {
            let source_fetches = stage_has(cx, stage, is_fetch);
            let source_decodes = stage_has(cx, stage, is_decoder);
            if !source_fetches && !source_decodes {
                continue;
            }
            for later in stages.iter().skip(earlier + 1) {
                if !stage_has(cx, later, |i| {
                    runs_given_text(i)
                        && i.name()
                            .is_some_and(|n| SHELLS.contains(&base_name(n)) || INTERPRETERS.contains(&base_name(n)))
                }) {
                    continue;
                }
                if source_fetches {
                    cx.add(Category::RemoteExec, "downloaded text is piped into a shell or interpreter");
                }
                if source_decodes {
                    cx.add(Category::Obfuscation, "decoded text is piped into a shell or interpreter");
                }
            }
        }
    }
}

/// `bash <(curl ...)`, `sh -c "$(curl ...)"`, `eval "$(... | base64 -d)"`: what feeds a command that runs text.
fn sinks(cx: &mut Cx<'_>, inv: &Invocation, name: &str) {
    if !(SHELLS.contains(&name) || INTERPRETERS.contains(&name) || matches!(name, "eval" | "source" | ".")) {
        return;
    }
    let mut feeders: Vec<usize> = inv.process_substitutions.iter().flatten().copied().collect();
    for word in inv.args() {
        feeders.extend(word.substitutions.iter().copied());
    }
    let mut remote = false;
    let mut decoded = false;
    for at in feeders {
        if let Some(feeder) = cx.parsed.invocations.get(at) {
            remote |= is_fetch(feeder);
            decoded |= is_decoder(feeder);
        }
    }
    if remote {
        cx.add(Category::RemoteExec, format!("{name} runs text downloaded by a command inside its arguments"));
    }
    if decoded {
        cx.add(Category::Obfuscation, format!("{name} runs decoded text"));
    }
}
