//! Records that a command inside an agent's sandbox could not write to the audit log.
//!
//! A sandboxed command may write only in its temporary and working directories, so `warden run` leaves its audit record
//! next to the session's token file. The next hook, which runs outside the sandbox, moves the records into the log.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use warden_audit::Entry;

use crate::run::session_path;

fn spool_path(session_dir: &Path, session: &str) -> PathBuf {
    session_path(session_dir, session).with_extension("spool")
}

/// Keep `entry` until a hook can write it to the audit log.
pub fn push(session_dir: &Path, session: &str, entry: &Entry) -> io::Result<()> {
    fs::create_dir_all(session_dir)?;
    let line = serde_json::to_string(entry).map_err(io::Error::other)?;
    let mut file = open_private(&spool_path(session_dir, session))?;
    writeln!(file, "{line}")
}

/// Take the records kept for a session; what could not be read is dropped.
pub fn drain(session_dir: &Path, session: &str) -> Vec<Entry> {
    let path = spool_path(session_dir, session);
    if !path.is_file() {
        return Vec::new();
    }
    let taken = path.with_extension("spool.reading");
    if fs::rename(&path, &taken).is_err() {
        return Vec::new();
    }
    let text = fs::read_to_string(&taken).unwrap_or_default();
    let _ = fs::remove_file(&taken);
    text.lines().filter_map(|line| serde_json::from_str(line).ok()).collect()
}

#[cfg(unix)]
fn open_private(path: &Path) -> io::Result<fs::File> {
    use std::os::unix::fs::OpenOptionsExt;
    fs::OpenOptions::new().create(true).append(true).mode(0o600).open(path)
}

#[cfg(not(unix))]
fn open_private(path: &Path) -> io::Result<fs::File> {
    fs::OpenOptions::new().create(true).append(true).open(path)
}

/// Say something about a degraded state on the error output, only when `WARDEN_DEBUG` is set: what a command prints
/// there goes to the model, and a guard's own troubles are not for it.
pub fn note(message: &str) {
    if std::env::var_os("WARDEN_DEBUG").is_some() {
        eprintln!("warden: {message}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("warden-spool-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        dir
    }

    fn entry(summary: &str) -> Entry {
        Entry { summary: summary.into(), decision: "redacted".into(), ..Entry::default() }
    }

    #[test]
    fn records_are_kept_and_taken_once_in_order() {
        let dir = dir("roundtrip");
        push(&dir, "s1", &entry("one")).expect("push");
        push(&dir, "s1", &entry("two")).expect("push");
        push(&dir, "s2", &entry("other")).expect("push");
        let taken = drain(&dir, "s1");
        assert_eq!(taken.iter().map(|e| e.summary.as_str()).collect::<Vec<_>>(), ["one", "two"]);
        assert_eq!(drain(&dir, "s1"), Vec::new(), "a record is taken only once");
        assert_eq!(drain(&dir, "s2").len(), 1);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_line_that_is_not_a_record_is_dropped_and_nothing_is_left_behind() {
        let dir = dir("garbage");
        fs::create_dir_all(&dir).expect("dir");
        fs::write(spool_path(&dir, "s"), "not json\n").expect("file");
        push(&dir, "s", &entry("good")).expect("push");
        assert_eq!(drain(&dir, "s").len(), 1);
        assert_eq!(fs::read_dir(&dir).expect("dir").count(), 0);
        let _ = fs::remove_dir_all(dir);
    }

    #[cfg(unix)]
    #[test]
    fn the_spool_is_private() {
        use std::os::unix::fs::PermissionsExt;
        let dir = dir("mode");
        push(&dir, "s", &entry("x")).expect("push");
        let mode = fs::metadata(spool_path(&dir, "s")).expect("metadata").permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_session_with_nothing_spooled_drains_to_nothing() {
        assert_eq!(drain(&dir("none"), "s"), Vec::new());
    }
}
