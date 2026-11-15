from shelf.domain.formatters import prettier_ignore, uses_prettier

PACKAGE = '{"devDependencies": {"prettier": "3.8.1"}, "scripts": {"format:check": "prettier --check ."}}'


def test_a_repository_with_prettier_in_its_manifest_and_no_ignore_file_gets_one_that_ignores_the_folder() -> None:
    assert prettier_ignore({"package.json": PACKAGE}) == "# Shelf's own files for each piece of work\n.shelf/\n"


def test_an_existing_ignore_file_keeps_its_lines_and_gains_one() -> None:
    updated = prettier_ignore({".prettierignore": "dist\ncoverage\n", "package.json": PACKAGE})
    assert updated == "dist\ncoverage\n\n# Shelf's own files for each piece of work\n.shelf/\n"


def test_a_folder_that_is_already_ignored_changes_nothing_however_it_is_written() -> None:
    for line in (".shelf", ".shelf/", "/.shelf", "/.shelf/", ".shelf/**", "**/.shelf/**", "  .shelf/  "):
        assert prettier_ignore({".prettierignore": f"dist\n{line}\n"}) is None, line


def test_a_repository_that_does_not_use_prettier_changes_nothing() -> None:
    assert prettier_ignore({"package.json": '{"devDependencies": {"eslint": "9"}}'}) is None
    assert prettier_ignore({}) is None
    assert prettier_ignore({"README.md": "prettier is nice"}) is None


def test_a_configuration_file_or_an_ignore_file_alone_means_the_repository_uses_prettier() -> None:
    for name in (".prettierrc", ".prettierrc.json", "prettier.config.mjs", ".prettierignore"):
        assert uses_prettier({name: ""}), name


def test_an_empty_ignore_file_gets_the_line_without_a_leading_blank() -> None:
    assert prettier_ignore({".prettierignore": "", "package.json": PACKAGE}) == (
        "# Shelf's own files for each piece of work\n.shelf/\n"
    )


def test_the_sandbox_block_is_added_once_at_the_end_and_taken_out_again_whole() -> None:
    from shelf.domain.formatters import (  # noqa: PLC0415
        SANDBOX_BEGIN,
        SANDBOX_PLACEHOLDERS,
        with_sandbox_placeholders,
        without_sandbox_placeholders,
    )

    original = "dist\n\n# Shelf's own files for each piece of work\n.shelf/\n"
    hidden = with_sandbox_placeholders(original)
    assert hidden.startswith(original.rstrip("\n"))
    assert hidden.count(SANDBOX_BEGIN) == 1
    assert all(name in hidden.splitlines() for name in SANDBOX_PLACEHOLDERS)
    assert with_sandbox_placeholders(hidden) == hidden  # asking again changes nothing
    assert without_sandbox_placeholders(hidden) == original


def test_a_missing_ignore_file_gets_only_the_block_and_loses_it_again() -> None:
    from shelf.domain.formatters import with_sandbox_placeholders, without_sandbox_placeholders  # noqa: PLC0415

    hidden = with_sandbox_placeholders(None)
    assert hidden.splitlines()[0].startswith("# shelf: sandbox placeholders")
    assert without_sandbox_placeholders(hidden).strip() == ""
    assert without_sandbox_placeholders("dist\n") == "dist\n"
