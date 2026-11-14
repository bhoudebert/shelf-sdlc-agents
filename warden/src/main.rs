//! Warden: a policy engine for coding agents. See `docs/adr/0014-guard-agents-with-warden-a-policy-engine-in-rust.md`.

use std::process::ExitCode;

/// The version of this build, as `warden version` prints it.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// What the command line asked for.
#[derive(Debug, PartialEq, Eq)]
enum Command {
    Version,
    Help,
    Unknown(String),
}

fn parse(args: &[String]) -> Command {
    match args.first().map(String::as_str) {
        Some("version" | "--version" | "-V") => Command::Version,
        None | Some("help" | "--help" | "-h") => Command::Help,
        Some(other) => Command::Unknown(other.to_owned()),
    }
}

const HELP: &str = "warden: a policy engine for coding agents\n\nUsage: warden <command>\n\nCommands:\n  version   print the version\n  help      print this help\n";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match parse(&args) {
        Command::Version => {
            println!("warden {VERSION}");
            ExitCode::SUCCESS
        }
        Command::Help => {
            print!("{HELP}");
            ExitCode::SUCCESS
        }
        Command::Unknown(name) => {
            eprintln!("warden: unknown command {name:?}\n\n{HELP}");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| (*s).to_owned()).collect()
    }

    #[test]
    fn version_is_asked_in_three_ways() {
        for form in ["version", "--version", "-V"] {
            assert_eq!(parse(&args(&[form])), Command::Version);
        }
    }

    #[test]
    fn no_arguments_print_the_help() {
        assert_eq!(parse(&[]), Command::Help);
        assert_eq!(parse(&args(&["--help"])), Command::Help);
    }

    #[test]
    fn an_unknown_command_is_named() {
        assert_eq!(
            parse(&args(&["frobnicate"])),
            Command::Unknown("frobnicate".into())
        );
    }

    #[test]
    fn the_version_is_the_package_version() {
        assert_eq!(VERSION, env!("CARGO_PKG_VERSION"));
    }
}
