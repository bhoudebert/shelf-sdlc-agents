#![allow(
    clippy::expect_used,
    clippy::unwrap_used,
    clippy::indexing_slicing,
    clippy::assert_is_empty,
    clippy::cast_possible_truncation
)]

mod common;

use common::{assert_found, assert_not_found, found, redactor, redactor_with_ip, redactor_without_allow};
use warden_redact::{Config, CustomPattern, Kind, PiiConfig, Redactor};

#[test]
fn email() {
    let r = redactor();
    assert_found(&r, "write to alice.martin+work@acme-corp.fr today", "email", "alice.martin+work@acme-corp.fr");
    assert_not_found(&r, "no address here, user@localhost, a@b", "email");
}

#[test]
fn email_allow_list_leaves_values_alone() {
    let r = redactor();
    for text in [
        "bob@example.com",
        "Bob@EXAMPLE.COM",
        "x@example.org",
        "noreply@github.com",
        "no-reply@acme.io",
        "git@github.com",
        "12345+octocat@users.noreply.github.com",
    ] {
        assert_not_found(&r, text, "email");
    }
    let mut config = Config::default();
    config.pii.allow = vec!["*@acme.io".to_owned()];
    let only_acme = Redactor::new(config).unwrap();
    assert_not_found(&only_acme, "bob@acme.io", "email");
    assert_found(&only_acme, "bob@example.com", "email", "bob@example.com");
}

#[test]
fn email_skips_package_specs_and_git_remotes() {
    let r = redactor_without_allow();
    assert_not_found(&r, "npm i @scope/pkg@1.2.3-beta.rc", "email");
    assert_not_found(&r, "npm i lodash@4.17.21-beta.rc", "email");
    assert_not_found(&r, "git clone git@github.com:org/repo.git", "email");
    assert_found(&r, "mail git@github.com now", "email", "git@github.com");
}

#[test]
fn phone() {
    let r = redactor();
    assert_found(&r, "call +33 6 12 34 56 78 now", "phone", "+33 6 12 34 56 78");
    assert_found(&r, "call 06 12 34 56 78.", "phone", "06 12 34 56 78");
    assert_found(&r, "tel: 06.12.34.56.78", "phone", "06.12.34.56.78");
    assert_found(&r, "tel: 01-23-45-67-89", "phone", "01-23-45-67-89");
    assert_found(&r, "us +1 415 555 2671 ok", "phone", "+1 415 555 2671");
    assert_found(&r, "+33612345678", "phone", "+33612345678");
}

#[test]
fn phone_rejects_dates_versions_and_short_numbers() {
    let r = redactor();
    for text in [
        "version 1.2.3",
        "released 2024-01-02",
        "on 02/01/2024",
        "v1.01.02.03.04.05",
        "1.01.02.03.04.05",
        "03-04-2024 10:20",
        "+33 12",
        "call 0612345",
        "a+33 6 12 34 56 78",
        "06 12 34 56 78 90 12",
    ] {
        assert_not_found(&r, text, "phone");
    }
}

#[test]
fn iban_needs_the_mod_97_check() {
    // GB82 WEST 1234 5698 7654 32 -> 'WEST12345698765432' + 'GB82' with W=32 E=14 S=28 T=29 G=16 B=11:
    // 3214282912345698765432161182 mod 97 = 1: valid.
    // GB83 ... ends in ...161183, which is 2 mod 97: invalid.
    let r = redactor();
    assert_found(&r, "IBAN: GB82 WEST 1234 5698 7654 32 please", "iban", "GB82 WEST 1234 5698 7654 32");
    assert_found(&r, "GB82WEST12345698765432", "iban", "GB82WEST12345698765432");
    // 30006000011234567890189 + 152776 (F=15, R=27, 76) = 30006000011234567890189152776 mod 97 = 1
    assert_found(&r, "FR76 3000 6000 0112 3456 7890 189", "iban", "FR76 3000 6000 0112 3456 7890 189");
    assert_not_found(&r, "IBAN: GB83 WEST 1234 5698 7654 32 please", "iban");
    assert_not_found(&r, "FR12 ABCD EFGH IJKL", "iban");
}

#[test]
fn iban_gives_back_a_word_that_follows_it() {
    let r = redactor();
    assert_found(&r, "DE89 3704 0044 0532 0130 00 DONE", "iban", "DE89 3704 0044 0532 0130 00");
}

#[test]
fn card_needs_the_luhn_check() {
    // 4539 1488 0343 6467, read from the right with every second digit doubled (minus 9 when the double is above 9):
    // 7 3 4 3 3 8 3 0 8 7 4 2 9 6 5 8 add up to 80, a multiple of 10. Ending in 8 instead of 7 the total is 81.
    let r = redactor();
    assert_found(&r, "card 4539 1488 0343 6467 expires", "card", "4539 1488 0343 6467");
    assert_found(&r, "4539148803436467", "card", "4539148803436467");
    assert_found(&r, "4539-1488-0343-6467", "card", "4539-1488-0343-6467");
    assert_not_found(&r, "card 4539 1488 0343 6468 expires", "card");
}

#[test]
fn card_rejects_timestamps_and_repeated_digits() {
    let r = redactor();
    // 1700000000004 passes Luhn (total 10) but is 2023-11-14 in milliseconds
    assert_not_found(&r, "ts=1700000000004", "card");
    // sixteen zeros pass Luhn too (total 0)
    assert_not_found(&r, "0000 0000 0000 0000", "card");
    assert_not_found(&r, "4444444444444444", "card");
    assert_not_found(&r, "12345", "card");
}

