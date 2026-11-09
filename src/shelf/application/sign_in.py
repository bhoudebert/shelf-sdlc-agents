"""Signing in: GitHub proves who the person is, the operator's rules say whether they are let in."""

from dataclasses import dataclass, replace

from shelf.application.errors import NotAllowed
from shelf.domain.access import AccessRules, may_sign_in
from shelf.domain.model import Identity
from shelf.domain.result import Err, Ok, Result
from shelf.ports.forge import Forge


@dataclass(frozen=True, slots=True)
class SignedIn:
    """A person let in, with the token to act as them on GitHub."""

    identity: Identity
    user_token: str


async def sign_in(forge: Forge, rules: AccessRules, code: str) -> Result[SignedIn, NotAllowed]:
    """Complete the OAuth round trip for ``code`` and check the person against ``rules``."""
    user_token = await forge.exchange_code(code)
    identity = await forge.identity(user_token)
    if not rules.is_configured:
        reason = "this instance has no access list yet, so nobody can sign in. The operator must name users, admins or "
        return Err(NotAllowed(reason + "organisations in shelf.toml"))
    if rules.organisations and not may_sign_in(rules, identity):
        member = await forge.memberships(identity.login, rules.organisations)
        identity = replace(identity, organisations=identity.organisations | member)
    if not may_sign_in(rules, identity):
        hint = " (for an organisation, the membership must be public or the App must be allowed to read members)"
        return Err(
            NotAllowed(
                f"{identity.login} is not on this instance's access list" + (hint if rules.organisations else "")
            )
        )
    return Ok(SignedIn(identity, user_token))
