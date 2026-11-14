#![allow(
    clippy::expect_used,
    clippy::unwrap_used,
    clippy::indexing_slicing,
    clippy::assert_is_empty,
    clippy::cast_possible_truncation
)]

mod common;

use common::{redactor, redactor_with_ip};
use warden_redact::{Config, Session};

const KEY_LINES: [&str; 5] = [
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU",
    "AAAAB3NzaC1yc2EAAAADAQABAAABAQC7",
    "-----END OPENSSH PRIVATE KEY-----",
    "ssh-ed25519 is a public key type",
];

#[test]
fn redact_swaps_values_for_tokens_and_counts_them() {
    let r = redactor();
    let mut session = Session::in_memory();
    let (out, counts) =
        r.redact(&mut session, "mail alice@acme.fr and bob@acme.fr, again alice@acme.fr, key AKIAIOSFODNN7EXAMPLE");
    assert_eq!(out, "mail <EMAIL_1> and <EMAIL_2>, again <EMAIL_1>, key <SECRET_1>");
    assert_eq!(counts.iter().collect::<Vec<_>>(), vec![("aws_access_key", 1), ("email", 3)]);
}

#[test]
fn restore_brings_values_back_and_leaves_unknown_tokens_alone() {
    let r = redactor();
    let mut session = Session::in_memory();
    r.redact(&mut session, "alice@acme.fr");
    let (out, n) = r.restore(&session, "to <EMAIL_1>, cc <EMAIL_9>, <EMAIL_1> and <NOPE_1> and <not a token>");
    assert_eq!(out, "to alice@acme.fr, cc <EMAIL_9>, alice@acme.fr and <NOPE_1> and <not a token>");
    assert_eq!(n, 2);
    assert_eq!(r.restore(&session, "nothing here"), ("nothing here".to_owned(), 0));
}

#[test]
fn redact_then_restore_round_trips_a_mixed_text() {
    let r = redactor_with_ip();
    let mut session = Session::in_memory();
    let text = format!(
        "# deploy notes\nserver 203.0.113.7, contact alice@acme.fr or +33 6 12 34 56 78\nDB_PASSWORD=Sup3rS3cret!x\n\
         card 4539 1488 0343 6467, iban GB82 WEST 1234 5698 7654 32, nir 1 85 05 78 006 084 91\n{}\nbye",
        KEY_LINES[..4].join("\n")
    );
    let (redacted, counts) = r.redact(&mut session, &text);
    for secret in ["203.0.113.7", "alice@acme.fr", "Sup3rS3cret!x", "4539 1488", "GB82", "006 084", "b3BlbnNz", "+33 6"]
    {
        assert!(!redacted.contains(secret), "{secret} leaked into {redacted}");
    }
    assert_eq!(counts.total(), 8, "{counts:?}");
    assert!(
        redacted.starts_with("# deploy notes\nserver <IP_1>, contact <EMAIL_1> or <PHONE_1>\nDB_PASSWORD=<SECRET_1>\n")
    );
    let (restored, n) = r.restore(&session, &redacted);
    assert_eq!(restored, text);
    assert_eq!(n, 8);
}

#[test]
fn a_private_key_block_in_one_string_is_one_secret() {
    let r = redactor();
    let mut session = Session::in_memory();
    let block = KEY_LINES[..4].join("\n");
    let (out, counts) = r.redact(&mut session, &format!("before\n{block}\nafter"));
    assert_eq!(out, "before\n<SECRET_1>\nafter");
    assert_eq!(counts.iter().collect::<Vec<_>>(), vec![("private_key", 1)]);
    assert_eq!(session.value_of("<SECRET_1>"), Some(block.as_str()));
}

#[test]
fn a_private_key_block_as_a_stream_becomes_one_token_and_empty_lines() {
    let r = redactor();
    let mut session = Session::in_memory();
    let mut lines = r.line_redactor();
    let mut out = Vec::new();
    let mut total = warden_redact::Counts::new();
    for line in KEY_LINES {
        let (redacted, counts) = lines.redact_line(&r, &mut session, line);
        out.push(redacted);
        total.merge(&counts);
    }
    assert_eq!(out, vec!["<SECRET_1>", "", "", "", "ssh-ed25519 is a public key type"]);
    assert_eq!(total.iter().collect::<Vec<_>>(), vec![("private_key", 1)]);
    assert_eq!(session.value_of("<SECRET_1>"), Some(KEY_LINES[..4].join("\n").as_str()));
    let (restored, n) = r.restore(&session, &out[0]);
    assert_eq!((restored.as_str(), n), (KEY_LINES[..4].join("\n").as_str(), 1));
    // the stream is over the block: ordinary lines are redacted as usual again
    let (line, _) = lines.redact_line(&r, &mut session, "mail alice@acme.fr");
    assert_eq!(line, "mail <EMAIL_1>");
}

#[test]
fn a_stream_of_a_key_that_never_ends_stays_inside_the_block() {
    let r = redactor();
    let mut session = Session::in_memory();
    let mut lines = r.line_redactor();
    let (first, _) = lines.redact_line(&r, &mut session, "-----BEGIN PRIVATE KEY-----");
    let (second, counts) = lines.redact_line(&r, &mut session, "MIIEvQIBADANBgkq");
    assert_eq!((first.as_str(), second.as_str()), ("<SECRET_1>", ""));
    assert!(counts.is_empty());
    assert_eq!(session.value_of("<SECRET_1>"), Some("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkq"));
}

