import re
from pathlib import Path

TEMPLATES = Path(__file__).parents[3] / "src/shelf/adapters/web/templates"
EXTERNAL = re.compile(
    r'<a\b[^>]*href="(?:https?://|\{\{ (?:item\.pull_request_url|install_url|temporal_link|[a-z_.]*url))[^"]*"[^>]*>'
)
SAME_TAB = {"login_url"}  # the sign-in round trip returns to this tab, so it stays here


def test_every_link_that_leaves_the_app_opens_in_a_new_tab_without_handing_over_the_page() -> None:
    offenders: list[str] = []
    for template in TEMPLATES.glob("*.html"):
        for link in EXTERNAL.findall(template.read_text()):
            if any(name in link for name in SAME_TAB):
                continue
            if 'target="_blank"' not in link or "noopener" not in link:
                offenders.append(f"{template.name}: {link}")
    assert not offenders, offenders
