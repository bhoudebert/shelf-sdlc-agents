"""Who may use an instance, and who administers it. The operator's file is the only source: no user table."""

from dataclasses import dataclass

from shelf.domain.model import Identity


@dataclass(frozen=True, slots=True)
class AccessRules:
    """The ``[access]`` section of the operator's configuration."""

    organisations: frozenset[str] = frozenset()
    users: frozenset[str] = frozenset()
    admins: frozenset[str] = frozenset()

    @property
    def is_open(self) -> bool:
        """True when anyone with a GitHub account may sign in."""
        return not self.organisations and not self.users


def may_sign_in(rules: AccessRules, identity: Identity) -> bool:
    """Whether ``identity`` may sign in: open instance, listed user or admin, or listed organisation."""
    return (
        rules.is_open
        or identity.login in rules.users
        or identity.login in rules.admins
        or not rules.organisations.isdisjoint(identity.organisations)
    )


def is_admin(rules: AccessRules, login: str) -> bool:
    """Whether ``login`` administers the instance."""
    return login in rules.admins
