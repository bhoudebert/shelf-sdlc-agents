#![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

use std::path::Path;

use warden_engine::Context;
use warden_engine::corpus::{Corpus, run};
use warden_policy::{Layer, Policy, Profile};

fn context() -> Context {
    Context { home: "/home/dev".into(), cwd: "/work/app".into() }
}

fn policy(profile: &str) -> Policy {
    let layer = Layer::parse(&format!("profile = \"{profile}\"")).expect("layer");
    Policy::resolve(&[("test".to_owned(), layer)], Path::new("/home/dev")).expect("policy")
}

fn corpus(path: &str) -> Corpus {
    let text = std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpus").join(path))
        .expect("corpus file");
    Corpus::parse(&text).expect("corpus parses")
}

#[test]
fn the_guarded_corpus_holds() {
    let corpus = corpus("guarded.toml");
    assert_eq!(corpus.profile, Some(Profile::Guarded));
    let mismatches = run(&policy("guarded"), &context(), &corpus);
    let report: Vec<String> = mismatches
        .iter()
        .map(|m| format!("{:?}: expected {}, got {} ({})", m.cmd, m.expected, m.actual, m.reason))
        .collect();
    assert!(mismatches.is_empty(), "\n{}", report.join("\n"));
}

#[test]
fn the_unattended_corpus_holds_and_nothing_in_it_asks() {
    let corpus = corpus("unattended.toml");
    assert_eq!(corpus.profile, Some(Profile::Unattended));
    assert!(corpus.cases.iter().all(|case| case.expect != warden_policy::Decision::Ask));
    let mismatches = run(&policy("unattended"), &context(), &corpus);
    let report: Vec<String> = mismatches
        .iter()
        .map(|m| format!("{:?}: expected {}, got {} ({})", m.cmd, m.expected, m.actual, m.reason))
        .collect();
    assert!(mismatches.is_empty(), "\n{}", report.join("\n"));
}

#[test]
fn shelf_decides_like_unattended() {
    let corpus = corpus("unattended.toml");
    let mismatches = run(&policy("shelf"), &context(), &corpus);
    assert_eq!(mismatches.len(), 0, "{mismatches:?}");
}