#[test]
fn nir_needs_the_right_key() {
    // 1 85 05 78 006 084: 1850578006084 mod 97 = 6, so the key is 97 - 6 = 91.
    let r = redactor();
    assert_found(&r, "nir 1 85 05 78 006 084 91 ok", "nir", "1 85 05 78 006 084 91");
    assert_found(&r, "185057800608491", "nir", "185057800608491");
    assert_not_found(&r, "nir 1 85 05 78 006 084 92 ok", "nir");
    assert_not_found(&r, "185057800608492", "nir");
    // Corsica, department 2A read as 19: 2991219123456 mod 97 = 9, so the key is 97 - 9 = 88.
    assert_found(&r, "2 99 12 2A 123 456 88", "nir", "2 99 12 2A 123 456 88");
    assert_not_found(&r, "2 99 12 2A 123 456 87", "nir");
    // the same number with 2B read as 18: 2991218123456 mod 97 = 79 so the key is 97 - 79 = 18
    assert_found(&r, "2 99 12 2B 123 456 18", "nir", "2 99 12 2B 123 456 18");
}

#[test]
fn ssn() {
    let r = redactor();
    assert_found(&r, "ssn 123-45-6789 on file", "ssn", "123-45-6789");
    for text in
        ["000-12-3456", "666-12-3456", "912-12-3456", "123-00-6789", "123-45-0000", "1123-45-6789", "123-45-6789-1"]
    {
        assert_not_found(&r, text, "ssn");
    }
}

#[test]
fn ip_only_when_asked_for_and_only_public() {
    let on = redactor_with_ip();
    assert_found(&on, "server 8.8.8.8 up", "ip", "8.8.8.8");
    assert_found(&on, "server 203.0.113.7.", "ip", "203.0.113.7");
    for text in [
        "10.0.0.1",
        "172.16.5.4",
        "172.31.255.255",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.1.1",
        "0.1.2.3",
        "224.0.0.1",
        "255.255.255.255",
        "999.1.1.1",
        "1.2.3.4.5",
        "version 8.8.8.8.8",
    ] {
        assert_not_found(&on, text, "ip");
    }
    assert_found(&on, "172.32.0.1", "ip", "172.32.0.1");
    assert_not_found(&redactor(), "server 8.8.8.8 up", "ip");
}

#[test]
fn person_names() {
    let config = Config {
        pii: PiiConfig { names: vec!["Jean Dupont".to_owned(), "Zoé".to_owned()], ..PiiConfig::default() },
        ..Config::default()
    };
    let r = Redactor::new(config).unwrap();
    assert_found(&r, "mail from jean dupont today", "person", "jean dupont");
    assert_found(&r, "JEAN DUPONT", "person", "JEAN DUPONT");
    assert_found(&r, "salut Zoé!", "person", "Zoé");
    assert_not_found(&r, "jean dupontel and Zoéline", "person");
    let hits = r.find("Jean Dupont");
    assert_eq!(hits[0].kind, Kind::Person);
}

#[test]
fn custom_patterns_name_their_tokens() {
    let config = Config {
        pii: PiiConfig {
            custom: vec![CustomPattern { name: "customer_id".to_owned(), pattern: r"CUST-\d{6}".to_owned() }],
            ..PiiConfig::default()
        },
        ..Config::default()
    };
    let r = Redactor::new(config).unwrap();
    assert_found(&r, "see CUST-123456 and CUST-65", "customer_id", "CUST-123456");
    let mut session = warden_redact::Session::in_memory();
    let (out, counts) = r.redact(&mut session, "see CUST-123456 and CUST-654321 and CUST-123456");
    assert_eq!(out, "see <CUSTOMER_ID_1> and <CUSTOMER_ID_2> and <CUSTOMER_ID_1>");
    assert_eq!(counts.iter().collect::<Vec<_>>(), vec![("customer_id", 3)]);
    assert_not_found(&r, "CUST-12", "customer_id");
}

#[test]
fn a_bad_custom_pattern_is_named_in_the_error() {
    let config = Config {
        pii: PiiConfig {
            custom: vec![CustomPattern { name: "broken".to_owned(), pattern: "(".to_owned() }],
            ..PiiConfig::default()
        },
        ..Config::default()
    };
    let Err(error) = Redactor::new(config) else { panic!("a pattern that does not compile must be refused") };
    assert!(error.contains("broken"), "{error}");
}

#[test]
fn pii_can_be_switched_off_or_narrowed() {
    let text = "alice@acme.fr 06 12 34 56 78";
    let off = Config { pii: PiiConfig { enabled: false, ..PiiConfig::default() }, ..Config::default() };
    assert!(Redactor::new(off).unwrap().find(text).is_empty());
    let email_only =
        Config { pii: PiiConfig { kinds: vec![Kind::Email], ..PiiConfig::default() }, ..Config::default() };
    let hits = found(&Redactor::new(email_only).unwrap(), text);
    assert_eq!(hits, vec![("email".to_owned(), "alice@acme.fr".to_owned())]);
}

#[test]
fn the_default_configuration_is_as_documented() {
    let config = Config::default();
    assert!(config.secrets && config.pii.enabled);
    assert_eq!(config.pii.kinds, vec![Kind::Email, Kind::Phone, Kind::Iban, Kind::Card, Kind::Nir, Kind::Ssn]);
    assert_eq!(config.pii.allow.len(), 6);
}

#[test]
fn kind_prefixes() {
    assert_eq!(Kind::Secret.prefix(), "SECRET");
    assert_eq!(Kind::Person.prefix(), "PERSON");
    assert_eq!(Kind::Ip.prefix(), "IP");
    assert_eq!(Kind::Custom("customer-id.v2".to_owned()).prefix(), "CUSTOMER_ID_V2");
}
