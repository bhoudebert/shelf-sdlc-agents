//! One policy file, as written. Each layer holds only what it changes; [`crate::Policy::resolve`] merges them.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::category::{Category, Decision};

/// The preset a layer extends.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Profile {
    /// Everything is classified and logged, nothing is blocked.
    Observe,
    /// Dangerous actions ask, exfiltration and obfuscation are denied, routine work flows.
    Guarded,
    /// Everything risky asks or is denied.
    Strict,
    /// Nobody answers, so nothing asks: catastrophic actions are denied, routine work is allowed and logged.
    Unattended,
    /// What Shelf runs: `unattended`, plus the operator's own locked file.
    Shelf,
}

impl Profile {
    /// The name used in files and logs.
    #[must_use]
    pub const fn name(self) -> &'static str {
        match self {
            Self::Observe => "observe",
            Self::Guarded => "guarded",
            Self::Strict => "strict",
            Self::Unattended => "unattended",
            Self::Shelf => "shelf",
        }
    }
}

/// Whether decisions are enforced.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    /// Asks and denies are carried out.
    Enforce,
    /// Asks and denies are logged and let through.
    Audit,
}

/// What to do with hook input that cannot be read.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OnError {
    /// Let the call through, with a message.
    Open,
    /// Refuse the call.
    Closed,
}

/// An explicit decision for the command lines a pattern matches.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuleSpec {
    /// A name for logs and for `warden explain`.
    pub id: String,
    /// A regular expression, matched against the whole command line after rewrites.
    #[serde(rename = "match")]
    pub pattern: String,
    /// The decision when it matches.
    pub decision: Decision,
    /// Why, shown to the model and in the log.
    #[serde(default)]
    pub reason: String,
}

/// A rewrite of a command line, applied before it is judged.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RewriteSpec {
    /// A name for logs.
    pub id: String,
    /// A regular expression.
    #[serde(rename = "match")]
    pub pattern: String,
    /// The replacement; `${1}` groups are allowed.
    pub replace: String,
}

/// File lists, as globs with `**` and a leading `~`.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PathsSpec {
    /// Credentials: reading one is `secret_access`.
    #[serde(default)]
    pub deny_read: Vec<String>,
    /// Never to be written: any write is `destructive`.
    #[serde(default)]
    pub deny_write: Vec<String>,
    /// Agent and Warden configuration: any write is `tamper`, always denied.
    #[serde(default)]
    pub protected: Vec<String>,
    /// Personal data: the Read tool refuses them, shell reads are redacted.
    #[serde(default)]
    pub pii: Vec<String>,
    /// When set, writes outside these directories (and `/tmp`) are `out_of_scope`.
    #[serde(default)]
    pub scope: Option<Vec<String>>,
}

/// Domain lists.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkSpec {
    /// When set and not empty, every other host is denied.
    #[serde(default)]
    pub allow_domains: Option<Vec<String>>,
    /// Hosts that are always denied.
    #[serde(default)]
    pub deny_domains: Vec<String>,
}

/// Agent tools to deny or ask about by name, as regular expressions.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ToolsSpec {
    /// Tool names to refuse.
    #[serde(default)]
    pub deny: Vec<String>,
    /// Tool names to ask about.
    #[serde(default)]
    pub ask: Vec<String>,
}

/// Where the audit log goes, and whether there is one.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuditSpec {
    /// Whether decisions are logged.
    pub enabled: Option<bool>,
    /// The directory of the log; `~` is expanded.
    pub dir: Option<String>,
}

/// What to do with personal data in a prompt.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PromptMode {
    /// Ignore it.
    Off,
    /// Let the prompt through and warn.
    Warn,
    /// Refuse the prompt.
    Block,
}

/// What to do when the Read tool opens a personal-data file, whose content cannot be redacted on the way.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadTool {
    /// Let it open.
    Allow,
    /// Refuse, and point at the shell, whose output is redacted.
    Deny,
}

/// A detector of the policy's own: a name, which becomes the token prefix, and a regular expression.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CustomSpec {
    /// The token prefix: `customer_id` gives `<CUSTOMER_ID_1>`.
    pub name: String,
    /// The pattern.
    pub pattern: String,
}