#[test]
fn a_complete_key_on_one_line_is_redacted_like_any_text() {
    let r = redactor();
    let mut session = Session::in_memory();
    let mut lines = r.line_redactor();
    let (out, _) = lines.redact_line(&r, &mut session, "k=-----BEGIN PRIVATE KEY----- abc -----END PRIVATE KEY-----");
    assert_eq!(out, "k=<SECRET_1>");
    let (next, _) = lines.redact_line(&r, &mut session, "plain line");
    assert_eq!(next, "plain line");
}

#[test]
fn text_around_matches_may_be_multi_byte() {
    let r = redactor();
    let mut session = Session::in_memory();
    let text = "café ☕ 日本語 alice@acme.fr 🎉🎉 06 12 34 56 78 ñandú — DB_PASSWORD=Sup3rS3cret!x fin";
    let (out, counts) = r.redact(&mut session, text);
    assert_eq!(out, "café ☕ 日本語 <EMAIL_1> 🎉🎉 <PHONE_1> ñandú — DB_PASSWORD=<SECRET_1> fin");
    assert_eq!(counts.total(), 3);
    assert_eq!(r.restore(&session, &out).0, text);
    for hit in r.find(text) {
        assert!(text.is_char_boundary(hit.start) && text.is_char_boundary(hit.end));
    }
}

#[test]
fn a_name_with_accents_and_case_folding_is_found() {
    let config = Config {
        pii: warden_redact::PiiConfig { names: vec!["Élodie Brûlé".to_owned()], ..Default::default() },
        ..Config::default()
    };
    let r = warden_redact::Redactor::new(config).unwrap();
    let mut session = Session::in_memory();
    let (out, _) = r.redact(&mut session, "merci à élodie brûlé 🙏");
    assert_eq!(out, "merci à <PERSON_1> 🙏");
}

#[test]
fn redacting_twice_changes_nothing() {
    let r = redactor_with_ip();
    let mut session = Session::in_memory();
    let text = format!(
        "alice@acme.fr, 06 12 34 56 78, 203.0.113.7, DB_PASSWORD=Sup3rS3cret!x postgres://u:p4ssW0rd!@h/db\n{}\n4539 1488 0343 6467",
        KEY_LINES[..4].join("\n")
    );
    let (once, first) = r.redact(&mut session, &text);
    let (twice, second) = r.redact(&mut session, &once);
    assert_eq!(once, twice);
    assert!(second.is_empty(), "{second:?}");
    assert!(first.total() >= 6);
}

#[test]
fn a_stream_redacted_twice_changes_nothing() {
    let r = redactor();
    let mut session = Session::in_memory();
    let mut first_pass = Vec::new();
    let mut lines = r.line_redactor();
    for line in KEY_LINES {
        first_pass.push(lines.redact_line(&r, &mut session, line).0);
    }
    let mut lines = r.line_redactor();
    let second_pass: Vec<String> = first_pass.iter().map(|l| lines.redact_line(&r, &mut session, l).0).collect();
    assert_eq!(first_pass, second_pass);
}

#[test]
fn an_empty_string_is_fine() {
    let r = redactor_with_ip();
    let mut session = Session::in_memory();
    assert!(r.find("").is_empty());
    assert_eq!(r.redact(&mut session, "").0, "");
    assert_eq!(r.restore(&session, ""), (String::new(), 0));
    assert_eq!(r.line_redactor().redact_line(&r, &mut session, "").0, "");
}

/// A deterministic mix of ascii, separators, digits and multi-byte characters, with now and then something that
/// looks like a secret, so that every detector has work to do.
fn noisy_text(bytes: usize) -> String {
    const PIECES: [&str; 24] = [
        "alpha",
        " ",
        "-",
        ".",
        "@",
        "=",
        ":",
        "0123",
        "9",
        "é",
        "日本",
        "🎉",
        "\n",
        "AKIA",
        "ghp_",
        "password",
        "+33 ",
        "4539 1488 0343 6467",
        "10.",
        "eyJ",
        "Bearer ",
        "://",
        "<b>",
        "-----BEGIN PRIVATE KEY-----",
    ];
    let mut state: u64 = 0x2545_F491_4F6C_DD1D;
    let mut text = String::with_capacity(bytes + 32);
    while text.len() < bytes {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        text.push_str(PIECES[(state % PIECES.len() as u64) as usize]);
    }
    text
}

#[test]
fn a_large_arbitrary_text_does_not_panic_and_round_trips() {
    let r = redactor_with_ip();
    let text = noisy_text(200 * 1024);
    assert!(text.len() >= 200 * 1024);
    let mut session = Session::in_memory();
    let (out, counts) = r.redact(&mut session, &text);
    assert!(counts.total() > 0);
    // idempotence is not promised on noise (a neighbour that was replaced can change what a number runs into), but
    // putting the values back always gives the text back
    assert_eq!(r.restore(&session, &out).0, text);
    let mut lines = r.line_redactor();
    for line in text.lines() {
        let _ = lines.redact_line(&r, &mut session, line);
    }
}
