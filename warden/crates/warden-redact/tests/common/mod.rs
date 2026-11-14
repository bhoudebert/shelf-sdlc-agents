#![allow(dead_code)]

use warden_redact::{Config, Kind, Redactor};

/// A redactor with the default configuration.
pub fn redactor() -> Redactor {
    Redactor::new(Config::default()).expect("the default configuration is valid")
}

/// A redactor that also looks for IP addresses.
pub fn redactor_with_ip() -> Redactor {
    let mut config = Config::default();
    config.pii.kinds.push(Kind::Ip);
    Redactor::new(config).expect("valid")
}

/// A redactor with no allow list, for the checks that must hold without it.
pub fn redactor_without_allow() -> Redactor {
    let mut config = Config::default();
    config.pii.allow.clear();
    Redactor::new(config).expect("valid")
}

/// What `redactor` finds in `text`, as (detector, value).
pub fn found(redactor: &Redactor, text: &str) -> Vec<(String, String)> {
    redactor.find(text).into_iter().map(|h| (h.detector, text[h.start..h.end].to_owned())).collect()
}

/// Asserts that `detector` found exactly `value` (and nothing else of that detector).
pub fn assert_found(redactor: &Redactor, text: &str, detector: &str, value: &str) {
    let all = found(redactor, text);
    let mine: Vec<&str> = all.iter().filter(|(d, _)| d == detector).map(|(_, v)| v.as_str()).collect();
    assert_eq!(mine, vec![value], "detector {detector} on {text:?}; everything found: {all:?}");
}

/// Asserts that `detector` found nothing in `text`.
pub fn assert_not_found(redactor: &Redactor, text: &str, detector: &str) {
    let all = found(redactor, text);
    assert!(all.iter().all(|(d, _)| d != detector), "detector {detector} must not fire on {text:?}; found: {all:?}");
}

/// n characters of letters and digits, the same every time.
pub fn fill(n: usize) -> String {
    "aB3dE5gH7jK9mN1pQ".chars().cycle().take(n).collect()
}