/// Personal data.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PiiSpec {
    /// Whether to look for it.
    pub enabled: Option<bool>,
    /// The kinds to look for: `email`, `phone`, `iban`, `card`, `nir`, `ssn`, `ip`.
    pub kinds: Option<Vec<String>>,
    /// Names that must never reach a model as they are.
    #[serde(default)]
    pub names: Vec<String>,
    /// Values to leave alone, as globs (`*@example.com`).
    #[serde(default)]
    pub allow: Vec<String>,
    /// Detectors of the policy's own.
    #[serde(default)]
    pub custom: Vec<CustomSpec>,
}

/// What is kept off the model.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RedactSpec {
    /// Whether allowed commands run through the redactor.
    pub outputs: Option<bool>,
    /// Whether credentials are redacted.
    pub secrets: Option<bool>,
    /// Whether MCP arguments are checked and pseudonymized.
    pub mcp: Option<bool>,
    /// What to do with personal data in a prompt.
    pub prompts: Option<PromptMode>,
    /// What to do when the Read tool opens a personal-data file.
    pub read_tool: Option<ReadTool>,
    /// Personal data.
    pub pii: Option<PiiSpec>,
}

/// Variables hidden from the commands the agent runs.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EnvSpec {
    /// Names or globs (`*_TOKEN`).
    #[serde(default)]
    pub hide: Vec<String>,
}

/// One policy file.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Layer {
    /// The format version; only 1 exists.
    pub version: Option<u32>,
    /// The preset this layer extends.
    pub profile: Option<Profile>,
    /// Enforce or only log.
    pub mode: Option<Mode>,
    /// Whether the layers above this one may loosen it.
    pub locked: Option<bool>,
    /// Whether a person can answer an ask.
    pub interactive: Option<bool>,
    /// What to do with hook input that cannot be read.
    pub on_error: Option<OnError>,
    /// A decision per category.
    #[serde(default)]
    pub categories: BTreeMap<Category, Decision>,
    /// Explicit overrides, matched in order.
    #[serde(default)]
    pub rules: Vec<RuleSpec>,
    /// Rewrites applied before judging.
    #[serde(default)]
    pub rewrites: Vec<RewriteSpec>,
    /// File lists.
    pub paths: Option<PathsSpec>,
    /// Domain lists.
    pub network: Option<NetworkSpec>,
    /// Tool lists.
    pub tools: Option<ToolsSpec>,
    /// The audit log.
    pub audit: Option<AuditSpec>,
    /// What is kept off the model.
    pub redact: Option<RedactSpec>,
    /// Variables hidden from commands.
    pub env: Option<EnvSpec>,
}

impl Layer {
    /// Read a layer from TOML.
    pub fn parse(text: &str) -> Result<Self, String> {
        let layer: Self = toml::from_str(text).map_err(|error| error.to_string())?;
        match layer.version {
            None | Some(1) => Ok(layer),
            Some(other) => Err(format!("unsupported policy version {other}: only 1 exists")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_layer_reads_every_section() {
        let layer = Layer::parse(
            r#"
version = 1
profile = "guarded"
locked = true
[categories]
exfil = "deny"
[[rules]]
id = "deploy"
match = '^\./deploy staging$'
decision = "allow"
reason = "routine"
[paths]
protected = ["infra/**"]
scope = ["."]
[network]
allow_domains = ["github.com"]
"#,
        )
        .expect("parses");
        assert_eq!(layer.profile, Some(Profile::Guarded));
        assert_eq!(layer.categories[&Category::Exfil], Decision::Deny);
        assert_eq!(layer.rules[0].id, "deploy");
        assert_eq!(layer.paths.expect("paths").scope, Some(vec![".".to_owned()]));
    }

    #[test]
    fn an_unknown_key_is_refused() {
        assert!(Layer::parse("colour = 1").is_err());
        assert!(Layer::parse("[categories]\nmadeup = \"deny\"").is_err());
    }

    #[test]
    fn a_wrong_version_is_refused() {
        assert!(Layer::parse("version = 2").is_err());
    }
}
