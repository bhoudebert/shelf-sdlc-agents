//! Finding and reading the policy files, and building the policy from them.

use std::path::{Path, PathBuf};

use warden_policy::{Layer, Policy, Profile};

/// What to read, as the command line asked.
#[derive(Debug, Clone, Default)]
pub struct Sources {
    /// A preset to start from, below every file.
    pub profile: Option<Profile>,
    /// Whether to read the global and repository files at all.
    pub files: bool,
    /// An explicit global file, in place of the default one.
    pub global: Option<PathBuf>,
    /// The operator's policy: a file an organisation controls, always locked, between the global and the repository's.
    /// Taken from `WARDEN_OPERATOR_POLICY` when not given.
    pub operator: Option<PathBuf>,
    /// The overlay: the rules an administrator adds from the web page. Taken from `WARDEN_OVERLAY_POLICY` when not given.
    pub overlay: Option<PathBuf>,
    /// The directory to look for the repository file from.
    pub cwd: PathBuf,
    /// The home directory.
    pub home: PathBuf,
}

/// The default global policy: `$WARDEN_POLICY`, or `~/.config/warden/policy.toml`.
fn global_path(sources: &Sources) -> PathBuf {
    if let Some(explicit) = &sources.global {
        return explicit.clone();
    }
    if let Some(from_env) = std::env::var_os("WARDEN_POLICY") {
        return PathBuf::from(from_env);
    }
    sources.home.join(".config/warden/policy.toml")
}

/// The operator's policy file: the one given, or `$WARDEN_OPERATOR_POLICY`.
fn operator_path(sources: &Sources) -> Option<PathBuf> {
    sources.operator.clone().or_else(|| std::env::var_os("WARDEN_OPERATOR_POLICY").map(PathBuf::from))
}

/// The overlay file: the one given, or `$WARDEN_OVERLAY_POLICY`.
fn overlay_path(sources: &Sources) -> Option<PathBuf> {
    sources.overlay.clone().or_else(|| std::env::var_os("WARDEN_OVERLAY_POLICY").map(PathBuf::from))
}

/// The nearest `.warden/policy.toml` from `start` up to the root of the repository (or the filesystem).
fn repo_path(start: &Path) -> Option<PathBuf> {
    for dir in start.ancestors() {
        let candidate = dir.join(".warden/policy.toml");
        if candidate.is_file() {
            return Some(candidate);
        }
        if dir.join(".git").exists() {
            break;
        }
    }
    None
}

fn read_layer(path: &Path) -> Result<(String, Layer), String> {
    let text = std::fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let layer = Layer::parse(&text).map_err(|error| format!("{}: {error}", path.display()))?;
    Ok((path.display().to_string(), layer))
}

