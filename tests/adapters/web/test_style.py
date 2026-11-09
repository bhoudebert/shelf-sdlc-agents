import re
from pathlib import Path

CSS = Path(__file__).parents[3] / "src/shelf/adapters/web/static/app.css"


def test_a_document_uses_the_whole_width_of_its_panel() -> None:
    css = CSS.read_text(encoding="utf-8")
    prose = re.search(r"^\.prose \{([^}]*)\}", css, re.MULTILINE)
    assert prose is not None
    assert "max-width" not in prose.group(1)
    assert re.search(r"\.prose p[^{]*\{\s*max-width:\s*none", css)
