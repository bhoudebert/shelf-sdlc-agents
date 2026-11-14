use serde::{Deserialize, Serialize};

use crate::kind::Kind;

/// A user-supplied pattern; whatever it matches is replaced by a token named after `name`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CustomPattern {
    /// The detector name; the token prefix comes from it (`customer_id` gives `<CUSTOMER_ID_1>`).
    pub name: String,
    /// The regular expression, in the syntax of the `regex` crate.
    pub pattern: String,
}

/// What to look for in the way of personal data.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct PiiConfig {
    /// Whether personal data is looked for at all (this includes `names` and `custom`).
    pub enabled: bool,
    /// Which of Email, Phone, Iban, Card, Nir, Ssn and Ip to detect; other kinds are ignored here.
    pub kinds: Vec<Kind>,
    /// Exact names, matched case-insensitively on word boundaries, replaced as [`Kind::Person`].
    pub names: Vec<String>,
    /// Globs, matched case-insensitively against a found value, for values that must be left alone.
    pub allow: Vec<String>,
    /// Extra patterns.
    pub custom: Vec<CustomPattern>,
}

impl Default for PiiConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            kinds: vec![Kind::Email, Kind::Phone, Kind::Iban, Kind::Card, Kind::Nir, Kind::Ssn],
            names: Vec::new(),
            allow: ["*@example.com", "*@example.org", "noreply@*", "no-reply@*", "git@*", "*@users.noreply.github.com"]
                .map(str::to_owned)
                .to_vec(),
            custom: Vec::new(),
        }
    }
}

/// What a [`crate::Redactor`] looks for.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    /// Whether credentials are looked for.
    pub secrets: bool,
    /// Personal data.
    pub pii: PiiConfig,
}

impl Default for Config {
    fn default() -> Self {
        Self { secrets: true, pii: PiiConfig::default() }
    }
}