/// Build the policy: the preset, then the global, operator and repository files, then the overlay.
pub fn policy(sources: &Sources) -> Result<Policy, String> {
    let mut layers: Vec<(String, Layer)> = Vec::new();
    if let Some(profile) = sources.profile {
        let layer = Layer::parse(&format!("profile = \"{}\"", profile.name()))?;
        layers.push(("--profile".to_owned(), layer));
    }
    if sources.files {
        let global = global_path(sources);
        if global.is_file() {
            layers.push(read_layer(&global)?);
        }
        if let Some(operator) = operator_path(sources).filter(|path| path.is_file()) {
            let (name, mut layer) = read_layer(&operator)?;
            layer.locked = Some(true);
            layers.push((format!("operator:{name}"), layer));
        }
        if let Some(repo) = repo_path(&sources.cwd) {
            layers.push(read_layer(&repo)?);
        }
        if let Some(overlay) = overlay_path(sources).filter(|path| path.is_file()) {
            let (name, layer) = read_layer(&overlay)?;
            let layer = layer.into_overlay().map_err(|error| format!("{name}: {error}"))?;
            layers.push((format!("overlay:{name}"), layer));
        }
    }
    Policy::resolve(&layers, &sources.home).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("warden-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("temp dir");
        dir
    }

    #[test]
    fn the_repository_file_is_found_from_a_subdirectory_and_the_global_file_comes_first() {
        let root = temp_dir("layers");
        std::fs::create_dir_all(root.join(".git")).expect("git dir");
        std::fs::create_dir_all(root.join(".warden")).expect("warden dir");
        std::fs::create_dir_all(root.join("a/b")).expect("subdirectory");
        std::fs::write(root.join(".warden/policy.toml"), "[categories]\npublish = \"deny\"").expect("repo file");
        let global = root.join("global.toml");
        std::fs::write(&global, "profile = \"strict\"").expect("global file");
        let sources = Sources {
            files: true,
            global: Some(global),
            cwd: root.join("a/b"),
            home: root.clone(),
            ..Sources::default()
        };
        let policy = policy(&sources).expect("policy");
        assert_eq!(policy.profile, Profile::Strict);
        assert_eq!(policy.sources.len(), 4, "{:?}", policy.sources);
        assert!(policy.sources[2].ends_with("global.toml"));
        assert!(policy.sources[3].ends_with(".warden/policy.toml"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn the_operators_file_is_always_locked_and_sits_between_the_global_and_the_repository_files() {
        let root = temp_dir("operator");
        std::fs::create_dir_all(root.join(".git")).expect("git dir");
        std::fs::create_dir_all(root.join(".warden")).expect("warden dir");
        // The repository tries to loosen the operator and to tighten one more thing.
        std::fs::write(root.join(".warden/policy.toml"), "[categories]\nexfil = \"allow\"\npackage_install = \"deny\"")
            .expect("repo file");
        let operator = root.join("operator.toml");
        std::fs::write(&operator, "profile = \"shelf\"\n[categories]\nexfil = \"deny\"").expect("operator file");
        let sources = Sources {
            files: true,
            operator: Some(operator),
            cwd: root.clone(),
            home: root.clone(),
            global: Some(root.join("none.toml")),
            ..Sources::default()
        };
        let policy = policy(&sources).expect("policy");
        assert!(policy.locked, "the operator's layer is locked although its file does not say so");
        assert_eq!(policy.decision(warden_policy::Category::Exfil), warden_policy::Decision::Deny);
        assert_eq!(
            policy.decision(warden_policy::Category::PackageInstall),
            warden_policy::Decision::Deny,
            "tightening works"
        );
        assert_eq!(policy.warnings.len(), 1, "{:?}", policy.warnings);
        assert!(policy.sources.iter().any(|s| s.starts_with("operator:")), "{:?}", policy.sources);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn without_files_only_the_preset_counts() {
        let sources = Sources {
            profile: Some(Profile::Unattended),
            cwd: "/".into(),
            home: "/home/dev".into(),
            ..Sources::default()
        };
        let policy = policy(&sources).expect("policy");
        assert_eq!(policy.profile, Profile::Unattended);
        assert_eq!(policy.sources.len(), 3);
    }

    #[test]
    fn a_broken_file_names_itself() {
        let root = temp_dir("broken");
        let file = root.join("p.toml");
        std::fs::write(&file, "colour = 1").expect("file");
        let sources =
            Sources { files: true, global: Some(file), cwd: root.clone(), home: root.clone(), ..Sources::default() };
        let error = policy(&sources).expect_err("refused");
        assert!(error.contains("p.toml"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    fn overlay_sources(root: &Path, operator: &str, overlay: Option<&str>) -> Sources {
        let operator_file = root.join("operator.toml");
        std::fs::write(&operator_file, operator).expect("operator file");
        let overlay_file = root.join("overlay.toml");
        if let Some(text) = overlay {
            std::fs::write(&overlay_file, text).expect("overlay file");
        }
        Sources {
            profile: Some(Profile::Shelf),
            files: true,
            operator: Some(operator_file),
            overlay: Some(overlay_file),
            cwd: root.to_path_buf(),
            home: root.to_path_buf(),
            global: Some(root.join("none.toml")),
        }
    }

    const FORCE: &str = "git push --force origin shelf/work-1";

    fn rule_for(command: &str, decision: &str) -> String {
        let pattern = command.replace('.', "\\.");
        format!("[[rules]]\nid = \"ui\"\nmatch = '^{pattern}$'\ndecision = \"{decision}\"\nreason = \"approved\"\n")
    }

    #[test]
    fn an_overlay_rule_allows_a_command_although_the_operators_file_is_locked() {
        let root = temp_dir("overlay-allow");
        let sources = overlay_sources(
            &root,
            "profile = \"guarded\"\n[categories]\nvcs_force = \"deny\"",
            Some(&rule_for(FORCE, "allow")),
        );
        let policy = policy(&sources).expect("policy");
        assert!(policy.sources.iter().any(|s| s.starts_with("overlay:")), "{:?}", policy.sources);
        let rule = policy.rule_for(FORCE).expect("the overlay rule matches");
        assert_eq!(rule.decision, warden_policy::Decision::Allow);
        assert!(rule.source.starts_with("overlay:"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn an_earlier_rule_that_denies_beats_the_overlays_allow() {
        let root = temp_dir("overlay-earlier");
        let operator = format!("profile = \"guarded\"\n{}", rule_for(FORCE, "deny").replace("\"ui\"", "\"never\""));
        let sources = overlay_sources(&root, &operator, Some(&rule_for(FORCE, "allow")));
        let policy = policy(&sources).expect("policy");
        let rule = policy.rule_for(FORCE).expect("a rule matches");
        assert_eq!(rule.decision, warden_policy::Decision::Deny);
        assert_eq!(rule.id, "never");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn an_overlay_can_deny_a_host() {
        let root = temp_dir("overlay-host");
        let sources =
            overlay_sources(&root, "profile = \"shelf\"", Some("[network]\ndeny_domains = [\"example.org\"]"));
        let policy = policy(&sources).expect("policy");
        assert!(policy.network.denies("example.org").is_some());
        assert!(policy.network.denies("docs.rs").is_none());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn an_overlay_that_holds_more_than_rules_and_domains_is_refused_with_what_it_may_hold() {
        let root = temp_dir("overlay-more");
        for text in [
            "[categories]\nexfil = \"allow\"",
            "profile = \"observe\"",
            "locked = false",
            "[network]\nallow_domains = [\"example.org\"]",
            "[paths]\ndeny_read = [\"x\"]",
        ] {
            let sources = overlay_sources(&root, "profile = \"shelf\"", Some(text));
            let error = policy(&sources).expect_err(text);
            assert!(error.contains("an overlay may hold only [[rules]] and [network] deny_domains"), "{text}: {error}");
        }
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn no_overlay_file_changes_nothing() {
        let root = temp_dir("overlay-none");
        let with = policy(&overlay_sources(&root, "profile = \"shelf\"", None)).expect("policy");
        let _ = std::fs::remove_file(root.join("overlay.toml"));
        assert!(!with.sources.iter().any(|s| s.starts_with("overlay:")));
        let _ = std::fs::remove_dir_all(root);
    }
}
