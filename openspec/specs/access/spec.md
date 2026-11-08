# Access

## Purpose

Decide who may use an instance and who may decide at which step, from the operator's file and the repository's own configuration, without a user table.

## Requirements

### Requirement: The operator's access list decides who signs in

The system SHALL let anyone with a GitHub account sign in when the access list names no organisation and no user, and otherwise only listed users, administrators and members of listed organisations.

#### Scenario: An open instance

- **WHEN** the access list is empty
- **THEN** any person who proves their GitHub identity is let in

#### Scenario: A restricted instance

- **WHEN** the access list names users and organisations
- **THEN** a listed user, an administrator or a member of a listed organisation is let in, and nobody else

### Requirement: Roles limit who decides, only when a repository sets them

The system SHALL let any signed-in person decide when a repository configures no roles, and otherwise only people holding a role allowed at the phase the work waits at, or administrators.

#### Scenario: The spec gate

- **WHEN** a repository maps the product-owner role to a person
- **THEN** only that person, or an administrator, may decide at the spec approval

#### Scenario: No roles configured

- **WHEN** a repository configures no roles
- **THEN** any signed-in person may decide
