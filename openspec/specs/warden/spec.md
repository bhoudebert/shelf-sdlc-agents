# Warden

## Purpose

Guard the agents Shelf runs, and the agents of anyone who installs it, with a policy engine that sees each tool call before it runs: it gates commands, keeps secrets and personal data off the model and records every decision. This capability is built in stages (decision 0014); the requirements below are the ones that hold so far.

## Requirements

### Requirement: Warden is a component with its own binary, checks and releases

The system SHALL keep Warden as a Cargo workspace under `warden/` that builds one binary, `warden`, checked by its own job in the pull request checks (formatting, lints as errors, tests) that the single required check waits for, and released as its own package with its own tag, apart from the Python product.

#### Scenario: The version

- **WHEN** a person runs `warden version`, `warden --version` or `warden -V`
- **THEN** it prints `warden` and the version of the build, and exits successfully

#### Scenario: Help

- **WHEN** a person runs `warden` with no argument, or `help`, `--help` or `-h`
- **THEN** it prints the list of commands and exits successfully

#### Scenario: An unknown command

- **WHEN** a person runs `warden` with a command it does not have
- **THEN** it names that command on the error output, prints the list of commands and exits with status 2

#### Scenario: A change to the engine is checked

- **WHEN** a pull request changes code under `warden/`
- **THEN** the Rust job runs `cargo fmt --check`, `cargo clippy` with warnings as errors and `cargo test`, and the pull request cannot merge while it fails

#### Scenario: Before a push

- **WHEN** a contributor pushes from a checkout that has `warden/` and a Rust toolchain
- **THEN** the pre-push hook runs the same three commands after the Python gate
