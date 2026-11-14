#![allow(
    clippy::expect_used,
    clippy::unwrap_used,
    clippy::indexing_slicing,
    clippy::assert_is_empty,
    clippy::cast_possible_truncation
)]

mod common;

use common::{assert_found, assert_not_found, fill, found, redactor};

#[test]
fn aws_access_key() {
    let r = redactor();
    assert_found(&r, "key AKIAIOSFODNN7EXAMPLE here", "aws_access_key", "AKIAIOSFODNN7EXAMPLE");
    assert_found(&r, "ASIAIOSFODNN7EXAMPLE", "aws_access_key", "ASIAIOSFODNN7EXAMPLE");
    assert_not_found(&r, "AKIA123 is short, and AKIAiosfodnn7example is lower case", "aws_access_key");
}

#[test]
fn aws_secret_key_replaces_the_value_only() {
    let r = redactor();
    let value = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY";
    assert_eq!(value.len(), 40);
    assert_found(&r, &format!("aws_secret_access_key = {value}"), "aws_secret_key", value);
    assert_found(&r, &format!("AWS_SECRET_ACCESS_KEY={value}\n"), "aws_secret_key", value);
    assert_not_found(&r, &format!("some_other_key = {value}"), "aws_secret_key");
    assert_not_found(&r, "aws_secret_access_key = tooShort", "aws_secret_key");
}

#[test]
fn github_token() {
    let r = redactor();
    let classic = format!("ghp_{}", fill(36));
    assert_found(&r, &format!("token {classic} end"), "github_token", &classic);
    let fine = format!("github_pat_{}", fill(50));
    assert_found(&r, &fine, "github_token", &fine);
    assert_not_found(&r, "ghp_tooshort and github_pat_tooshort", "github_token");
}

#[test]
fn gitlab_token() {
    let r = redactor();
    let token = format!("glpat-{}", fill(24));
    assert_found(&r, &token, "gitlab_token", &token);
    assert_not_found(&r, "glpat-short", "gitlab_token");
}

#[test]
fn slack_token() {
    let r = redactor();
    let token = "xoxb-123456789012-abcdefghijkl";
    assert_found(&r, token, "slack_token", token);
    assert_not_found(&r, "xoxz-123456789012-abcdefghijkl and xoxb-1", "slack_token");
}

#[test]
fn google_api_key() {
    let r = redactor();
    let key = format!("AIza{}", fill(35));
    assert_found(&r, &format!("key={key}"), "google_api_key", &key);
    assert_not_found(&r, "AIza123", "google_api_key");
}

#[test]
fn stripe_key() {
    let r = redactor();
    let live = format!("sk_live_{}", fill(24));
    assert_found(&r, &live, "stripe_key", &live);
    let restricted = format!("rk_live_{}", fill(16));
    assert_found(&r, &restricted, "stripe_key", &restricted);
    assert_not_found(&r, &format!("sk_test_{}", fill(24)), "stripe_key");
}

#[test]
fn openai_key() {
    let r = redactor();
    for prefix in ["sk-", "sk-proj-", "sk-ant-"] {
        let key = format!("{prefix}{}", fill(40));
        assert_found(&r, &format!("OPENAI={key}"), "openai_key", &key);
    }
    assert_not_found(&r, "sk-short and task-force-with-a-very-long-name-here", "openai_key");
}

#[test]
fn sendgrid_key() {
    let r = redactor();
    let key = format!("SG.{}.{}", fill(22), fill(43));
    assert_found(&r, &key, "sendgrid_key", &key);
    assert_not_found(&r, "SG.short.short", "sendgrid_key");
}

#[test]
fn twilio_key() {
    let r = redactor();
    let key = format!("SK{}", "0123456789abcdef".repeat(2));
    assert_found(&r, &key, "twilio_key", &key);
    assert_not_found(&r, "SK0123456789abcdef and SKzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", "twilio_key");
}

#[test]
fn npm_token() {
    let r = redactor();
    let token = format!("npm_{}", fill(36));
    assert_found(&r, &token, "npm_token", &token);
    assert_not_found(&r, "npm_install and npm_short", "npm_token");
}

#[test]
fn pypi_token() {
    let r = redactor();
    let token = format!("pypi-{}", fill(60));
    assert_found(&r, &token, "pypi_token", &token);
    assert_not_found(&r, "pypi-short", "pypi_token");
}

#[test]
fn huggingface_token() {
    let r = redactor();
    let token = format!("hf_{}", "abcdefghij".repeat(4));
    assert_found(&r, &token, "huggingface_token", &token);
    assert_not_found(&r, "hf_short and hf_123456789012345678901234567890", "huggingface_token");
}

#[test]
fn doppler_token() {
    let r = redactor();
    let token = format!("dp.pt.{}", fill(40));
    assert_found(&r, &token, "doppler_token", &token);
    assert_not_found(&r, "dp.pt.short", "doppler_token");
}

