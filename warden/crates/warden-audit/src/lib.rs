//! The audit log: one line per decision, each carrying the hash of the line before it.
//!
//! Records are JSON lines in one file per day. A record holds a digest of what was judged and a short summary, never
//! a redacted value, a prompt or the content of a file. Because each record is hashed together with the previous
//! hash, removing or changing a line breaks the chain, and [`AuditLog::verify`] names the first line that does.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// The hash a chain starts from.
const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";

/// How much of a summary is kept.
const SUMMARY_LIMIT: usize = 200;

/// What a caller says happened. The log adds the time and the chain.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Entry {
    /// The agent: `claude`, `codex`, `opencode`, `copilot`, `shim`.
    pub agent: String,
    /// The session the agent reported.
    pub session: String,
    /// The hook event: `PreToolUse`, `UserPromptSubmit`, `Run`...
    pub event: String,
    /// The tool the agent used.
    pub tool: String,
    /// What kind of tool it is: `bash`, `read`, `write`, `web`, `mcp`...
    pub kind: String,
    /// The working directory.
    pub cwd: String,
    /// A short digest of the input, so a record can be matched to a command without storing more.
    pub input_sha256: String,
    /// The command line or the path, shortened. The caller redacts it first.
    pub summary: String,
    /// The risk categories that were found.
    pub categories: Vec<String>,
    /// What happened: `allow`, `ask`, `deny`, or `redacted` for a run that changed output.
    pub decision: String,
    /// What the policy decided, when that is not what happened (audit mode, nobody to ask).
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub intended: String,
    /// Why.
    pub reason: String,
    /// The layers of the policy that were in force.
    pub policy: String,
    /// `enforce` or `audit`.
    pub mode: String,
    /// How many values of each kind were redacted.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub redactions: BTreeMap<String, usize>,
}

/// A line of the log.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Record {
    /// When, in UTC, to the millisecond.
    pub ts: String,
    /// The hash of the previous record.
    pub prev: String,
    /// The hash of this one.
    pub hash: String,
    /// What was recorded.
    #[serde(flatten)]
    pub entry: Entry,
}

impl Record {
    fn digest(prev: &str, ts: &str, entry: &Entry) -> io::Result<String> {
        let unsigned = Self { ts: ts.to_owned(), prev: prev.to_owned(), hash: String::new(), entry: entry.clone() };
        let text = serde_json::to_string(&unsigned).map_err(io::Error::other)?;
        let mut hasher = Sha256::new();
        hasher.update(text.as_bytes());
        Ok(to_hex(&hasher.finalize()))
    }

    /// Whether the hash of this record is the one its content and previous hash give.
    #[must_use]
    pub fn is_intact(&self) -> bool {
        Self::digest(&self.prev, &self.ts, &self.entry).is_ok_and(|hash| hash == self.hash)
    }
}

fn to_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(char::from(DIGITS[usize::from(byte >> 4)]));
        out.push(char::from(DIGITS[usize::from(byte & 0x0f)]));
    }
    out
}

/// A short digest of an input, for [`Entry::input_sha256`].
#[must_use]
pub fn digest_of(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    to_hex(&hasher.finalize()).chars().take(16).collect()
}

/// A summary shortened to what a log line should hold.
#[must_use]
pub fn shorten(text: &str) -> String {
    let single: String = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if single.chars().count() <= SUMMARY_LIMIT {
        return single;
    }
    let cut: String = single.chars().take(SUMMARY_LIMIT).collect();
    format!("{cut}...")
}

/// `2026-11-14T09:30:05.123Z` for a point in time.
#[must_use]
pub fn rfc3339(time: SystemTime) -> String {
    let since = time.duration_since(UNIX_EPOCH).unwrap_or_default();
    let seconds = i64::try_from(since.as_secs()).unwrap_or(i64::MAX);
    let (days, rest) = (seconds.div_euclid(86_400), seconds.rem_euclid(86_400));
    // Civil date from a day count (Howard Hinnant's algorithm).
    let shifted = days + 719_468;
    let era = shifted.div_euclid(146_097);
    let day_of_era = shifted.rem_euclid(146_097);
    let year_of_era = (day_of_era - day_of_era / 1460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month = if month_index < 10 { month_index + 3 } else { month_index - 9 };
    let year = year_of_era + era * 400 + i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{:03}Z",
        rest / 3600,
        rest % 3600 / 60,
        rest % 60,
        since.subsec_millis()
    )
}

/// Which records to read.
#[derive(Debug, Clone, Default)]
pub struct Filter {
    /// Only this session.
    pub session: Option<String>,
    /// Only the most recent this many.
    pub last: Option<usize>,
}

