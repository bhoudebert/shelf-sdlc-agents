//! Paths as an agent writes them, made comparable: `~` and `$HOME` expanded, relative paths made absolute.

use std::path::{Component, Path, PathBuf};

use warden_shell::Word;

/// Where the agent is and who it runs as: what a relative path or a `~` means.
#[derive(Debug, Clone)]
pub struct Context {
    /// The home directory.
    pub home: PathBuf,
    /// The working directory of the tool call.
    pub cwd: PathBuf,
}

impl Context {
    /// A context for the current process: `$HOME` and the current directory.
    #[must_use]
    pub fn from_env() -> Self {
        let home = std::env::var_os("HOME").map_or_else(|| PathBuf::from("/"), PathBuf::from);
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/"));
        Self { home, cwd }
    }

    /// Expand `~` and `$HOME` in text written as a path.
    #[must_use]
    pub fn expand(&self, text: &str) -> String {
        let home = self.home.display().to_string();
        let text = text.replace("${HOME}", &home).replace("$HOME", &home);
        match text.strip_prefix('~') {
            Some(rest) if rest.is_empty() || rest.starts_with('/') => format!("{home}{rest}"),
            _ => text,
        }
    }

    /// The path made absolute and lexically cleaned (`.` and `..` resolved without touching the disk).
    #[must_use]
    pub fn absolute(&self, text: &str) -> PathBuf {
        let expanded = self.expand(text);
        let path = Path::new(&expanded);
        let joined = if path.is_absolute() { path.to_path_buf() } else { self.cwd.join(path) };
        let mut clean = PathBuf::new();
        for part in joined.components() {
            match part {
                Component::ParentDir => {
                    clean.pop();
                }
                Component::CurDir => {}
                other => clean.push(other.as_os_str()),
            }
        }
        clean
    }

    /// The text of a word as a path when it is known before the command runs: its static text, or text whose only
    /// expansion is `$HOME`. `None` when it depends on anything else.
    #[must_use]
    pub fn resolved(&self, word: &Word) -> Option<String> {
        if let Some(value) = &word.value {
            return Some(value.clone());
        }
        let unquoted = word.raw.trim_matches(|c| c == '"' || c == '\'');
        let expanded = self.expand(unquoted);
        (!expanded.contains('$') && !expanded.contains('`')).then_some(expanded)
    }

    /// The forms of a word to compare against a glob: as written (expanded) and absolute.
    #[must_use]
    pub fn candidates(&self, word: &Word) -> Vec<String> {
        let Some(resolved) = self.resolved(word) else { return Vec::new() };
        let text = resolved.trim_end_matches('*');
        if text.is_empty() {
            return Vec::new();
        }
        let written = self.expand(text);
        let absolute = self.absolute(text).display().to_string();
        if written == absolute { vec![written] } else { vec![written, absolute] }
    }

    /// Whether `absolute` is inside the working directory.
    #[must_use]
    pub fn in_workspace(&self, absolute: &Path) -> bool {
        absolute.starts_with(&self.cwd)
    }

    /// Whether `absolute` is inside one of the scope directories (each relative to the working directory).
    #[must_use]
    pub fn in_scope(&self, absolute: &Path, scope: &[String]) -> bool {
        scope.iter().any(|dir| absolute.starts_with(self.absolute(dir)))
    }
}

/// Whether a path is a temporary directory, where writes are always in scope.
#[must_use]
pub fn is_temporary(absolute: &Path) -> bool {
    ["/tmp", "/private/tmp", "/var/tmp", "/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"]
        .iter()
        .any(|dir| absolute.starts_with(dir))
}

/// Whether a path is, or is inside, a place the system or the whole home directory lives.
#[must_use]
pub fn is_system_directory(absolute: &Path, home: &Path) -> bool {
    const INSIDE: [&str; 18] = [
        "/usr",
        "/etc",
        "/var",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/opt",
        "/boot",
        "/sys",
        "/proc",
        "/dev",
        "/root",
        "/srv",
        "/mnt",
        "/System",
        "/Library",
        "/Applications",
    ];
    const EXACT: [&str; 4] = ["/", "/home", "/Users", "/nix"];
    absolute == home
        || EXACT.iter().any(|dir| absolute == Path::new(dir))
        || INSIDE.iter().any(|dir| absolute.starts_with(dir))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx() -> Context {
        Context { home: PathBuf::from("/home/dev"), cwd: PathBuf::from("/work/app") }
    }

    #[test]
    fn home_is_expanded_in_its_three_spellings() {
        let c = ctx();
        assert_eq!(c.expand("~/.ssh"), "/home/dev/.ssh");
        assert_eq!(c.expand("~"), "/home/dev");
        assert_eq!(c.expand("$HOME/x"), "/home/dev/x");
        assert_eq!(c.expand("${HOME}/x"), "/home/dev/x");
        assert_eq!(c.expand("~other/x"), "~other/x");
    }

    #[test]
    fn relative_paths_are_made_absolute_and_cleaned() {
        let c = ctx();
        assert_eq!(c.absolute("src/../lib/a.rs"), PathBuf::from("/work/app/lib/a.rs"));
        assert_eq!(c.absolute("../other"), PathBuf::from("/work/other"));
        assert_eq!(c.absolute("/etc/./passwd"), PathBuf::from("/etc/passwd"));
    }

    #[test]
    fn the_workspace_and_the_scope_are_measured_from_the_working_directory() {
        let c = ctx();
        assert!(c.in_workspace(&c.absolute("a/b")));
        assert!(!c.in_workspace(&c.absolute("../x")));
        assert!(c.in_scope(&c.absolute("a/b"), &[".".to_owned()]));
        assert!(!c.in_scope(&c.absolute("/etc/x"), &[".".to_owned()]));
    }

    #[test]
    fn system_directories_are_recognised() {
        let home = Path::new("/home/dev");
        for yes in ["/", "/usr/local", "/etc", "/home/dev", "/home"] {
            assert!(is_system_directory(Path::new(yes), home), "{yes}");
        }
        for no in ["/home/dev/project", "/work/app", "/tmp/x"] {
            assert!(!is_system_directory(Path::new(no), home), "{no}");
        }
    }

    #[test]
    fn temporary_places_are_always_in_scope() {
        assert!(is_temporary(Path::new("/tmp/x")));
        assert!(is_temporary(Path::new("/dev/null")));
        assert!(!is_temporary(Path::new("/etc/x")));
    }
}
