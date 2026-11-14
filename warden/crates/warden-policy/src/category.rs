//! What a finding is called, and what the policy can do about it.

use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};

/// What to do with a tool call. The order is the order of strictness: a deny beats an ask beats an allow.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Decision {
    /// Let it run.
    Allow,
    /// Ask a person, where there is one to ask.
    Ask,
    /// Refuse it, with a reason.
    Deny,
}

impl fmt::Display for Decision {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Allow => "allow",
            Self::Ask => "ask",
            Self::Deny => "deny",
        })
    }
}

macro_rules! categories {
    ($($variant:ident => $name:literal),+ $(,)?) => {
        /// A kind of risk the classifier can name.
        #[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
        #[serde(rename_all = "snake_case")]
        pub enum Category { $($variant),+ }

        impl Category {
            /// Every category, in the order of the documentation.
            pub const ALL: &'static [Category] = &[$(Category::$variant),+];

            /// The name used in policy files and logs.
            #[must_use]
            pub const fn name(self) -> &'static str {
                match self { $(Category::$variant => $name),+ }
            }
        }

        impl FromStr for Category {
            type Err = String;
            fn from_str(text: &str) -> Result<Self, String> {
                match text { $($name => Ok(Category::$variant),)+ other => Err(format!("unknown category {other:?}")) }
            }
        }
    };
}

categories! {
    Destructive => "destructive",
    Delete => "delete",
    VcsDestructive => "vcs_destructive",
    VcsForce => "vcs_force",
    BypassChecks => "bypass_checks",
    Exfil => "exfil",
    Network => "network",
    BlockedDomain => "blocked_domain",
    Privilege => "privilege",
    RemoteExec => "remote_exec",
    PackageInstall => "package_install",
    Publish => "publish",
    SecretAccess => "secret_access",
    EnvDump => "env_dump",
    Obfuscation => "obfuscation",
    Eval => "eval",
    DynamicExec => "dynamic_exec",
    InterpreterExec => "interpreter_exec",
    InterpreterShell => "interpreter_shell",
    OutOfScope => "out_of_scope",
    Tamper => "tamper",
    SecretWrite => "secret_write",
    SupplyChain => "supply_chain",
    PiiRead => "pii_read",
    PiiOutbound => "pii_outbound",
    PiiPrompt => "pii_prompt",
    SecretPrompt => "secret_prompt",
    Leak => "leak",
}

impl Category {
    /// Categories whose decision is deny whatever a policy or a rule says.
    #[must_use]
    pub const fn always_denied(self) -> bool {
        matches!(self, Self::Tamper | Self::BlockedDomain)
    }
}

impl fmt::Display for Category {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.name())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decisions_are_ordered_by_strictness() {
        assert!(Decision::Allow < Decision::Ask && Decision::Ask < Decision::Deny);
    }

    #[test]
    fn every_category_round_trips_through_its_name() {
        for category in Category::ALL {
            assert_eq!(category.name().parse::<Category>(), Ok(*category));
        }
        assert!("nonsense".parse::<Category>().is_err());
    }

    #[test]
    fn only_tampering_and_blocked_domains_are_always_denied() {
        let always: Vec<_> = Category::ALL.iter().filter(|c| c.always_denied()).collect();
        assert_eq!(always, [&Category::BlockedDomain, &Category::Tamper]);
    }
}
