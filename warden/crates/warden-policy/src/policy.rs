//! The resolved policy: presets and layers merged, patterns compiled.

use std::collections::BTreeMap;
use std::fmt;
use std::path::Path;

use globset::{Glob, GlobSet, GlobSetBuilder};
use regex::Regex;

use crate::category::{Category, Decision};
use crate::layer::{Layer, Mode, OnError, Profile};
use crate::presets;

/// Why a set of layers could not be merged into a policy.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyError {
    /// A rule or rewrite pattern is not a regular expression.
    Pattern {
        /// The rule or rewrite.
        id: String,
        /// What the regex engine said.
        message: String,
    },
    /// A path glob is not valid.
    Glob {
        /// The glob.
        pattern: String,
        /// What the glob parser said.
        message: String,
    },
    /// A preset built into the binary does not parse: a bug in Warden.
    Preset(String),
}

impl fmt::Display for PolicyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Pattern { id, message } => write!(f, "rule or rewrite {id:?} has an invalid pattern: {message}"),
            Self::Glob { pattern, message } => write!(f, "invalid path glob {pattern:?}: {message}"),
            Self::Preset(message) => write!(f, "a built-in preset is broken: {message}"),
        }
    }
}

impl std::error::Error for PolicyError {}

/// An explicit decision for the command lines a pattern matches.
#[derive(Debug, Clone)]
pub struct Rule {
    /// The name.
    pub id: String,
    /// The compiled pattern.
    pub pattern: Regex,
    /// The decision when it matches.
    pub decision: Decision,
    /// Why.
    pub reason: String,
    /// The layer it came from.
    pub source: String,
}

/// A rewrite of a command line before it is judged.
#[derive(Debug, Clone)]
pub struct Rewrite {
    /// The name.
    pub id: String,
    /// The compiled pattern.
    pub pattern: Regex,
    /// The replacement.
    pub replace: String,
}

/// A list of path globs, with `~` expanded.
#[derive(Debug, Clone)]
pub struct PathSet {
    patterns: Vec<String>,
    set: GlobSet,
}

impl PathSet {
    /// Compile `patterns`, expanding a leading `~` to `home`.
    pub fn new(patterns: &[String], home: &Path) -> Result<Self, PolicyError> {
        let mut builder = GlobSetBuilder::new();
        for pattern in patterns {
            let expanded = match pattern.strip_prefix("~/") {
                Some(rest) => format!("{}/{rest}", home.display()),
                None if pattern == "~" => home.display().to_string(),
                None => pattern.clone(),
            };
            let glob = Glob::new(&expanded)
                .map_err(|error| PolicyError::Glob { pattern: pattern.clone(), message: error.to_string() })?;
            builder.add(glob);
        }
        let set = builder
            .build()
            .map_err(|error| PolicyError::Glob { pattern: String::new(), message: error.to_string() })?;
        Ok(Self { patterns: patterns.to_vec(), set })
    }

    /// Whether any candidate (a path as written, or made absolute) matches a glob.
    #[must_use]
    pub fn is_match<S: AsRef<str>>(&self, candidates: &[S]) -> bool {
        candidates.iter().any(|path| self.set.is_match(path.as_ref()))
    }

    /// The globs, as written.
    #[must_use]
    pub fn patterns(&self) -> &[String] {
        &self.patterns
    }
}

/// The file lists of a policy.
#[derive(Debug, Clone)]
pub struct Paths {
    /// Credentials.
    pub deny_read: PathSet,
    /// Never to be written.
    pub deny_write: PathSet,
    /// Agent and Warden configuration.
    pub protected: PathSet,
    /// Personal data.
    pub pii: PathSet,
    /// When set, the directories writes are confined to.
    pub scope: Option<Vec<String>>,
}

/// The domain lists of a policy.
#[derive(Debug, Clone, Default)]
pub struct Network {
    /// When set and not empty, every other host is denied.
    pub allow_domains: Option<Vec<String>>,
    /// Hosts that are always denied.
    pub deny_domains: Vec<String>,
}

impl Network {
    /// Whether `host` is on the list `domains`: the same name, or a subdomain of it.
    #[must_use]
    pub fn listed(domains: &[String], host: &str) -> bool {
        let host = host.to_ascii_lowercase();
        domains.iter().any(|domain| {
            let domain = domain.to_ascii_lowercase();
            host == domain || host.ends_with(&format!(".{domain}"))
        })
    }

