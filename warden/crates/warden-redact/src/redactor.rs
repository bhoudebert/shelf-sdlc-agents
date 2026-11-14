use std::cmp::Reverse;
use std::collections::BTreeMap;

use globset::{GlobBuilder, GlobSet, GlobSetBuilder};
use regex::{Regex, RegexBuilder};

use crate::config::Config;
use crate::counts::Counts;
use crate::detect::{Detector, PII, PRIVATE_KEY_BEGIN, PRIVATE_KEY_END, SECRETS, TOKEN};
use crate::kind::Kind;
use crate::session::Session;

/// A value found in a text: the part to replace.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Hit {
    /// What it is.
    pub kind: Kind,
    /// The name of the detector that found it.
    pub detector: String,
    /// Byte offset where the value starts.
    pub start: usize,
    /// Byte offset just after the value.
    pub end: usize,
}

/// Finds credentials and personal data and swaps them for tokens, and back.
#[derive(Clone)]
pub struct Redactor {
    detectors: Vec<Detector>,
    allow: GlobSet,
    secrets: bool,
}

impl Redactor {
    /// Builds a redactor. The error names the custom pattern or the allow glob that does not compile.
    #[allow(clippy::needless_pass_by_value)] // the configuration is handed over: the redactor is built once from it
    pub fn new(config: Config) -> Result<Self, String> {
        let mut detectors: Vec<Detector> = Vec::new();
        if config.secrets {
            detectors.extend(SECRETS.iter().cloned());
        }
        let mut custom = Vec::new();
        for pattern in &config.pii.custom {
            if pattern.name.trim().is_empty() {
                return Err("custom pattern with an empty name".to_owned());
            }
            let re = Regex::new(&pattern.pattern)
                .map_err(|e| format!("custom pattern `{}` does not compile: {e}", pattern.name))?;
            custom.push(Detector::custom(&pattern.name, re));
        }
        let person = person_detector(&config.pii.names)?;
        let mut allow = GlobSetBuilder::new();
        for glob in &config.pii.allow {
            let glob = GlobBuilder::new(glob)
                .case_insensitive(true)
                .build()
                .map_err(|e| format!("allow glob `{glob}` does not compile: {e}"))?;
            allow.add(glob);
        }
        let allow = allow.build().map_err(|e| format!("allow globs do not compile: {e}"))?;
        if config.pii.enabled {
            detectors.extend(custom);
            detectors.extend(person);
            detectors.extend(PII.iter().filter(|d| config.pii.kinds.contains(&d.kind)).cloned());
        }
        Ok(Self { detectors, allow, secrets: config.secrets })
    }

    /// Every value to replace, in text order, none overlapping another. When spans overlap the longer one wins; on a
    /// tie the earlier detector wins (secrets, custom patterns, names, then Email, Phone, Iban, Nir, Card, Ssn, Ip).
    /// A span that touches a token of this crate (`<EMAIL_1>`) is dropped, so redacting twice changes nothing.
    #[must_use]
    pub fn find(&self, text: &str) -> Vec<Hit> {
        let tokens: Vec<(usize, usize)> = TOKEN.find_iter(text).map(|m| (m.start(), m.end())).collect();
        let touches_token = |start: usize, end: usize| {
            let first = tokens.partition_point(|&(_, token_end)| token_end <= start);
            tokens.get(first).is_some_and(|&(token_start, _)| token_start < end)
        };
        // (length, detector order, start, end)
        let mut candidates: Vec<(usize, usize, usize, usize)> = Vec::new();
        for (order, detector) in self.detectors.iter().enumerate() {
            detector.scan(text, &mut |start, end| {
                let allowed = detector.allowable && text.get(start..end).is_some_and(|v| self.allow.is_match(v));
                if !allowed && !touches_token(start, end) {
                    candidates.push((end - start, order, start, end));
                }
            });
        }
        candidates.sort_by_key(|&(len, order, start, _)| (Reverse(len), order, start));
        let mut accepted: BTreeMap<usize, (usize, usize)> = BTreeMap::new();
        for (_, order, start, end) in candidates {
            let clash = accepted.range(..end).next_back().is_some_and(|(_, &(accepted_end, _))| accepted_end > start);
            if !clash {
                accepted.insert(start, (end, order));
            }
        }
        accepted
            .into_iter()
            .filter_map(|(start, (end, order))| {
                let detector = self.detectors.get(order)?;
                Some(Hit { kind: detector.kind.clone(), detector: detector.name.clone(), start, end })
            })
            .collect()
    }

