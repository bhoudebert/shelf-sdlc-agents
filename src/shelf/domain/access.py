"""Who may use an instance, and who administers it. The operator's file is the only source: no user table.

Access is closed by default: an instance that lists nobody lets nobody in, because whoever signs in spends the
operator's model account and acts on their repositories.
"""

from dataclasses import dataclass

from shelf.domain.model import Identity

MEMBER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER"})
"""GitHub's words for someone who belongs to the organisation that owns the repository."""


@dataclass(frozen=True, slots=True)
class AccessRules:
    """The ``[access]`` section of the operator's configuration."""

    organisations: frozenset[str] = frozenset()
    users: frozenset[str] = frozenset()
    admins: frozenset[str] = frozenset()

    @property
    def is_configured(self) -> bool:
        """Whether the operator listed anyone at all. Without that, nobody may use the instance."""
        return bool(self.organisations or self.users or self.admins)


def may_sign_in(rules: AccessRules, identity: Identity) -> bool:
    """Whether ``identity`` may sign in: a listed user or admin, or a member of a listed organisation. Nobody else."""
    return (
        identity.login in rules.users
        or identity.login in rules.admins
        or not rules.organisations.isdisjoint(identity.organisations)
    )


def may_use_repository(rules: AccessRules, owner: str, login: str = "") -> bool:
    """Whether work may happen on a repository of ``owner``.

    That is a listed organisation, a listed person's own account, or the signed-in person's own account (``login``).

    Anyone can install the App on an account or organisation they own, so that the App can reach a repository says
    nothing about whether this instance may spend its model account there. Names compare without regard to case,
    as GitHub's do.
    """
    wanted = owner.casefold()
    listed = {name.casefold() for name in (*rules.organisations, *rules.users, *rules.admins)}
    return wanted in listed or (login != "" and wanted == login.casefold())


def may_act_from_github(rules: AccessRules, login: str, association: str, owner: str) -> bool:
    """Whether a command typed on a pull request counts.

    The repository must be one this instance serves, and the person listed or a member of a listed organisation.

    GitHub tells us a commenter's association with the repository's owner, not their organisations, so membership of a
    listed organisation is read as: the repository belongs to it and the commenter is a member (or the owner) of it.
    """
    if not may_use_repository(rules, owner, login):
        return False
    return (
        login in rules.users
        or login in rules.admins
        or (owner in rules.organisations and association in MEMBER_ASSOCIATIONS)
    )


def is_admin(rules: AccessRules, login: str) -> bool:
    """Whether ``login`` administers the instance."""
    return login in rules.admins