    /// Whether the policy denies `host`: on the deny list, or off a non-empty allow list.
    #[must_use]
    pub fn denies(&self, host: &str) -> Option<String> {
        if Self::listed(&self.deny_domains, host) {
            return Some(format!("{host} is on the list of denied domains"));
        }
        match &self.allow_domains {
            Some(allowed) if !allowed.is_empty() && !Self::listed(allowed, host) => {
                Some(format!("{host} is not on the list of allowed domains"))
            }
            _ => None,
        }
    }
}

/// The audit log of a policy.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Audit {
    /// Whether decisions are logged.
    pub enabled: bool,
    /// The directory of the log, `~` not yet expanded.
    pub dir: String,
}

/// The policy a tool call is judged against.
#[derive(Debug, Clone)]
pub struct Policy {
    /// The preset in force.
    pub profile: Profile,
    /// Enforce or only log.
    pub mode: Mode,
    /// Whether a person can answer an ask.
    pub interactive: bool,
    /// What to do with hook input that cannot be read.
    pub on_error: OnError,
    /// Whether some layer was locked.
    pub locked: bool,
    /// The decision of each category.
    pub categories: BTreeMap<Category, Decision>,
    /// Explicit overrides, the highest layer first.
    pub rules: Vec<Rule>,
    /// Rewrites, in order.
    pub rewrites: Vec<Rewrite>,
    /// File lists.
    pub paths: Paths,
    /// Domain lists.
    pub network: Network,
    /// Tool names to refuse.
    pub tools_deny: Vec<Regex>,
    /// Tool names to ask about.
    pub tools_ask: Vec<Regex>,
    /// The audit log.
    pub audit: Audit,
    /// The layers that contributed, lowest first.
    pub sources: Vec<String>,
    /// Things a layer tried that a locked layer or a fixed rule did not allow, and so were ignored.
    pub warnings: Vec<String>,
}

/// What a locked layer fixes for the layers above it: a snapshot, so each flag is its own fact.
#[allow(clippy::struct_excessive_bools)]
struct Floor {
    categories: BTreeMap<Category, Decision>,
    mode: Mode,
    interactive: bool,
    on_error: OnError,
    scope_set: bool,
    allow_domains_set: bool,
    audit_enabled: bool,
}

#[derive(Default)]
struct Lists {
    deny_read: Vec<String>,
    deny_write: Vec<String>,
    protected: Vec<String>,
    pii: Vec<String>,
}

fn extend_unique(into: &mut Vec<String>, from: &[String]) {
    for item in from {
        if !into.contains(item) {
            into.push(item.clone());
        }
    }
}

fn compile(id: &str, pattern: &str) -> Result<Regex, PolicyError> {
    Regex::new(pattern).map_err(|error| PolicyError::Pattern { id: id.to_owned(), message: error.to_string() })
}

impl Policy {
    /// Merge layers, lowest precedence first, on top of the preset they name.
    ///
    /// Lists add up and nothing can be removed; a decision per category overrides; a scalar overrides. A layer with
    /// `locked = true` fixes what it says: the layers after it cannot loosen a decision, add an `allow` rule, turn
    /// the mode to audit, make asks answerable, widen the scope or the allowed domains, or switch the preset. Such an
    /// attempt is ignored and reported in [`Policy::warnings`].
    pub fn resolve(layers: &[(String, Layer)], home: &Path) -> Result<Self, PolicyError> {
        let mut warnings = Vec::new();
        let profile = chosen_profile(layers, &mut warnings);
        let mut stack: Vec<(String, Layer)> = presets::layers(profile)?;
        stack.extend(layers.iter().cloned());
        Fold::run(&stack, profile, home, warnings)
    }

    /// The decision for a category; a category nobody mentions is allowed.
    #[must_use]
    pub fn decision(&self, category: Category) -> Decision {
        if category.always_denied() {
            return Decision::Deny;
        }
        self.categories.get(&category).copied().unwrap_or(Decision::Allow)
    }

    /// Apply the rewrites to a command line. Returns the new line and the ids of the rewrites that changed it.
    #[must_use]
    pub fn rewrite(&self, command: &str) -> (String, Vec<String>) {
        let mut line = command.to_owned();
        let mut applied = Vec::new();
        for rewrite in &self.rewrites {
            let replaced = rewrite.pattern.replace_all(&line, rewrite.replace.as_str());
            if replaced != line {
                line = replaced.into_owned();
                applied.push(rewrite.id.clone());
            }
        }
        (line, applied)
    }

    /// The first rule that matches a command line.
    #[must_use]
    pub fn rule_for(&self, command: &str) -> Option<&Rule> {
        self.rules.iter().find(|rule| rule.pattern.is_match(command))
    }