    /// Replaces every value found in `text` by its token from `session`, and says what was replaced.
    pub fn redact(&self, session: &mut Session, text: &str) -> (String, Counts) {
        let mut out = String::with_capacity(text.len());
        let mut counts = Counts::new();
        let mut at = 0;
        for hit in self.find(text) {
            let (Some(before), Some(value)) = (text.get(at..hit.start), text.get(hit.start..hit.end)) else { continue };
            out.push_str(before);
            out.push_str(&session.token_for(&hit.kind, value));
            counts.add(&hit.detector);
            at = hit.end;
        }
        out.push_str(text.get(at..).unwrap_or_default());
        (out, counts)
    }

    /// Puts back the value of every token `session` knows; other tokens stay as they are. Says how many it restored.
    #[must_use]
    pub fn restore(&self, session: &Session, text: &str) -> (String, usize) {
        let mut out = String::with_capacity(text.len());
        let mut restored = 0;
        let mut at = 0;
        for m in TOKEN.find_iter(text) {
            let Some(value) = session.value_of(m.as_str()) else { continue };
            out.push_str(text.get(at..m.start()).unwrap_or_default());
            out.push_str(value);
            restored += 1;
            at = m.end();
        }
        out.push_str(text.get(at..).unwrap_or_default());
        (out, restored)
    }

    /// A redactor for a stream read line by line.
    #[must_use]
    pub fn line_redactor(&self) -> LineRedactor {
        LineRedactor::default()
    }
}

/// One regular expression for all the names, longest first; none when there are no names.
fn person_detector(names: &[String]) -> Result<Option<Detector>, String> {
    let mut names: Vec<&str> = names.iter().map(|n| n.trim()).filter(|n| !n.is_empty()).collect();
    names.sort_by_key(|n| Reverse(n.len()));
    names.dedup();
    if names.is_empty() {
        return Ok(None);
    }
    let alternatives: Vec<String> = names
        .iter()
        .map(|name| {
            let word_start = name.chars().next().is_some_and(|c| c.is_alphanumeric() || c == '_');
            let word_end = name.chars().next_back().is_some_and(|c| c.is_alphanumeric() || c == '_');
            format!(
                "{}{}{}",
                if word_start { r"\b" } else { "" },
                regex::escape(name),
                if word_end { r"\b" } else { "" }
            )
        })
        .collect();
    let re = RegexBuilder::new(&alternatives.join("|"))
        .case_insensitive(true)
        .build()
        .map_err(|e| format!("names do not compile: {e}"))?;
    Ok(Some(Detector::person(re)))
}

/// Redacts a stream line by line. It remembers one thing: whether it is inside a private key block, which spans many
/// lines and cannot be recognized one line at a time.
///
/// The first line of the block becomes the token and the following lines become empty, up to the `END` line. The
/// token's value is the block so far, so it is complete once the `END` line has been seen. A block that was already
/// seen in one piece (with [`Redactor::redact`]) keeps its token only when it is read whole; a streamed block always
/// gets a new token, because its first line must be written before the rest is known.
#[derive(Debug, Clone, Default)]
pub struct LineRedactor {
    /// The token of the block being read, if there is one.
    open_block: Option<String>,
}

impl LineRedactor {
    /// Redacts one line, without its line terminator.
    pub fn redact_line(&mut self, redactor: &Redactor, session: &mut Session, line: &str) -> (String, Counts) {
        if let Some(token) = self.open_block.clone() {
            session.extend_block(&token, line);
            if PRIVATE_KEY_END.is_match(line) {
                session.finish_block(&token);
                self.open_block = None;
            }
            return (String::new(), Counts::new());
        }
        if redactor.secrets {
            if let Some(begin) = PRIVATE_KEY_BEGIN.find(line) {
                let whole_in_one_line = line.get(begin.end()..).is_some_and(|rest| PRIVATE_KEY_END.is_match(rest));
                if !whole_in_one_line {
                    let token = session.begin_block(&Kind::Secret, line);
                    self.open_block = Some(token.clone());
                    let mut counts = Counts::new();
                    counts.add("private_key");
                    return (token, counts);
                }
            }
        }
        redactor.redact(session, line)
    }
}