/// What [`AuditLog::verify`] found.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Verification {
    /// How many files were read.
    pub files: usize,
    /// How many records were read.
    pub records: usize,
    /// The first problem, if the chain is broken.
    pub problem: Option<Problem>,
}

/// A broken link of the chain.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Problem {
    /// The file.
    pub file: String,
    /// The line, from 1.
    pub line: usize,
    /// What is wrong.
    pub what: String,
}

/// A count of what the log holds.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Summary {
    /// How many records.
    pub total: usize,
    /// How many of each decision; a decision that audit mode let through is counted as `allow(audit)`.
    pub decisions: BTreeMap<String, usize>,
    /// How many values of each kind were redacted.
    pub redactions: BTreeMap<String, usize>,
}

/// Count what a list of records holds.
#[must_use]
pub fn summarize(records: &[Record]) -> Summary {
    let mut summary = Summary { total: records.len(), ..Summary::default() };
    for record in records {
        *summary.decisions.entry(label(record)).or_default() += 1;
        for (kind, count) in &record.entry.redactions {
            *summary.redactions.entry(kind.clone()).or_default() += count;
        }
    }
    summary
}

/// The decision of a record as a person reads it: `allow(audit)` when audit mode let through what would have been
/// stopped.
#[must_use]
pub fn label(record: &Record) -> String {
    let entry = &record.entry;
    if entry.mode == "audit" && !entry.intended.is_empty() && entry.intended != entry.decision {
        format!("{}(audit)", entry.decision)
    } else {
        entry.decision.clone()
    }
}

/// The log in a directory.
#[derive(Debug, Clone)]
pub struct AuditLog {
    dir: PathBuf,
}

impl AuditLog {
    /// The log kept in `dir`; the directory is created when the first record is written.
    #[must_use]
    pub fn new(dir: impl Into<PathBuf>) -> Self {
        Self { dir: dir.into() }
    }

    /// The directory.
    #[must_use]
    pub fn dir(&self) -> &Path {
        &self.dir
    }

    fn chain_file(&self) -> PathBuf {
        self.dir.join(".chain")
    }

    /// Add a record, stamped now.
    pub fn append(&self, entry: &Entry) -> io::Result<Record> {
        self.append_at(entry, SystemTime::now())
    }

    /// Add a record stamped with `time`. Several processes may write at once: the chain is extended under a lock.
    pub fn append_at(&self, entry: &Entry, time: SystemTime) -> io::Result<Record> {
        fs::create_dir_all(&self.dir)?;
        let lock = OpenOptions::new().create(true).truncate(false).write(true).open(self.dir.join(".lock"))?;
        lock.lock()?;
        let result = self.append_locked(entry, time);
        let _ = lock.unlock();
        result
    }

    fn append_locked(&self, entry: &Entry, time: SystemTime) -> io::Result<Record> {
        let prev =
            fs::read_to_string(self.chain_file()).map_or_else(|_| GENESIS.to_owned(), |text| text.trim().to_owned());
        let ts = rfc3339(time);
        let hash = Record::digest(&prev, &ts, entry)?;
        let record = Record { ts: ts.clone(), prev, hash: hash.clone(), entry: entry.clone() };
        let line = serde_json::to_string(&record).map_err(io::Error::other)?;
        let file_name = format!("{}.jsonl", ts.get(..10).unwrap_or("unknown"));
        let mut file = open_private(&self.dir.join(file_name))?;
        writeln!(file, "{line}")?;
        file.flush()?;
        let mut chain = open_private_truncated(&self.chain_file())?;
        write!(chain, "{hash}")?;
        Ok(record)
    }

    fn files(&self) -> io::Result<Vec<PathBuf>> {
        let mut files: Vec<PathBuf> = match fs::read_dir(&self.dir) {
            Ok(entries) => entries
                .filter_map(Result::ok)
                .map(|e| e.path())
                .filter(|p| p.extension().is_some_and(|ext| ext == "jsonl"))
                .collect(),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Vec::new(),
            Err(error) => return Err(error),
        };
        files.sort();
        Ok(files)
    }

    /// Read records, oldest first.
    pub fn read(&self, filter: &Filter) -> io::Result<Vec<Record>> {
        let mut records = Vec::new();
        for path in self.files()? {
            for line in BufReader::new(File::open(&path)?).lines() {
                let line = line?;
                if line.trim().is_empty() {
                    continue;
                }
                if let Ok(record) = serde_json::from_str::<Record>(&line)
                    && filter.session.as_ref().is_none_or(|s| *s == record.entry.session)
                {
                    records.push(record);
                }
            }
        }
        if let Some(last) = filter.last {
            let skip = records.len().saturating_sub(last);
            records.drain(..skip);
        }
        Ok(records)
    }

