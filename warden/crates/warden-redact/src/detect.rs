//! The detectors: a regular expression to find candidates, an optional check to throw false ones away.

use std::sync::LazyLock;

use regex::Regex;

use crate::kind::Kind;

/// A check on a candidate value only.
pub(crate) type ValueCheck = fn(&str) -> bool;
/// A check that also sees the text around: `(text, start, end)`; gives the end of the part to keep, or nothing to
/// drop the candidate.
pub(crate) type ContextCheck = fn(&str, usize, usize) -> Option<usize>;

/// How a candidate is checked.
#[derive(Clone, Copy)]
pub(crate) enum Check {
    None,
    Value(ValueCheck),
    Context(ContextCheck),
}

/// One named detector.
#[derive(Clone)]
pub(crate) struct Detector {
    pub(crate) name: String,
    pub(crate) kind: Kind,
    re: Regex,
    /// the capture groups that hold the part to replace; the first that took part wins
    groups: &'static [usize],
    check: Check,
    /// whether the allow list applies to what this detector finds
    pub(crate) allowable: bool,
}

impl Detector {
    pub(crate) fn custom(name: &str, re: Regex) -> Self {
        Self {
            name: name.to_owned(),
            kind: Kind::Custom(name.to_owned()),
            re,
            groups: &[0],
            check: Check::None,
            allowable: false,
        }
    }

    pub(crate) fn person(re: Regex) -> Self {
        Self { name: "person".to_owned(), kind: Kind::Person, re, groups: &[0], check: Check::None, allowable: true }
    }

    /// Calls `found(start, end)` for every candidate that passes the check.
    pub(crate) fn scan(&self, text: &str, found: &mut impl FnMut(usize, usize)) {
        let mut accept = |start: usize, end: usize| {
            let end = match self.check {
                Check::None => Some(end),
                Check::Value(check) => text.get(start..end).filter(|v| check(v)).map(|_| end),
                Check::Context(check) => check(text, start, end),
            };
            if let Some(end) = end.filter(|&end| end > start) {
                found(start, end);
            }
        };
        if self.groups == [0] {
            for m in self.re.find_iter(text) {
                accept(m.start(), m.end());
            }
        } else {
            for caps in self.re.captures_iter(text) {
                if let Some(m) = self.groups.iter().find_map(|&g| caps.get(g)) {
                    accept(m.start(), m.end());
                }
            }
        }
    }
}

/// Compiles a pattern written in this source. A literal that does not compile is a programmer error that the tests of
/// this crate catch (`every_builtin_pattern_compiles`), never something a user can cause.
#[allow(clippy::expect_used)]
fn re(pattern: &str) -> Regex {
    Regex::new(pattern).expect("a built-in pattern is valid; the tests compile them all")
}

/// Matches a token this crate hands out: `<EMAIL_1>`, `<CUSTOMER_ID_12>`.
pub(crate) static TOKEN: LazyLock<Regex> = LazyLock::new(|| re(r"<[A-Z0-9_]+_[0-9]+>"));
/// A complete private key block, over several lines.
pub(crate) static PRIVATE_KEY_BLOCK: LazyLock<Regex> =
    LazyLock::new(|| re(r"(?s)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----"));
