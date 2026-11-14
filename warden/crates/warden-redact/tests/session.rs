#![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

use std::path::PathBuf;

use warden_redact::{Counts, Kind, Session};

/// A directory under the system temp dir that is unique to the test and removed at the end.
struct TempDir(PathBuf);

impl TempDir {
    fn new(name: &str) -> Self {
        let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let dir = std::env::temp_dir().join(format!("warden-redact-{name}-{}-{nanos}", std::process::id()));
        Self(dir)
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

#[test]
fn the_same_value_gets_the_same_token_and_a_new_one_the_next_number() {
    let mut session = Session::in_memory();
    let a = session.token_for(&Kind::Email, "a@acme.fr");
    let b = session.token_for(&Kind::Email, "b@acme.fr");
    assert_eq!(a, "<EMAIL_1>");
    assert_eq!(b, "<EMAIL_2>");
    assert_eq!(session.token_for(&Kind::Email, "a@acme.fr"), a);
    assert_eq!(session.token_for(&Kind::Secret, "hunter2hunter2"), "<SECRET_1>");
    assert_eq!(session.token_for(&Kind::Custom("customer_id".into()), "C1"), "<CUSTOMER_ID_1>");
    assert_eq!(session.len(), 4);
    assert_eq!(session.value_of("<EMAIL_2>"), Some("b@acme.fr"));
    assert_eq!(session.value_of("<EMAIL_3>"), None);
}

#[test]
fn tokens_survive_a_save_and_an_open() {
    let dir = TempDir::new("roundtrip");
    let path = dir.0.join("nested/deeper/session.json");
    let mut session = Session::open(&path).unwrap();
    assert_eq!(session.len(), 0);
    let first = session.token_for(&Kind::Email, "a@acme.fr");
    let second = session.token_for(&Kind::Email, "b@acme.fr");
    let secret = session.token_for(&Kind::Secret, "s3cr3t-value");
    session.save().unwrap();

    let mut reopened = Session::open(&path).unwrap();
    assert_eq!(reopened.len(), 3);
    assert_eq!(reopened.value_of(&first), Some("a@acme.fr"));
    assert_eq!(reopened.value_of(&second), Some("b@acme.fr"));
    assert_eq!(reopened.value_of(&secret), Some("s3cr3t-value"));
    // same values, same tokens; a new value continues the numbering
    assert_eq!(reopened.token_for(&Kind::Email, "b@acme.fr"), second);
    assert_eq!(reopened.token_for(&Kind::Email, "c@acme.fr"), "<EMAIL_3>");
    assert_eq!(reopened.token_for(&Kind::Secret, "another"), "<SECRET_2>");
    // no temporary file is left behind
    let names: Vec<_> = std::fs::read_dir(path.parent().unwrap()).unwrap().map(|e| e.unwrap().file_name()).collect();
    assert_eq!(names, vec![std::ffi::OsString::from("session.json")]);
}

#[cfg(unix)]
#[test]
fn the_saved_file_is_private() {
    use std::os::unix::fs::PermissionsExt;
    let dir = TempDir::new("mode");
    let path = dir.0.join("session.json");
    let mut session = Session::open(&path).unwrap();
    session.token_for(&Kind::Secret, "s3cr3t-value");
    session.save().unwrap();
    assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
    // and again over an existing file
    session.save().unwrap();
    assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
}

#[test]
fn a_corrupt_file_is_invalid_data() {
    let dir = TempDir::new("corrupt");
    std::fs::create_dir_all(&dir.0).unwrap();
    let path = dir.0.join("session.json");
    std::fs::write(&path, "this is not json").unwrap();
    let error = Session::open(&path).unwrap_err();
    assert_eq!(error.kind(), std::io::ErrorKind::InvalidData);
}

#[test]
fn an_in_memory_session_saves_nothing() {
    let mut session = Session::in_memory();
    session.token_for(&Kind::Secret, "x");
    session.save().unwrap();
}

#[test]
fn counts_add_merge_and_total() {
    let mut a = Counts::new();
    assert!(a.is_empty());
    a.add("email");
    a.add("email");
    a.add("jwt");
    let mut b = Counts::new();
    b.add("email");
    b.add("card");
    a.merge(&b);
    assert_eq!(a.total(), 5);
    assert!(!a.is_empty());
    assert_eq!(a.iter().collect::<Vec<_>>(), vec![("card", 1), ("email", 3), ("jwt", 1)]);
    assert_eq!(a.clone(), a);
}
