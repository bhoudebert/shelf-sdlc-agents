import re
from pathlib import Path

import pytest

from shelf.domain.model import WorkId, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.work import Outcome, Reason
from tests.adapters.web.test_app import REPO, Fixture

WEB = Path(__file__).parents[3] / "src/shelf/adapters/web"
CSS = WEB / "static/app.css"


def luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6});", block))


def theme_blocks() -> tuple[dict[str, str], dict[str, str]]:
    css = CSS.read_text(encoding="utf-8")
    light = re.search(r"^:root \{(.*?)^\}", css, re.MULTILINE | re.DOTALL)
    dark = re.search(r'^:root\[data-theme="dark"\] \{(.*?)^\}', css, re.MULTILINE | re.DOTALL)
    assert light is not None
    assert dark is not None
    return tokens(light.group(1)), tokens(dark.group(1))


def test_text_meets_aa_in_both_themes_and_the_dark_one_stays_calm() -> None:
    light, dark = theme_blocks()
    for theme in (light, dark):
        assert contrast(theme["ink"], theme["ground"]) >= 7
        assert contrast(theme["ink-2"], theme["ground"]) >= 4.5
        assert contrast(theme["on-accent"], theme["accent"]) >= 4.5
    assert 10 <= contrast(dark["ink"], dark["ground"]) <= 14


def test_every_illustration_is_hidden_from_assistive_technology() -> None:
    art = (WEB / "templates/_art.html").read_text(encoding="utf-8")
    svgs = re.findall(r"<svg\b[^>]*>", art)
    assert svgs
    assert all('aria-hidden="true"' in svg for svg in svgs)


@pytest.mark.parametrize(
    ("view", "pose"),
    [
        ({"phase": Phase.DESIGN}, "work"),
        ({"phase": Phase.SPEC_APPROVAL, "waiting_for": Reason.GATE}, "wave"),
        ({"phase": Phase.IMPLEMENT, "waiting_for": Reason.FAILURE}, "confused"),
        ({"phase": Phase.PULL_REQUEST, "outcome": Outcome.MERGED}, "celebrate"),
        ({"phase": Phase.DESIGN, "outcome": Outcome.ABORTED}, "sleep"),
    ],
)
def test_the_mascot_on_the_work_page_tells_the_state(view: dict[str, object], pose: str) -> None:
    fixture = Fixture()
    fixture.sign_in()
    fixture.runner.views[WorkId("work-1")] = WorkView(
        WorkId("work-1"),
        REPO,
        "alice",
        EntryPoint.NEED,
        **view,  # pyright: ignore[reportArgumentType]
    )
    panel = fixture.client.get("/work/work-1").text
    assert f"mascot-{pose} status-art" in panel
