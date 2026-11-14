//! Recognising a credential in a piece of text. Used where a credential has no business being: a command line, a URL.

use std::sync::LazyLock;

use regex::Regex;

/// A pattern that is written in this file, so that failing to compile it is a bug the tests catch.
#[allow(clippy::expect_used)]
pub(crate) fn literal(pattern: &str) -> Regex {
    Regex::new(pattern).expect("a literal pattern in the source is valid")
}

static TOKENS: LazyLock<Vec<(&'static str, Regex)>> = LazyLock::new(|| {
    vec![
        ("a GitHub token", literal(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
        ("a GitHub token", literal(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
        ("an AWS access key", literal(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
        ("a Google API key", literal(r"\bAIza[0-9A-Za-z_-]{35}\b")),
        ("a Slack token", literal(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
        ("an API key", literal(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}\b")),
        ("a Stripe key", literal(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
        ("a private key", literal(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
        ("a JSON web token", literal(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
        ("a password in a URL", literal(r"://[^/\s:@'\x22]+:[^/\s@'\x22]{3,}@")),
    ]
});

static SECRET_NAME: LazyLock<Regex> = LazyLock::new(|| {
    literal(
        r"(?i)(?:^|_)(?:token|secret|passw(?:or)?d|passwd|api_?key|access_?key|private_?key|credential|auth)(?:_|$)",
    )
});

/// Whether a variable name looks like it holds a secret.
#[must_use]
pub fn is_secret_name(name: &str) -> bool {
    SECRET_NAME.is_match(name)
}

/// What kind of credential `text` contains, if it contains one.
#[must_use]
pub fn credential_in(text: &str) -> Option<&'static str> {
    TOKENS.iter().find(|(_, pattern)| pattern.is_match(text)).map(|(kind, _)| *kind)
}

/// Whether `value` looks like a real secret and not a placeholder or a reference: long enough, with a mix of
/// characters, and not an expansion.
#[must_use]
pub fn looks_like_secret_value(value: &str) -> bool {
    let value = value.trim_matches(|c| c == '"' || c == '\'');
    if value.len() < 12 || value.starts_with('$') || value.contains("${") || value.contains('<') {
        return false;
    }
    let classes = [
        value.chars().any(|c| c.is_ascii_lowercase()),
        value.chars().any(|c| c.is_ascii_uppercase()),
        value.chars().any(|c| c.is_ascii_digit()),
        value.chars().any(|c| !c.is_ascii_alphanumeric()),
    ];
    classes.iter().filter(|present| **present).count() >= 3
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn well_known_token_formats_are_recognised() {
        for (text, kind) in [
            ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", "a GitHub token"),
            ("AKIAIOSFODNN7EXAMPLE", "an AWS access key"),
            ("xoxb-123456789012-abcdefghij", "a Slack token"),
            ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "an API key"),
            ("-----BEGIN OPENSSH PRIVATE KEY-----", "a private key"),
            ("https://user:hunter2@example.com/repo", "a password in a URL"),
        ] {
            assert_eq!(credential_in(text), Some(kind), "{text}");
        }
    }

    #[test]
    fn ordinary_text_is_not_a_credential() {
        for text in ["git status", "https://github.com/org/repo", "user@example.com", "sk-short"] {
            assert_eq!(credential_in(text), None, "{text}");
        }
    }

    #[test]
    fn secret_looking_names_are_recognised() {
        for name in ["GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD", "api_key", "OPENAI_API_KEY", "AUTH"] {
            assert!(is_secret_name(name), "{name}");
        }
        for name in ["PATH", "HOME", "AUTHOR", "TOKENIZER_MODE_X"] {
            assert!(!is_secret_name(name), "{name}");
        }
    }

    #[test]
    fn a_secret_value_has_length_and_mixed_characters() {
        assert!(looks_like_secret_value("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"));
        assert!(!looks_like_secret_value("changeme"));
        assert!(!looks_like_secret_value("$OTHER_VARIABLE_NAME"));
        assert!(!looks_like_secret_value("<SECRET_1>"));
    }
}
