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

/// Build the policy: the preset, then the global file, then the repository file.
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
        if let Some(repo) = repo_path(&sources.cwd) {
            layers.push(read_layer(&repo)?);
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
}
