"""What the operator gives the app: the credentials of the GitHub App."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GitHubAppSettings:
    """The registered GitHub App's credentials and the endpoints to reach it (overridable for GitHub Enterprise)."""

    app_id: str
    private_key: str
    """The App's private key, in PEM."""
    client_id: str
    client_secret: str
    api_url: str = "https://api.github.com"
    web_url: str = "https://github.com"