    /// What the policy says about an agent tool by name, if anything.
    #[must_use]
    pub fn tool_decision(&self, tool: &str) -> Option<Decision> {
        if self.tools_deny.iter().any(|pattern| pattern.is_match(tool)) {
            Some(Decision::Deny)
        } else if self.tools_ask.iter().any(|pattern| pattern.is_match(tool)) {
            Some(Decision::Ask)
        } else {
            None
        }
    }
}

fn chosen_profile(layers: &[(String, Layer)], warnings: &mut Vec<String>) -> Profile {
    let mut profile = Profile::Guarded;
    let mut locked_before = false;
    for (name, layer) in layers {
        if let Some(wanted) = layer.profile {
            if locked_before {
                warnings.push(format!(
                    "{name}: profile {} ignored: a locked layer already chose the preset",
                    wanted.name()
                ));
            } else {
                profile = wanted;
            }
        }
        locked_before |= layer.locked == Some(true);
    }
    profile
}

struct Fold {
    mode: Mode,
    interactive: bool,
    on_error: OnError,
    categories: BTreeMap<Category, Decision>,
    rules: Vec<(usize, Rule)>,
    rewrites: Vec<Rewrite>,
    lists: Lists,
    scope: Option<Vec<String>>,
    allow_domains: Option<Vec<String>>,
    deny_domains: Vec<String>,
    tools_deny: Vec<String>,
    tools_ask: Vec<String>,
    audit_enabled: bool,
    audit_dir: String,
    locked: bool,
    floor: Option<Floor>,
    warnings: Vec<String>,
}

impl Fold {
    fn run(
        stack: &[(String, Layer)],
        profile: Profile,
        home: &Path,
        warnings: Vec<String>,
    ) -> Result<Policy, PolicyError> {
        let mut fold = Self {
            mode: Mode::Enforce,
            interactive: true,
            on_error: OnError::Closed,
            categories: BTreeMap::new(),
            rules: Vec::new(),
            rewrites: Vec::new(),
            lists: Lists::default(),
            scope: None,
            allow_domains: None,
            deny_domains: Vec::new(),
            tools_deny: Vec::new(),
            tools_ask: Vec::new(),
            audit_enabled: true,
            audit_dir: "~/.local/share/warden/audit".to_owned(),
            locked: false,
            floor: None,
            warnings,
        };
        for (index, (name, layer)) in stack.iter().enumerate() {
            fold.apply(index, name, layer)?;
        }
        fold.finish(stack, profile, home)
    }

    fn apply(&mut self, index: usize, name: &str, layer: &Layer) -> Result<(), PolicyError> {
        self.scalars(name, layer);
        self.decisions(name, layer);
        for spec in &layer.rules {
            if self.floor.is_some() && spec.decision == Decision::Allow {
                self.warnings
                    .push(format!("{name}: rule {} ignored: a locked layer does not allow `allow` rules", spec.id));
                continue;
            }
            let rule = Rule {
                id: spec.id.clone(),
                pattern: compile(&spec.id, &spec.pattern)?,
                decision: spec.decision,
                reason: spec.reason.clone(),
                source: name.to_owned(),
            };
            self.rules.push((index, rule));
        }
        for spec in &layer.rewrites {
            self.rewrites.push(Rewrite {
                id: spec.id.clone(),
                pattern: compile(&spec.id, &spec.pattern)?,
                replace: spec.replace.clone(),
            });
        }
        self.lists_and_domains(name, layer);
        self.audit(name, layer);
        if layer.locked == Some(true) {
            self.locked = true;
            self.floor = Some(Floor {
                categories: self.categories.clone(),
                mode: self.mode,
                interactive: self.interactive,
                on_error: self.on_error,
                scope_set: self.scope.is_some(),
                allow_domains_set: self.allow_domains.is_some(),
                audit_enabled: self.audit_enabled,
            });
        }
        Ok(())
    }

    fn scalars(&mut self, name: &str, layer: &Layer) {
        if let Some(mode) = layer.mode {
            if self.floor.as_ref().is_some_and(|f| f.mode == Mode::Enforce) && mode == Mode::Audit {
                self.warnings.push(format!("{name}: mode audit ignored: a locked layer enforces"));
            } else {
                self.mode = mode;
            }
        }
        if let Some(interactive) = layer.interactive {
            if self.floor.as_ref().is_some_and(|f| !f.interactive) && interactive {
                self.warnings.push(format!("{name}: interactive ignored: a locked layer has nobody to ask"));
            } else {
                self.interactive = interactive;
            }
        }
        if let Some(on_error) = layer.on_error {
            if self.floor.as_ref().is_some_and(|f| f.on_error == OnError::Closed) && on_error == OnError::Open {
                self.warnings.push(format!("{name}: on_error open ignored: a locked layer fails closed"));
            } else {
                self.on_error = on_error;
            }
        }
    }

