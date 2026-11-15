import pytest

from shelf.domain.tool_detection import detect_tools, is_declared, plain

CI = """name: CI
jobs:
  quality:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21.0.4'
      - name: install
        run: npm ci
"""


def test_the_versions_a_workflow_sets_up_are_found_with_the_ones_in_a_version_file() -> None:
    found = detect_tools({".github/workflows/ci.yml": CI, ".python-version": "3.12.4\n"})
    assert found == {"node": "24", "python": "3.12.4", "java": "21"}


def test_a_repository_that_declares_its_tools_for_mise_detects_nothing() -> None:
    for name in ("mise.toml", ".mise.toml", ".tool-versions"):
        assert is_declared({name: "x"})
        assert detect_tools({name: "x", ".github/workflows/ci.yml": CI}) == {}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("24", "24"),
        ("v22.1.0", "22.1.0"),
        ("'24'", "24"),
        ("24.x", "24"),
        ("lts/*", "lts"),
        ("lts", "lts"),
        ("22.1.0.4", None),
    ],
)
def test_only_a_plain_version_is_accepted(value: str, expected: str | None) -> None:
    assert plain(value) == expected


@pytest.mark.parametrize(
    "value",
    ["${{ matrix.node }}", "https://example.org/node.tgz", "../evil", "24; rm -x", "node@latest", "$(curl x)", ""],
)
def test_a_version_that_is_an_expression_an_address_or_a_command_is_ignored(value: str) -> None:
    workflow = f"      - uses: actions/setup-node@v4\n        with:\n          node-version: {value}\n"
    assert detect_tools({".github/workflows/ci.yml": workflow}) == {}


def test_a_workflow_wins_over_a_version_file_because_ci_decides_what_is_green() -> None:
    workflow = "      - uses: actions/setup-node@v4\n        with:\n          node-version: 24\n"
    assert detect_tools({".github/workflows/ci.yml": workflow, ".nvmrc": "v20\n"}) == {"node": "24"}


def test_the_version_files_are_read_when_no_workflow_says() -> None:
    assert detect_tools({".nvmrc": "v22.3.0\n"}) == {"node": "22.3.0"}
    assert detect_tools({".node-version": "20\n"}) == {"node": "20"}
    assert detect_tools({".python-version": "3.13\n"}) == {"python": "3.13"}
    assert detect_tools({"go.mod": "module x\n\ngo 1.22.1\n"}) == {"go": "1.22.1"}
    assert detect_tools({"package.json": '{"engines": {"node": ">=24 <26"}}'}) == {"node": "24"}


def test_a_version_file_named_by_the_workflow_is_followed() -> None:
    workflow = "      - uses: actions/setup-node@v4\n        with:\n          node-version-file: .nvmrc\n"
    assert detect_tools({".github/workflows/ci.yml": workflow, ".nvmrc": "v22\n"}) == {"node": "22"}


def test_a_package_json_that_cannot_be_read_is_ignored() -> None:
    assert detect_tools({"package.json": "{not json"}) == {}
    assert detect_tools({"package.json": '{"engines": {"node": "22 || 24"}}'}) == {}


def test_a_matrix_of_versions_is_not_guessed() -> None:
    workflow = "      - uses: actions/setup-node@v4\n        with:\n          node-version: [20, 22]\n"
    assert detect_tools({".github/workflows/ci.yml": workflow}) == {}


def test_nothing_is_found_in_a_repository_with_no_ci_and_no_version_file() -> None:
    assert detect_tools({}) == {}
    assert detect_tools({"README.md": "# x"}) == {}
