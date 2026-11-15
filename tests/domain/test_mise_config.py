from shelf.domain.mise_config import declared_tools, ignored_sections


def test_the_plain_tools_of_a_declaration_are_kept_for_any_language() -> None:
    text = '[tools]\njava = "temurin-27.0.1+0"\nrust = "1.90"\ngo = ["1.24", "1.23"]\nghc = { version = "9.12" }\nzig = "latest"\n'
    found = declared_tools({"mise.toml": text})
    assert found.tools == {"java": "temurin-27.0.1+0", "rust": "1.90", "go": "1.24", "ghc": "9.12", "zig": "latest"}
    assert found.ignored == ()


def test_what_names_a_backend_an_address_or_an_option_is_ignored_with_a_reason() -> None:
    text = (
        '[tools]\n"npm:left-pad" = "1"\n"asdf:evil" = "1"\n"https://x.example/t" = "1"\n'
        'node = { version = "22", postinstall = "curl x | sh" }\npython = "3.13; rm -rf /"\nruby = "3.4"\n'
    )
    found = declared_tools({"mise.toml": text})
    assert found.tools == {"ruby": "3.4"}
    assert len(found.ignored) == 5
    assert any("left-pad" in reason for reason in found.ignored)
    assert any("node" in reason and "option" in reason for reason in found.ignored)


def test_the_sections_that_would_run_code_are_named() -> None:
    text = '[tools]\nnode = "22"\n[hooks]\nenter = "x"\n[plugins]\nfoo = "https://x"\n[env]\n_.source = "x"\n'
    assert ignored_sections({"mise.toml": text}) == ("hooks", "plugins", "env")
    assert ignored_sections({"mise.toml": '[tools]\nnode = "22"\n'}) == ()


def test_a_tool_versions_file_and_a_broken_file_are_read_safely() -> None:
    found = declared_tools({".tool-versions": "nodejs 22.1.0 # lts\njava temurin-27\nbad;name 1\nlonely\n"})
    assert found.tools == {"nodejs": "22.1.0", "java": "temurin-27"}
    assert len(found.ignored) == 1
    broken = declared_tools({"mise.toml": "[tools\nnode ="})
    assert broken.tools == {}
    assert broken.ignored == ("the declaration is not valid TOML",)
    assert declared_tools({}).tools == {}


def test_more_tools_than_the_limit_are_not_installed() -> None:
    text = "[tools]\n" + "".join(f't{n} = "1"\n' for n in range(30))
    found = declared_tools({"mise.toml": text})
    assert len(found.tools) == 20
    assert len(found.ignored) == 10