#[test]
fn jwt() {
    let r = redactor();
    let token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    assert_found(&r, &format!("jwt: {token}"), "jwt", token);
    assert_not_found(&r, "eyJhbGciOiJIUzI1NiJ9 alone, and a.b.c", "jwt");
}

#[test]
fn bearer_token_replaces_the_value_only() {
    let r = redactor();
    assert_found(&r, "Authorization: Bearer abcdefghij0123456789xyz", "bearer_token", "abcdefghij0123456789xyz");
    assert_not_found(&r, "Bearer short and the bearer of bad news", "bearer_token");
}

#[test]
fn basic_auth_replaces_the_value_only() {
    let r = redactor();
    assert_found(&r, "Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==", "basic_auth", "dXNlcjpwYXNzd29yZDEyMw==");
    assert_not_found(&r, "Basic dXNlcjpwYXNzd29yZDEyMw== without the header", "basic_auth");
}

#[test]
fn url_credentials_keep_scheme_user_and_host() {
    let r = redactor();
    let text = "DATABASE=postgres://admin:s3cr3tPass@db.internal:5432/app";
    assert_found(&r, text, "url_credentials", "s3cr3tPass");
    let (out, _) = r.redact(&mut warden_redact::Session::in_memory(), text);
    assert_eq!(out, "DATABASE=postgres://admin:<SECRET_1>@db.internal:5432/app");
    assert_not_found(&r, "https://github.com/org/repo and ssh://git@host:22/path", "url_credentials");
    assert_not_found(&r, "https://user:${PASSWORD}@host/", "url_credentials");
}

#[test]
fn npmrc_token() {
    let r = redactor();
    assert_found(&r, "//registry.npmjs.org/:_authToken=abcd1234efgh5678", "npmrc_token", "abcd1234efgh5678");
    assert_not_found(&r, "//registry.npmjs.org/:_authToken=${NPM_TOKEN}", "npmrc_token");
}

#[test]
fn private_key_block() {
    let r = redactor();
    let block = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\nabcdef\n-----END RSA PRIVATE KEY-----";
    assert_found(&r, &format!("before\n{block}\nafter"), "private_key", block);
    let openssh = "-----BEGIN OPENSSH PRIVATE KEY-----\nxyz\n-----END OPENSSH PRIVATE KEY-----";
    assert_found(&r, openssh, "private_key", openssh);
    assert_not_found(&r, "-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----", "private_key");
    assert_not_found(&r, "-----BEGIN RSA PRIVATE KEY-----\nno end", "private_key");
}

#[test]
fn credential_assignment_replaces_the_value_only() {
    let r = redactor();
    assert_found(&r, "DB_PASSWORD=Sup3rS3cret!x", "credential_assignment", "Sup3rS3cret!x");
    assert_found(&r, r#"{"client_secret": "Zx9Qm2LpVw7K"}"#, "credential_assignment", "Zx9Qm2LpVw7K");
    assert_found(&r, "api_key: 'k8Jd9sL2mQ4x'", "credential_assignment", "k8Jd9sL2mQ4x");
    assert_found(&r, "token = abcdefghijklmnopqrst", "credential_assignment", "abcdefghijklmnopqrst");
    assert_found(&r, "clientSecret=Ab3dE5gH7j", "credential_assignment", "Ab3dE5gH7j");
    let (out, counts) = r.redact(&mut warden_redact::Session::in_memory(), "password=Sup3rS3cret!x");
    assert_eq!(out, "password=<SECRET_1>");
    assert_eq!(counts.total(), 1);
}

#[test]
fn credential_assignment_ignores_placeholders_and_weak_values() {
    let r = redactor();
    for text in [
        "password=changeme",
        "password=hunter2",
        "password: \"your_password_here\"",
        "api_key=********",
        "secret=xxxxxxxxxxxx",
        "secret=aaaaaaaa",
        "token=$TOKEN_VALUE_HERE1",
        "token=${CI_TOKEN_VALUE}1",
        "password={{ vault_password_1 }}",
        "password=<your-password-1>",
        "password=password",
        "password=example.Password1!",
        "author = \"Jean Dupont, Software Engineer\"",
        "tokenizer = abcdefghijklmnopqrstuvwxyz",
    ] {
        assert_not_found(&r, text, "credential_assignment");
    }
}

#[test]
fn a_secret_that_two_detectors_find_is_found_once() {
    let r = redactor();
    let token = format!("ghp_{}", fill(36));
    let hits = found(&r, &format!("GITHUB_TOKEN={token}"));
    assert_eq!(hits, vec![("github_token".to_owned(), token)]);
}

#[test]
fn secrets_can_be_switched_off() {
    let config = warden_redact::Config { secrets: false, ..warden_redact::Config::default() };
    let r = warden_redact::Redactor::new(config).unwrap();
    assert!(r.find("AKIAIOSFODNN7EXAMPLE password=Sup3rS3cret!x").is_empty());
}