    fn decisions(&mut self, name: &str, layer: &Layer) {
        for (category, decision) in &layer.categories {
            if category.always_denied() && *decision != Decision::Deny {
                self.warnings.push(format!("{name}: {category} stays deny: it is always denied"));
                continue;
            }
            let fixed = self.floor.as_ref().and_then(|f| f.categories.get(category)).copied();
            if fixed.is_some_and(|fixed| *decision < fixed) {
                self.warnings.push(format!(
                    "{name}: {category} = {decision} ignored: a locked layer says {}",
                    fixed.unwrap_or(Decision::Deny)
                ));
                continue;
            }
            self.categories.insert(*category, *decision);
        }
    }

    fn audit(&mut self, name: &str, layer: &Layer) {
        let Some(spec) = &layer.audit else { return };
        if let Some(enabled) = spec.enabled {
            if !enabled && self.floor.as_ref().is_some_and(|f| f.audit_enabled) {
                self.warnings.push(format!("{name}: audit.enabled = false ignored: a locked layer keeps the log on"));
            } else {
                self.audit_enabled = enabled;
            }
        }
        if let Some(dir) = &spec.dir {
            if self.floor.is_some() {
                self.warnings.push(format!("{name}: audit.dir ignored: a locked layer fixed where the log goes"));
            } else {
                self.audit_dir.clone_from(dir);
            }
        }
    }

    fn lists_and_domains(&mut self, name: &str, layer: &Layer) {
        if let Some(paths) = &layer.paths {
            extend_unique(&mut self.lists.deny_read, &paths.deny_read);
            extend_unique(&mut self.lists.deny_write, &paths.deny_write);
            extend_unique(&mut self.lists.protected, &paths.protected);
            extend_unique(&mut self.lists.pii, &paths.pii);
            if let Some(scope) = &paths.scope {
                if self.floor.as_ref().is_some_and(|f| f.scope_set) {
                    self.warnings.push(format!("{name}: scope ignored: a locked layer fixed it"));
                } else {
                    self.scope = Some(scope.clone());
                }
            }
        }
        if let Some(network) = &layer.network {
            extend_unique(&mut self.deny_domains, &network.deny_domains);
            if let Some(allowed) = &network.allow_domains {
                if self.floor.as_ref().is_some_and(|f| f.allow_domains_set) {
                    self.warnings.push(format!("{name}: allow_domains ignored: a locked layer fixed it"));
                } else {
                    self.allow_domains = Some(allowed.clone());
                }
            }
        }
        if let Some(tools) = &layer.tools {
            extend_unique(&mut self.tools_deny, &tools.deny);
            extend_unique(&mut self.tools_ask, &tools.ask);
        }
    }

    fn finish(self, stack: &[(String, Layer)], profile: Profile, home: &Path) -> Result<Policy, PolicyError> {
        let mut rules = self.rules;
        rules.sort_by_key(|(index, _)| std::cmp::Reverse(*index));
        let tools = |patterns: &[String]| -> Result<Vec<Regex>, PolicyError> {
            patterns.iter().map(|pattern| compile("tools", pattern)).collect()
        };
        Ok(Policy {
            profile,
            mode: self.mode,
            interactive: self.interactive,
            on_error: self.on_error,
            locked: self.locked,
            categories: self.categories,
            rules: rules.into_iter().map(|(_, rule)| rule).collect(),
            rewrites: self.rewrites,
            paths: Paths {
                deny_read: PathSet::new(&self.lists.deny_read, home)?,
                deny_write: PathSet::new(&self.lists.deny_write, home)?,
                protected: PathSet::new(&self.lists.protected, home)?,
                pii: PathSet::new(&self.lists.pii, home)?,
                scope: self.scope,
            },
            network: Network { allow_domains: self.allow_domains, deny_domains: self.deny_domains },
            tools_deny: tools(&self.tools_deny)?,
            tools_ask: tools(&self.tools_ask)?,
            audit: Audit { enabled: self.audit_enabled, dir: self.audit_dir },
            sources: stack.iter().map(|(name, _)| name.clone()).collect(),
            warnings: self.warnings,
        })
    }
}