    /// Walk the chain and name the first line that does not belong.
    pub fn verify(&self) -> io::Result<Verification> {
        let mut previous = GENESIS.to_owned();
        let (mut files, mut records) = (0, 0);
        for path in self.files()? {
            files += 1;
            let name = path.file_name().map_or_else(String::new, |n| n.to_string_lossy().into_owned());
            for (index, line) in BufReader::new(File::open(&path)?).lines().enumerate() {
                let line = line?;
                let problem = |what: &str| Verification {
                    files,
                    records,
                    problem: Some(Problem { file: name.clone(), line: index + 1, what: what.to_owned() }),
                };
                let Ok(record) = serde_json::from_str::<Record>(&line) else {
                    return Ok(problem("the line is not a record"));
                };
                if record.prev != previous {
                    return Ok(problem("the record does not follow the one before it: a line was removed or changed"));
                }
                if !record.is_intact() {
                    return Ok(problem("the record was changed after it was written"));
                }
                previous = record.hash;
                records += 1;
            }
        }
        if let Ok(text) = fs::read_to_string(self.chain_file())
            && text.trim() != previous
            && records > 0
        {
            return Ok(Verification {
                files,
                records,
                problem: Some(Problem {
                    file: ".chain".to_owned(),
                    line: 0,
                    what: "the last record is not the one the chain ends on: records were removed from the end"
                        .to_owned(),
                }),
            });
        }
        Ok(Verification { files, records, problem: None })
    }
}

#[cfg(unix)]
fn open_private(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new().create(true).append(true).mode(0o600).open(path)
}

#[cfg(not(unix))]
fn open_private(path: &Path) -> io::Result<File> {
    OpenOptions::new().create(true).append(true).open(path)
}

#[cfg(unix)]
fn open_private_truncated(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new().create(true).write(true).truncate(true).mode(0o600).open(path)
}

