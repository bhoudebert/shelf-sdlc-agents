import re
from pathlib import Path

from shelf.domain.pipeline import EntryPoint

CSS = Path(__file__).parents[3] / "src/shelf/adapters/web/static/app.css"


def test_a_document_uses_the_whole_width_of_its_panel() -> None:
    css = CSS.read_text(encoding="utf-8")
    prose = re.search(r"^\.prose \{([^}]*)\}", css, re.MULTILINE)
    assert prose is not None
    assert "max-width" not in prose.group(1)
    assert re.search(r"\.prose p[^{]*\{\s*max-width:\s*none", css)


def test_the_interface_is_dark_whatever_the_system_prefers_and_light_only_when_chosen() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in css
    assert ':root[data-theme="dark"]' in css
    script = (CSS.parent / "app.js").read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in script
    assert 'return "dark"' in script
    assert 'data-theme="dark"' in (CSS.parent.parent / "templates" / "base.html").read_text(encoding="utf-8")


def test_the_start_preview_knows_every_entry_point_so_none_shows_everything_as_skipped() -> None:
    css = CSS.read_text(encoding="utf-8")
    for entry in EntryPoint:
        assert f'input[value="{entry.value}"]:checked) .preview li' in css, entry


def test_a_stopped_phase_on_the_board_differs_by_shape_not_only_by_colour() -> None:
    css = CSS.read_text(encoding="utf-8")
    stopped = re.search(r"^\.mini i\.stopped::after \{([^}]*)\}", css, re.MULTILINE)
    assert stopped is not None
    assert "rotate(45deg)" in stopped.group(1)


def test_the_star_field_sits_behind_the_content_and_lets_clicks_through() -> None:
    css = CSS.read_text(encoding="utf-8")
    stars = re.search(r"^body::before \{([^}]*)\}", css, re.MULTILINE)
    assert stars is not None
    assert "z-index: -1" in stars.group(1)
    assert "pointer-events: none" in stars.group(1)


def test_the_note_box_is_tall_and_keeps_a_draft() -> None:
    panel = (CSS.parent.parent / "templates" / "_work_panel.html").read_text(encoding="utf-8")
    assert 'class="roomy"' in panel
    assert 'rows="9"' in panel
    script = (CSS.parent / "app.js").read_text(encoding="utf-8")
    assert "shelf-draft-" in script
    assert "ctrlKey" in script
