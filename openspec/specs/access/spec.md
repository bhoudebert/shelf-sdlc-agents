# Access

## Purpose

Decide who may use an instance and who may decide at which step, from the operator's file and the repository's own configuration, without a user table.

## Requirements

### Requirement: The operator's access list decides who signs in

The system SHALL be closed by default: only listed users, administrators and members of listed organisations may sign in, and nobody else, so an empty list lets nobody in.

#### Scenario: A closed instance

- **WHEN** the access list is empty
- **THEN** nobody is let in, and the refusal tells the person the operator has not named anyone yet

#### Scenario: A restricted instance

- **WHEN** the access list names users and organisations
- **THEN** a listed user, an administrator or a member of a listed organisation is let in, and nobody else

### Requirement: GitHub commands obey the same list

The system SHALL act on a `/shelf` command written on a pull request only when its author is a listed user or administrator, or a member or owner of a listed organisation that owns the repository, whether the command arrives by webhook or by polling.

#### Scenario: A stranger comments

- **WHEN** someone not on the access list comments `/shelf approve`
- **THEN** the command is ignored and the webhook log shows it as refused

### Requirement: Roles limit who decides, only when a repository sets them

The system SHALL let any signed-in person decide when a repository configures no roles, and otherwise only people holding a role allowed at the phase the work waits at, or administrators.

#### Scenario: The spec gate

- **WHEN** a repository maps the product-owner role to a person
- **THEN** only that person, or an administrator, may decide at the spec approval

#### Scenario: No roles configured

- **WHEN** a repository configures no roles
- **THEN** any signed-in person may decide