#[cfg(not(unix))]
fn open_private_truncated(path: &Path) -> io::Result<File> {
    OpenOptions::new().create(true).write(true).truncate(true).open(path)
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("warden-audit-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        dir
    }

    fn entry(decision: &str, session: &str) -> Entry {
        Entry {
            agent: "claude".into(),
            session: session.into(),
            event: "PreToolUse".into(),
            tool: "Bash".into(),
            kind: "bash".into(),
            cwd: "/work/app".into(),
            input_sha256: digest_of("ls"),
            summary: "ls".into(),
            decision: decision.into(),
            reason: "no risky pattern".into(),
            policy: "preset:guarded".into(),
            mode: "enforce".into(),
            ..Entry::default()
        }
    }

    #[test]
    fn a_time_is_written_as_utc_to_the_millisecond() {
        assert_eq!(rfc3339(UNIX_EPOCH), "1970-01-01T00:00:00.000Z");
        let leap = UNIX_EPOCH + Duration::from_millis(1_709_164_800_123);
        assert_eq!(rfc3339(leap), "2024-02-29T00:00:00.123Z");
        let later = UNIX_EPOCH + Duration::from_secs(1_794_648_605);
        assert_eq!(rfc3339(later), "2026-11-14T09:30:05.000Z");
    }

    #[test]
    fn records_chain_to_each_other_and_verify() {
        let dir = temp_dir("chain");
        let log = AuditLog::new(&dir);
        let first = log.append(&entry("allow", "s1")).expect("first");
        let second = log.append(&entry("deny", "s1")).expect("second");
        assert_eq!(first.prev.len(), 64);
        assert_eq!(second.prev, first.hash);
        let verification = log.verify().expect("verifies");
        assert_eq!((verification.records, verification.problem), (2, None));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_changed_line_is_named() {
        let dir = temp_dir("changed");
        let log = AuditLog::new(&dir);
        for decision in ["allow", "deny", "allow"] {
            log.append(&entry(decision, "s")).expect("append");
        }
        let file = log.files().expect("files").remove(0);
        let text = fs::read_to_string(&file).expect("read");
        fs::write(&file, text.replacen("\"deny\"", "\"allow\"", 1)).expect("tamper");
        let problem = log.verify().expect("verifies").problem.expect("a problem");
        assert_eq!(problem.line, 2);
        assert!(problem.what.contains("changed"), "{}", problem.what);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_removed_line_in_the_middle_and_at_the_end_are_both_named() {
        let dir = temp_dir("removed");
        let log = AuditLog::new(&dir);
        for _ in 0..4 {
            log.append(&entry("allow", "s")).expect("append");
        }
        let file = log.files().expect("files").remove(0);
        let lines: Vec<String> = fs::read_to_string(&file).expect("read").lines().map(str::to_owned).collect();

        fs::write(&file, format!("{}\n{}\n{}\n", lines[0], lines[2], lines[3])).expect("remove the second");
        let problem = log.verify().expect("verifies").problem.expect("a problem");
        assert_eq!(problem.line, 2);
        assert!(problem.what.contains("removed or changed"), "{}", problem.what);

        fs::write(&file, format!("{}\n{}\n{}\n", lines[0], lines[1], lines[2])).expect("remove the last");
        let problem = log.verify().expect("verifies").problem.expect("a problem");
        assert_eq!(problem.file, ".chain");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn an_empty_or_missing_log_verifies() {
        let log = AuditLog::new(temp_dir("empty"));
        let verification = log.verify().expect("verifies");
        assert_eq!((verification.files, verification.records, verification.problem), (0, 0, None));
        assert_eq!(log.read(&Filter::default()).expect("reads"), Vec::new());
    }

    #[test]
    fn days_go_to_their_own_files_and_the_chain_runs_across_them() {
        let dir = temp_dir("days");
        let log = AuditLog::new(&dir);
        let day = UNIX_EPOCH + Duration::from_secs(1_794_648_605);
        log.append_at(&entry("allow", "s"), day).expect("day one");
        log.append_at(&entry("allow", "s"), day + Duration::from_secs(86_400)).expect("day two");
        let names: Vec<String> =
            log.files().expect("files").iter().filter_map(|p| p.file_name()?.to_str().map(str::to_owned)).collect();
        assert_eq!(names, ["2026-11-14.jsonl", "2026-11-15.jsonl"]);
        assert_eq!(log.verify().expect("verifies").problem, None);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn reading_can_pick_a_session_and_the_latest() {
        let dir = temp_dir("read");
        let log = AuditLog::new(&dir);
        for (decision, session) in [("allow", "a"), ("deny", "b"), ("ask", "a"), ("allow", "a")] {
            log.append(&entry(decision, session)).expect("append");
        }
        let only_a = log.read(&Filter { session: Some("a".into()), last: None }).expect("reads");
        assert_eq!(only_a.len(), 3);
        let last_two = log.read(&Filter { session: None, last: Some(2) }).expect("reads");
        assert_eq!(last_two.iter().map(|r| r.entry.decision.as_str()).collect::<Vec<_>>(), ["ask", "allow"]);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_summary_counts_decisions_and_marks_what_audit_mode_let_through() {
        let dir = temp_dir("summary");
        let log = AuditLog::new(&dir);
        log.append(&entry("allow", "s")).expect("allow");
        let mut observed = entry("allow", "s");
        observed.mode = "audit".into();
        observed.intended = "deny".into();
        log.append(&observed).expect("audit");
        let mut redacted = entry("redacted", "s");
        redacted.redactions.insert("email".into(), 2);
        log.append(&redacted).expect("redacted");
        let summary = summarize(&log.read(&Filter::default()).expect("reads"));
        assert_eq!(summary.total, 3);
        assert_eq!(summary.decisions["allow"], 1);
        assert_eq!(summary.decisions["allow(audit)"], 1);
        assert_eq!(summary.redactions["email"], 2);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_summary_is_short_and_one_line() {
        assert_eq!(shorten("a  b\n c"), "a b c");
        let long = "x".repeat(500);
        let short = shorten(&long);
        assert_eq!(short.chars().count(), SUMMARY_LIMIT + 3);
        assert!(short.ends_with("..."));
        assert_eq!(shorten("héllo wörld 🚀"), "héllo wörld 🚀");
    }

    #[cfg(unix)]
    #[test]
    fn the_files_are_private() {
        use std::os::unix::fs::PermissionsExt;
        let dir = temp_dir("mode");
        let log = AuditLog::new(&dir);
        log.append(&entry("allow", "s")).expect("append");
        for path in log.files().expect("files").into_iter().chain([log.chain_file()]) {
            let mode = fs::metadata(&path).expect("metadata").permissions().mode() & 0o777;
            assert_eq!(mode, 0o600, "{}", path.display());
        }
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn concurrent_writers_keep_one_chain() {
        let dir = temp_dir("threads");
        let log = AuditLog::new(&dir);
        let handles: Vec<_> = (0..4)
            .map(|n| {
                let log = log.clone();
                std::thread::spawn(move || {
                    for _ in 0..10 {
                        log.append(&entry("allow", &format!("t{n}"))).expect("append");
                    }
                })
            })
            .collect();
        for handle in handles {
            handle.join().expect("thread");
        }
        let verification = log.verify().expect("verifies");
        assert_eq!((verification.records, verification.problem), (40, None));
        let _ = fs::remove_dir_all(dir);
    }
}
