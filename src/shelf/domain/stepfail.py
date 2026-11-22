"""What to tell a person when a step could not reach the model. Pure: no I/O."""

from typing import Final

SIGNS: Final = (
    "EAI_AGAIN",
    "ENOTFOUND",
    "ECONNREFUSED",
    "Can't reach the API server",
    "Temporary failure in name resolution",
)
"""What an agent or the system library says when a name does not resolve or a connection is refused."""

ADVICE: Final = (
    " The step could not reach the model: its names did not resolve or its network is cut. Check the resolvers of the "
    "steps (`SHELF_STEP_DNS` in deploy/.env; `sh deploy/host-runtime.sh --probe` finds them) and the network the "
    "steps run on."
)


def explain_model_failure(reason: str) -> str:
    """``reason`` with what to check added when it says the model was not reached; any other reason as it is."""
    if ADVICE in reason or not any(sign in reason for sign in SIGNS):
        return reason
    return reason.rstrip() + ADVICE


def unresolvable(host: str, why: str) -> str:
    """The error of a step whose model host does not resolve, said before the agent starts and not after minutes."""
    return f"The step cannot resolve {host} ({why}).{ADVICE}"