/// The first line of a private key block.
pub(crate) static PRIVATE_KEY_BEGIN: LazyLock<Regex> = LazyLock::new(|| re(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"));
/// The last line of a private key block.
pub(crate) static PRIVATE_KEY_END: LazyLock<Regex> = LazyLock::new(|| re(r"-----END [A-Z0-9 ]*PRIVATE KEY-----"));

fn secret(name: &str, pattern: &str, groups: &'static [usize], check: Check) -> Detector {
    Detector { name: name.to_owned(), kind: Kind::Secret, re: re(pattern), groups, check, allowable: false }
}

fn pii(name: &str, kind: Kind, pattern: &str, check: Check) -> Detector {
    Detector { name: name.to_owned(), kind, re: re(pattern), groups: &[0], check, allowable: true }
}

/// The secret detectors, in the order that breaks ties.
pub(crate) static SECRETS: LazyLock<Vec<Detector>> = LazyLock::new(|| {
    let plain = |name: &str, pattern: &str| secret(name, pattern, &[0], Check::None);
    vec![
        plain("aws_access_key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        secret(
            "aws_secret_key",
            r#"(?i)aws[_-]?secret[_-]?(?:access[_-]?)?key["']?(?:\s*[=:]\s*|\s+)["']?([A-Za-z0-9/+=]{40})(?:[^A-Za-z0-9/+=]|$)"#,
            &[1],
            Check::None,
        ),
        plain("github_token", r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
        plain("gitlab_token", r"\bglpat-[A-Za-z0-9_-]{20,}"),
        plain("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
        plain("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}"),
        plain("stripe_key", r"\b[sr]k_live_[0-9A-Za-z]{16,}"),
        plain("openai_key", r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"),
        plain("sendgrid_key", r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
        plain("twilio_key", r"\bSK[0-9a-fA-F]{32}\b"),
        plain("npm_token", r"\bnpm_[A-Za-z0-9]{36}\b"),
        plain("pypi_token", r"\bpypi-[A-Za-z0-9_-]{50,}"),
        plain("huggingface_token", r"\bhf_[A-Za-z]{30,}"),
        plain("doppler_token", r"\bdp\.pt\.[A-Za-z0-9]{30,}"),
        plain("jwt", r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+"),
        secret("bearer_token", r"(?i)\bBearer +([A-Za-z0-9._~+/=-]{20,})", &[1], Check::None),
        secret("basic_auth", r"(?i)\bAuthorization:\s*Basic\s+([A-Za-z0-9+/]{8,}={0,2})", &[1], Check::None),
        secret(
            "url_credentials",
            r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s:/@]+:([^\s/@]+)@",
            &[1],
            Check::Value(not_a_reference),
        ),
        secret("npmrc_token", r#"_authToken\s*=\s*["']?([^\s"']+)"#, &[1], Check::Value(not_a_reference)),
        plain("private_key", PRIVATE_KEY_BLOCK.as_str()),
        secret(
            "credential_assignment",
            r#"(?i:password|passwd|secret|token|api[_-]?key|apikey|auth|credentials?)(?:[_.-][A-Za-z0-9_.-]*|[A-Z][A-Za-z0-9]*)?["']?\s*[:=]\s*(?:"([^"\n]*)"|'([^'\n]*)'|([^\s"',;]+))"#,
            &[1, 2, 3],
            Check::Value(credential_value),
        ),
    ]
});

/// The PII detectors, in the order that breaks ties (the NIR before the card: its check is the stricter one).
pub(crate) static PII: LazyLock<Vec<Detector>> = LazyLock::new(|| {
    vec![
        pii(
            "email",
            Kind::Email,
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
            Check::Context(email),
        ),
        pii(
            "phone",
            Kind::Phone,
            r"(?:\+[1-9]\d{0,2}(?:[ .-]?\d{1,4}){2,6}|\b0[1-9](?:[ .-]?\d{2}){4})\b",
            Check::Context(phone),
        ),
        pii("iban", Kind::Iban, r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b", Check::Context(iban)),
        pii(
            "nir",
            Kind::Nir,
            r"\b[12][ .-]?\d{2}[ .-]?(?:0[1-9]|1[0-2]|[2-9]\d)[ .-]?(?:\d{2}|2[ABab])[ .-]?\d{3}[ .-]?\d{3}[ .-]?\d{2}\b",
            Check::Value(nir),
        ),
        pii("card", Kind::Card, r"\b\d(?:[ -]?\d){12,18}\b", Check::Value(card)),
        pii("ssn", Kind::Ssn, r"\b\d{3}-\d{2}-\d{4}\b", Check::Context(ssn)),
        pii("ip", Kind::Ip, r"\b(?:\d{1,3}\.){3}\d{1,3}\b", Check::Context(ip)),
    ]
});

// ---------------------------------------------------------------- checks

/// A value that is a reference to a variable or a placeholder rather than a secret: `$TOKEN`, `${X}`, `<...>`, `{{x}}`.
fn not_a_reference(value: &str) -> bool {
    !(value.starts_with(['$', '<']) || value.starts_with("{{"))
}

/// Whether the value assigned to a sensitive name looks like a real credential and not a placeholder.
fn credential_value(value: &str) -> bool {
    let length = value.chars().count();
    if length < 8 || !not_a_reference(value) {
        return false;
    }
    let lower = value.to_lowercase();
    let placeholder = lower.contains("changeme")
        || lower.contains("change_me")
        || lower.contains("example")
        || lower.starts_with("your_")
        || lower.starts_with("your-")
        || matches!(lower.as_str(), "password" | "passwd" | "secret" | "token" | "null" | "undefined")
        || lower.chars().all(|c| matches!(c, 'x' | '*' | '.' | '-' | '_' | '#'));
    if placeholder {
        return false;
    }
    let classes = [
        value.chars().any(char::is_lowercase),
        value.chars().any(char::is_uppercase),
        value.chars().any(|c| c.is_ascii_digit()),
        value.chars().any(|c| !c.is_alphanumeric()),
    ];
    classes.iter().filter(|&&present| present).count() >= 3 || length >= 20
}

fn char_before(text: &str, at: usize) -> Option<char> {
    text.get(..at)?.chars().next_back()
}

fn char_after(text: &str, at: usize) -> Option<char> {
    text.get(at..)?.chars().next()
}

/// Whether the candidate is glued to a longer dotted, dashed or slashed number (`1.2.3.4.5`, `10-12-2024-5`).
fn embedded_in_number(text: &str, start: usize, end: usize) -> bool {
    let separator = |c: char| matches!(c, '.' | '-' | '/');
    let before = text.get(..start).map(|t| t.chars().rev().take(2).collect::<Vec<_>>()).unwrap_or_default();
    let after = text.get(end..).map(|t| t.chars().take(2).collect::<Vec<_>>()).unwrap_or_default();
    matches!(before.as_slice(), [s, d] if separator(*s) && d.is_ascii_digit())
        || matches!(after.as_slice(), [s, d] if separator(*s) && d.is_ascii_digit())
}

fn email(text: &str, start: usize, end: usize) -> Option<usize> {
    let found = text.get(start..end)?;
    let (local, domain) = found.split_once('@')?;
    // `@scope/pkg@1.2.3`: the word before the match starts with `@`
    if char_before(text, start) == Some('/') {
        let word = text.get(..start)?.rsplit(char::is_whitespace).next().unwrap_or_default();
        if word.starts_with('@') {
            return None;
        }
    }
    // `scheme://user:secret@host.tld`: the password is not a mailbox
    if char_before(text, start) == Some(':') {
        let word = text.get(..start)?.rsplit(char::is_whitespace).next().unwrap_or_default();
        if word.contains("://") {
            return None;
        }
    }
    // `pkg@1.2.3-beta.rc`: a version, not a host
    if domain.split('.').next().is_some_and(|label| label.chars().all(|c| c.is_ascii_digit())) {
        return None;
    }
    // `git@host:path`: a git remote
    if local == "git" && char_after(text, end) == Some(':') {
        return None;
    }
    if char_after(text, end).is_some_and(|c| c.is_ascii_alphanumeric() || c == '-') {
        return None;
    }
    Some(end)
}

fn phone(text: &str, start: usize, end: usize) -> Option<usize> {
    let found = text.get(start..end)?;
    let digits = found.chars().filter(char::is_ascii_digit).count();
    if !(8..=15).contains(&digits) || is_date(found) {
        return None;
    }
    if char_before(text, start).is_some_and(char::is_alphanumeric) || embedded_in_number(text, start, end) {
        return None;
    }
    if !found.starts_with('+') {
        // more digit pairs run on: `06 12 34 56 78 90 12` is not one number
        let separator = |c: char| matches!(c, ' ' | '.' | '-');
        let mut after = text.get(end..).unwrap_or_default().chars();
        let mut before = text.get(..start).unwrap_or_default().chars().rev();
        let runs_on_after = matches!((after.next(), after.next(), after.next()), (Some(s), Some(a), Some(b)) if separator(s) && a.is_ascii_digit() && b.is_ascii_digit());
        let runs_on_before = matches!((before.next(), before.next(), before.next()), (Some(s), Some(a), Some(b)) if separator(s) && a.is_ascii_digit() && b.is_ascii_digit());
        if runs_on_after || runs_on_before {
            return None;
        }
        // a French number keeps one separator throughout: `01 02 03 04 05`, never `03-04-2024 10`
        let separators: Vec<char> = found.chars().filter(|c| !c.is_ascii_digit()).collect();
        if let Some(&first) = separators.first() {
            let uniform = separators.iter().all(|&c| c == first);
            let pairs = found.split(first).count() == 5 && found.split(first).all(|part| part.len() == 2);
            if !uniform || !pairs {
                return None;
            }
        }
    }
    Some(end)
}

/// `2024-01-02`, `02/01/2024`, `2.1.24`: three numbers split by one separator.
fn is_date(text: &str) -> bool {
    let separator = |c: char| matches!(c, '-' | '.' | '/' | ' ');
    let parts: Vec<&str> = text.split(separator).collect();
    let [a, b, c] = parts.as_slice() else { return false };
    let numbers = parts.iter().all(|p| !p.is_empty() && p.chars().all(|ch| ch.is_ascii_digit()));
    numbers
        && ((a.len() == 4 && b.len() <= 2 && c.len() <= 2)
            || (a.len() <= 2 && b.len() <= 2 && matches!(c.len(), 2 | 4)))
}

/// ISO 7064 mod 97-10: move the first four characters to the end, letters become 10..35, the number mod 97 must be 1.
fn iban_valid(compact: &str) -> bool {
    if !(15..=34).contains(&compact.len()) || !compact.is_ascii() {
        return false;
    }
    let rearranged = compact.get(4..).unwrap_or_default().chars().chain(compact.chars().take(4));
    let mut remainder = 0_u32;
    for c in rearranged {
        let Some(value) = c.to_digit(36) else { return false };
        remainder = if value >= 10 { (remainder * 100 + value) % 97 } else { (remainder * 10 + value) % 97 };
    }
    remainder == 1
}

fn iban(text: &str, start: usize, end: usize) -> Option<usize> {
    // The pattern may have swallowed a word after the number (`... 7654 32 DONE` is not possible, but a four letter
    // word after a number that ends on a group is): give back trailing groups until the number checks.
    let mut end = end;
    loop {
        let found = text.get(start..end)?;
        let compact: String = found.chars().filter(|&c| c != ' ').collect();
        if iban_valid(&compact) {
            return Some(end);
        }
        let cut = found.rfind(' ')?;
        end = start + cut;
    }
}

fn luhn(digits: &[u32]) -> bool {
    let sum: u32 = digits
        .iter()
        .rev()
        .enumerate()
        .map(|(i, &d)| if i % 2 == 1 { if d * 2 > 9 { d * 2 - 9 } else { d * 2 } } else { d })
        .sum();
    sum % 10 == 0
}

fn card(value: &str) -> bool {
    let digits: Vec<u32> = value.chars().filter_map(|c| c.to_digit(10)).collect();
    if !(13..=19).contains(&digits.len()) || digits.windows(2).all(|w| w[0] == w[1]) {
        return false;
    }
    // 13 digits with no separator that read as a date between 2000 and 2100 in milliseconds: a Unix timestamp
    if digits.len() == 13 && !value.contains([' ', '-']) {
        let millis: u64 = digits.iter().fold(0, |n, &d| n * 10 + u64::from(d));
        if (946_684_800_000..4_102_444_800_000).contains(&millis) {
            return false;
        }
    }
    luhn(&digits)
}

/// The NIR key: `97 - (first 13 digits mod 97)`, with Corsica's `2A` read as `19` and `2B` as `18`.
fn nir(value: &str) -> bool {
    let compact: String = value.chars().filter(char::is_ascii_alphanumeric).map(|c| c.to_ascii_uppercase()).collect();
    if compact.len() != 15 || !compact.is_ascii() {
        return false;
    }
    let (body, key) = compact.split_at(13);
    let body = match body.get(5..7) {
        Some("2A") => format!("{}19{}", &body[..5], &body[7..]),
        Some("2B") => format!("{}18{}", &body[..5], &body[7..]),
        _ => body.to_owned(),
    };
    match (body.parse::<u64>(), key.parse::<u64>()) {
        (Ok(number), Ok(key)) => 97 - number % 97 == key,
        _ => false,
    }
}

fn ssn(text: &str, start: usize, end: usize) -> Option<usize> {
    let found = text.get(start..end)?;
    let mut parts = found.split('-');
    let (area, group, serial) = (parts.next()?, parts.next()?, parts.next()?);
    let invalid_area = area == "000" || area == "666" || area.starts_with('9');
    if invalid_area || group == "00" || serial == "0000" || embedded_in_number(text, start, end) {
        return None;
    }
    Some(end)
}

fn ip(text: &str, start: usize, end: usize) -> Option<usize> {
    let octets: Vec<u32> = text.get(start..end)?.split('.').map(|p| p.parse().unwrap_or(u32::MAX)).collect();
    let [a, b, _, _] = octets.as_slice() else { return None };
    if octets.iter().any(|&o| o > 255) || embedded_in_number(text, start, end) {
        return None;
    }
    let private = *a == 10
        || (*a == 172 && (16..=31).contains(b))
        || (*a == 192 && *b == 168)
        || *a == 127
        || (*a == 169 && *b == 254)
        || *a == 0
        || *a >= 224;
    (!private).then_some(end)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_builtin_pattern_compiles() {
        let names: Vec<&str> = SECRETS.iter().chain(PII.iter()).map(|d| d.name.as_str()).collect();
        assert_eq!(names.len(), 28);
        for regex in [&*TOKEN, &*PRIVATE_KEY_BLOCK, &*PRIVATE_KEY_BEGIN, &*PRIVATE_KEY_END] {
            assert_ne!(regex.as_str(), "");
        }
    }
}
