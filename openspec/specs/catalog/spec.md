# Catalog

## Purpose

Let the operator give agents the corporate skills and plugins they want, each pinned to a commit and reviewable, without anything from those sources running while they are installed.

## Requirements

### Requirement: Every source is pinned

The system SHALL read the operator's catalog from `catalog.toml`, where each `[[source]]` names a slug, a git repository, a full 40-character commit, a kind (`skills` or `plugin`), and optionally a path inside the repository and the skill folders to take. It SHALL refuse the whole catalog, naming the source, when a source has no full commit, a name that is not a slug, an unknown kind, a path that leaves the repository, or a name that another source already has.

#### Scenario: A branch name instead of a commit

- **WHEN** a source's `ref` is `main`
- **THEN** the catalog is refused and the error names that source and says a full commit is required

#### Scenario: A path that leaves the repository

- **WHEN** a source's `path` is `../elsewhere`
- **THEN** the catalog is refused and the error names that source

#### Scenario: A valid catalog

- **WHEN** every source has a slug, a repository, a full commit and a known kind
- **THEN** the catalog is accepted with its sources in the order written

### Requirement: Syncing fetches files and never runs them

The system SHALL, when it syncs the catalog, fetch each source at its pinned commit, check that it has the structure its kind needs, and copy its files, and SHALL NOT run any script, hook, installer or build step that a source contains. A source that does not have the expected structure SHALL fail the sync, naming the source, and a failed sync SHALL leave the previous catalog in place.

#### Scenario: A plugin source without a plugin manifest

- **WHEN** a `plugin` source has no `.claude-plugin/plugin.json`
- **THEN** the sync fails naming the source and the catalog on disk is unchanged

#### Scenario: A skills source without skills

- **WHEN** a `skills` source contains no folder with a `SKILL.md`
- **THEN** the sync fails naming the source

#### Scenario: A source that carries an installer

- **WHEN** a source contains a script that would write a file if it ran
- **THEN** the sync completes and that file does not exist

#### Scenario: A commit the repository does not have

- **WHEN** a source names a commit that cannot be fetched
- **THEN** the sync fails naming the source and the commit

### Requirement: A skills source becomes a skill-only plugin

The system SHALL turn a `skills` source into a generated plugin named after the source that holds only the skill folders taken (every folder with a `SKILL.md` under the source's path, or only those named in `skills`), and none of the source's hooks, commands, agents or servers.

#### Scenario: A source with hooks

- **WHEN** a `skills` source is a plugin that also has a session-start hook
- **THEN** the generated plugin has its skill folders and no hook

#### Scenario: A selection of skills

- **WHEN** a source lists two of its skills in `skills`
- **THEN** the generated plugin holds those two only

### Requirement: A plugin source is registered for every agent

The system SHALL register each `plugin` source in a generated local marketplace and write a managed policy that force-enables those plugins, allows only managed hooks, and points at that marketplace, so that their hooks run for every agent and no repository's own hooks do.

#### Scenario: A plugin source

- **WHEN** the catalog has one `plugin` source
- **THEN** the marketplace lists it, and the managed policy enables it and allows managed hooks only

#### Scenario: Only skill sources

- **WHEN** the catalog has no `plugin` source
- **THEN** the managed policy enables no plugin and still allows managed hooks only

### Requirement: The lock says what was fetched

The system SHALL write a lock file listing, for each source, its commit, its kind, the skills or plugin it produced, and every command that its hooks would run, so that a change of commit shows up as a reviewable difference.

#### Scenario: A plugin with a hook

- **WHEN** a `plugin` source declares a session-start command
- **THEN** the lock lists that command under the source
