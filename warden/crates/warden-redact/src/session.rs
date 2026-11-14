use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::kind::Kind;

/// The on-disk shape of a session.
#[derive(Serialize, Deserialize)]
struct Stored {
    tokens: BTreeMap<String, String>,
}

/// The token map of one agent session: which value each token stands for.
///
/// The same kind and value always get the same token, numbered per prefix from 1.
#[derive(Debug, Clone, Default)]
pub struct Session {
    path: Option<PathBuf>,
    /// token (`<EMAIL_1>`) to value
    tokens: BTreeMap<String, String>,
    /// (prefix, value) to token
    reverse: HashMap<(String, String), String>,
    /// last number handed out, per prefix
    counters: HashMap<String, usize>,
}

impl Session {
    /// A session that lives in memory only; [`Session::save`] does nothing.
    #[must_use]
    pub fn in_memory() -> Self {
        Self::default()
    }

    /// Opens the session kept in the JSON file at `path`, or starts an empty one if there is no such file; the
    /// parent directories are created. A file that is not a session gives an `InvalidData` error.
    pub fn open(path: &Path) -> io::Result<Self> {
        if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
            fs::create_dir_all(parent)?;
        }
        let mut session = Self { path: Some(path.to_path_buf()), ..Self::default() };
        match fs::read_to_string(path) {
            Ok(content) => {
                let stored: Stored = serde_json::from_str(&content)
                    .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("{}: {e}", path.display())))?;
                for (token, value) in stored.tokens {
                    session.load(token, value);
                }
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
        }
        Ok(session)
    }

    fn load(&mut self, token: String, value: String) {
        if let Some((prefix, n)) = split_token(&token) {
            let counter = self.counters.entry(prefix.to_owned()).or_insert(0);
            *counter = (*counter).max(n);
            self.reverse.entry((prefix.to_owned(), value.clone())).or_insert_with(|| token.clone());
        }
        self.tokens.insert(token, value);
    }

    /// Writes the session to its file: to a temporary file in the same directory, then renamed over it, with mode
    /// 0600 on unix. Does nothing for an in-memory session.
    pub fn save(&self) -> io::Result<()> {
        let Some(path) = &self.path else { return Ok(()) };
        let json = serde_json::to_string_pretty(&Stored { tokens: self.tokens.clone() })
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        let mut tmp_name = path.file_name().map(std::ffi::OsString::from).unwrap_or_default();
        tmp_name.push(format!(".tmp-{}", std::process::id()));
        let tmp = path.with_file_name(tmp_name);
        let written = write_private(&tmp, json.as_bytes()).and_then(|()| fs::rename(&tmp, path));
        if written.is_err() {
            let _ = fs::remove_file(&tmp);
        }
        written
    }

    /// The token for `value` of this `kind`: the same one every time, a new one (`<EMAIL_2>`) the first time.
    pub fn token_for(&mut self, kind: &Kind, value: &str) -> String {
        let prefix = kind.prefix();
        if let Some(token) = self.reverse.get(&(prefix.clone(), value.to_owned())) {
            return token.clone();
        }
        let token = self.allocate(&prefix);
        self.tokens.insert(token.clone(), value.to_owned());
        self.reverse.insert((prefix, value.to_owned()), token.clone());
        token
    }

    /// The value a token stands for, if this session knows it.
    #[must_use]
    pub fn value_of(&self, token: &str) -> Option<&str> {
        self.tokens.get(token).map(String::as_str)
    }

    /// How many tokens the session holds.
    #[must_use]
    pub fn len(&self) -> usize {
        self.tokens.len()
    }

    /// Whether the session holds no token.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.tokens.is_empty()
    }

    fn allocate(&mut self, prefix: &str) -> String {
        let n = self.counters.entry(prefix.to_owned()).or_insert(0);
        *n += 1;
        format!("<{prefix}_{n}>")
    }

    /// Starts a block whose end is not known yet (a private key read line by line): the token is handed out now, with
    /// the first line as its value, and the value grows with [`Session::extend_block`].
    pub(crate) fn begin_block(&mut self, kind: &Kind, first_line: &str) -> String {
        let token = self.allocate(&kind.prefix());
        self.tokens.insert(token.clone(), first_line.to_owned());
        token
    }

    /// Appends a line to the value of a block started by [`Session::begin_block`].
    pub(crate) fn extend_block(&mut self, token: &str, line: &str) {
        if let Some(value) = self.tokens.get_mut(token) {
            value.push('\n');
            value.push_str(line);
        }
    }

    /// Declares a block complete, so that the same block seen later in one piece gets this token.
    pub(crate) fn finish_block(&mut self, token: &str) {
        if let (Some((prefix, _)), Some(value)) = (split_token(token), self.tokens.get(token)) {
            self.reverse.entry((prefix.to_owned(), value.clone())).or_insert_with(|| token.to_owned());
        }
    }
}

/// `<EMAIL_12>` gives `("EMAIL", 12)`.
fn split_token(token: &str) -> Option<(&str, usize)> {
    let inner = token.strip_prefix('<')?.strip_suffix('>')?;
    let (prefix, n) = inner.rsplit_once('_')?;
    Some((prefix, n.parse().ok()?))
}

#[cfg(unix)]
fn write_private(path: &Path, bytes: &[u8]) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    let mut file = fs::OpenOptions::new().write(true).create(true).truncate(true).mode(0o600).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()
}

#[cfg(not(unix))]
fn write_private(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let mut file = fs::File::create(path)?;
    file.write_all(bytes)?;
    file.sync_all()
}
