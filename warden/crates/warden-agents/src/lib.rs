//! One adapter per coding agent.
//!
//! Every agent calls a program before it uses a tool, and tells it what it is about to do in its own JSON. An
//! [`Adapter`] reads that into one [`Call`] the engine can judge, and writes the engine's [`Answer`] in the shape that
//! agent expects. What an agent can intercept, rewrite or ask differs, and each adapter documents its own edges.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]

mod claude;
mod codex;
mod copilot;
mod opencode;

pub use claude::Claude;
pub use codex::Codex;
pub use copilot::Copilot;
pub use opencode::OpenCode;
use serde_json::Value;
use warden_policy::Decision;

/// The moment in the agent's life the call is about.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Event {
    /// A tool is about to run.
    PreToolUse,
    /// A tool has run.
    PostToolUse,
    /// A person sent a prompt.
    UserPromptSubmit,
    /// A session began.
    SessionStart,
    /// The agent stopped.
    Stop,
    /// The agent asks whether a tool may run.
    PermissionRequest,
    /// Anything else the agent reports.
    Other(String),
}

impl Event {
    /// The agent's name for the event.
    #[must_use]
    pub fn name(&self) -> &str {
        match self {
            Self::PreToolUse => "PreToolUse",
            Self::PostToolUse => "PostToolUse",
            Self::UserPromptSubmit => "UserPromptSubmit",
            Self::SessionStart => "SessionStart",
            Self::Stop => "Stop",
            Self::PermissionRequest => "PermissionRequest",
            Self::Other(name) => name,
        }
    }

    /// Read an event name.
    #[must_use]
    pub fn parse(name: &str) -> Self {
        match name {
            "PreToolUse" => Self::PreToolUse,
            "PostToolUse" => Self::PostToolUse,
            "UserPromptSubmit" => Self::UserPromptSubmit,
            "SessionStart" => Self::SessionStart,
            "Stop" => Self::Stop,
            "PermissionRequest" => Self::PermissionRequest,
            other => Self::Other(other.to_owned()),
        }
    }
}

/// What a tool does, in terms the engine understands.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Tool {
    /// A shell command.
    Bash {
        /// The command line.
        command: String,
    },
    /// Reading a file or searching a directory.
    Read {
        /// The path.
        path: String,
    },
    /// Creating or replacing a file.
    Write {
        /// The path.
        path: String,
        /// The new content.
        content: String,
    },
    /// Changing part of a file.
    Edit {
        /// The path.
        path: String,
        /// The text that goes in.
        new_text: String,
    },
    /// A patch that changes several files.
    Patch {
        /// The files it touches.
        paths: Vec<String>,
        /// The patch text.
        content: String,
    },
    /// Fetching a URL.
    Web {
        /// The URL.
        url: String,
    },
    /// A tool of an MCP server.
    Mcp {
        /// The server.
        server: String,
        /// The tool.
        tool: String,
        /// Every string in the arguments.
        strings: Vec<String>,
    },
    /// Starting a subagent.
    Agent,
}

/// What the agent is about to do or has done, as the engine sees it.
#[derive(Debug, Clone, PartialEq)]
pub struct Call {
    /// The agent: `claude`.
    pub agent: String,
    /// The moment.
    pub event: Event,
    /// The session the agent reported.
    pub session: String,
    /// The working directory.
    pub cwd: String,
    /// The tool's name as the agent calls it.
    pub tool_name: String,
    /// What the tool does, when it is one the engine understands.
    pub tool: Option<Tool>,
    /// The arguments of the tool, as the agent sent them.
    pub input: Value,
    /// What the tool printed, for the events after it ran.
    pub output: Option<String>,
    /// The person's prompt.
    pub prompt: Option<String>,
}

/// What to tell the agent.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Answer {
    /// The decision; `None` says nothing and lets the agent's own flow decide.
    pub decision: Option<Decision>,
    /// Why, for the model.
    pub reason: String,
    /// Text for the model to read next to the tool's result or the prompt.
    pub context: Option<String>,
    /// The tool's arguments, replaced.
    pub updated_input: Option<Value>,
    /// Refuse a person's prompt.
    pub block_prompt: bool,
    /// What the tool printed, replaced, for the agents that let a hook change the result the model sees.
    pub updated_output: Option<String>,
}

/// What a hook prints and how it exits.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Rendered {
    /// The standard output: empty for no decision.
    pub stdout: String,
    /// The standard error.
    pub stderr: String,
    /// The exit code.
    pub code: i32,
}

/// An agent's hook format.
pub trait Adapter {
    /// The agent's name.
    fn name(&self) -> &'static str;

    /// Read what the agent sent on standard input for `event`.
    fn parse(&self, event: &str, stdin: &str) -> Result<Call, String>;

    /// Write `answer` for `call` in the format the agent expects.
    fn render(&self, call: &Call, answer: &Answer) -> Rendered;

    /// What to print when the input could not be read and the policy says to fail closed.
    fn refuse(&self, event: &Event, reason: &str) -> Rendered;

    /// Whether the agent lets a hook replace the arguments of a tool: Warden then wraps a command so its output is
    /// redacted, and rewrites it for a safer form.
    fn can_rewrite_input(&self) -> bool {
        true
    }

    /// Whether the agent lets a hook replace what a tool printed before the model sees it: Warden then redacts the
    /// output there when it cannot wrap the command.
    fn can_rewrite_output(&self) -> bool {
        false
    }
}

/// The adapter named `name`.
#[must_use]
pub fn adapter(name: &str) -> Option<Box<dyn Adapter>> {
    match name {
        "claude" => Some(Box::new(Claude)),
        "codex" => Some(Box::new(Codex)),
        "copilot" => Some(Box::new(Copilot)),
        "opencode" => Some(Box::new(OpenCode)),
        _ => None,
    }
}
