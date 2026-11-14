//! `warden run`: execute a command and redact what it prints.
//!
//! The command runs through `bash -c`; its standard output and error are read line by line and written back with
//! credentials and personal data replaced by stable tokens, so the model never sees the values. The exit code is the
//! command's own.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;

use warden_policy::Policy;
use warden_redact::{Config, Counts, CustomPattern, Kind, PiiConfig, Redactor, Session};

/// The redactor a policy asks for.
pub fn redactor_for(policy: &Policy) -> Result<Redactor, String> {
    let pii = &policy.redact.pii;
    let kinds = pii
        .kinds
        .iter()
        .filter_map(|kind| match kind.as_str() {
            "email" => Some(Kind::Email),
            "phone" => Some(Kind::Phone),
            "iban" => Some(Kind::Iban),
            "card" => Some(Kind::Card),
            "nir" => Some(Kind::Nir),
            "ssn" => Some(Kind::Ssn),
            "ip" => Some(Kind::Ip),
            _ => None,
        })
        .collect();
    Redactor::new(Config {
        secrets: policy.redact.secrets,
        pii: PiiConfig {
            enabled: pii.enabled,
            kinds,
            names: pii.names.clone(),
            allow: pii.allow.clone(),
            custom: pii
                .custom
                .iter()
                .map(|(name, pattern)| CustomPattern { name: name.clone(), pattern: pattern.clone() })
                .collect(),
        },
    })
}

/// A session id made safe to use in a file name.
fn safe_id(id: &str) -> String {
    let cleaned: String = id.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_').take(64).collect();
    if cleaned.is_empty() { "default".to_owned() } else { cleaned }
}

/// Where the token map of a session lives.
pub fn session_path(state_dir: &std::path::Path, id: &str) -> PathBuf {
    state_dir.join("sessions").join(format!("{}.json", safe_id(id)))
}

/// Whether `name` matches `pattern`, where `*` stands for any run of characters.
fn wildcard(pattern: &str, name: &str) -> bool {
    let parts: Vec<&str> = pattern.split('*').collect();
    if parts.len() == 1 {
        return pattern == name;
    }
    let mut rest = name;
    for (index, part) in parts.iter().enumerate() {
        if index == 0 {
            let Some(after) = rest.strip_prefix(part) else { return false };
            rest = after;
        } else if index == parts.len() - 1 {
            return rest.ends_with(part);
        } else if let Some(at) = rest.find(part) {
            rest = &rest[at + part.len()..];
        } else {
            return false;
        }
    }
    true
}

/// What `run` did.
pub struct Outcome {
    /// The exit code to return.
    pub code: i32,
    /// How many values were redacted, by detector.
    pub counts: Counts,
}

fn pump(
    stream: impl std::io::Read,
    mut sink: impl Write,
    redactor: &Redactor,
    session: &Mutex<Session>,
    counts: &Mutex<Counts>,
) {
    let mut lines = redactor.line_redactor();
    let mut reader = BufReader::new(stream);
    let mut buffer = Vec::new();
    loop {
        buffer.clear();
        match reader.read_until(b'\n', &mut buffer) {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
        let text = String::from_utf8_lossy(&buffer).into_owned();
        let (body, newline) = text.strip_suffix('\n').map_or((text.as_str(), ""), |body| (body, "\n"));
        let (clean, found) = match session.lock() {
            Ok(mut guard) => lines.redact_line(redactor, &mut guard, body),
            Err(_) => (String::new(), Counts::new()),
        };
        if let Ok(mut total) = counts.lock() {
            total.merge(&found);
        }
        if write!(sink, "{clean}{newline}").is_err() || sink.flush().is_err() {
            break;
        }
    }
}

/// Run `command` through `bash -c`, redacting its output with `redactor`.
pub fn run(policy: &Policy, redactor: &Redactor, session: Session, command: &str) -> (Outcome, Session) {
    let mut child = Command::new("bash");
    child.arg("-c").arg(command).env("WARDEN_ACTIVE", "1").stdin(Stdio::inherit());
    for (name, _) in std::env::vars_os().filter_map(|(k, v)| Some((k.into_string().ok()?, v))) {
        if policy.env_hide.iter().any(|pattern| wildcard(pattern, &name)) {
            child.env_remove(&name);
        }
    }
    if !policy.redact.outputs {
        let code = child.status().map_or(127, |status| status.code().unwrap_or(1));
        return (Outcome { code, counts: Counts::new() }, session);
    }
    let mut spawned = match child.stdout(Stdio::piped()).stderr(Stdio::piped()).spawn() {
        Ok(spawned) => spawned,
        Err(error) => {
            eprintln!("warden: cannot start the shell: {error}");
            return (Outcome { code: 127, counts: Counts::new() }, session);
        }
    };
    let session = Mutex::new(session);
    let counts = Mutex::new(Counts::new());
    std::thread::scope(|scope| {
        if let Some(out) = spawned.stdout.take() {
            scope.spawn(|| pump(out, std::io::stdout(), redactor, &session, &counts));
        }
        if let Some(err) = spawned.stderr.take() {
            scope.spawn(|| pump(err, std::io::stderr(), redactor, &session, &counts));
        }
    });
    let code = spawned.wait().map_or(127, |status| status.code().unwrap_or(128 + signal_of(status)));
    let session = session.into_inner().unwrap_or_default();
    let counts = counts.into_inner().unwrap_or_default();
    (Outcome { code, counts }, session)
}

#[cfg(unix)]
fn signal_of(status: std::process::ExitStatus) -> i32 {
    use std::os::unix::process::ExitStatusExt;
    status.signal().unwrap_or(0)
}

#[cfg(not(unix))]
fn signal_of(_: std::process::ExitStatus) -> i32 {
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_wildcard_matches_the_names_a_policy_hides() {
        assert!(wildcard("*_TOKEN", "GITHUB_TOKEN"));
        assert!(wildcard("AWS_*", "AWS_SECRET_ACCESS_KEY"));
        assert!(wildcard("*SECRET*", "MY_SECRET_VALUE"));
        assert!(wildcard("HOME", "HOME"));
        assert!(!wildcard("*_TOKEN", "TOKEN_FILE"));
        assert!(!wildcard("HOME", "HOMEDIR"));
    }

    #[test]
    fn a_session_id_is_made_safe_for_a_file_name() {
        assert_eq!(safe_id("abc-123_X"), "abc-123_X");
        assert_eq!(safe_id("../../etc/passwd"), "etcpasswd");
        assert_eq!(safe_id(""), "default");
    }
}
