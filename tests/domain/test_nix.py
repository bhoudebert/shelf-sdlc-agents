import json

from shelf.domain.nix import (
    NIX_BIN,
    ci_uses_nix,
    dev_environment,
    has_flake,
    nix_failed,
    nix_ready,
    print_dev_env_command,
)


def shell(**exported: str) -> str:
    return json.dumps({"variables": {name: {"type": "exported", "value": value} for name, value in exported.items()}})


def test_the_path_and_the_plain_variables_of_the_development_shell_are_passed() -> None:
    path, variables = dev_environment(
        shell(
            PATH="/nix/store/a/bin:/nix/store/b/bin", JAVA_HOME="/nix/store/j", NODE_OPTIONS="--max-old-space-size=4096"
        )
    )
    assert path == "/nix/store/a/bin:/nix/store/b/bin"
    assert variables == {"JAVA_HOME": "/nix/store/j", "NODE_OPTIONS": "--max-old-space-size=4096"}


def test_a_home_a_shell_a_certificate_a_credential_of_ours_and_a_loader_variable_are_never_passed() -> None:
    _, variables = dev_environment(
        shell(
            PATH="/nix/store/a/bin",
            HOME="/homeless-shelter",
            SHELL="/bin/bash",
            TMPDIR="/scratch",
            SSL_CERT_FILE="/x.crt",
            NIX_CFLAGS_COMPILE="-x",
            LD_PRELOAD="/x.so",
            LD_LIBRARY_PATH="/x",
            BASH_ENV="/x.sh",
            GH_TOKEN="ghs_x",
            GITHUB_TOKEN="x",
            ANTHROPIC_API_KEY="sk-x",
            CLAUDE_CODE_OAUTH_TOKEN="x",
            WARDEN_PROFILE="observe",
            SHELF_WEB="off",
            KEEP="1",
        )
    )
    assert variables == {"KEEP": "1"}


def test_a_value_that_is_not_plain_text_is_dropped() -> None:
    document = {
        "variables": {
            "PATH": {"type": "exported", "value": "/nix/store/a/bin"},
            "MULTI": {"type": "exported", "value": "a\nb"},
            "BIG": {"type": "exported", "value": "x" * 5000},
            "LIST": {"type": "exported", "value": ["a"]},
            "plain": {"type": "var", "value": "not exported"},
            "bad name": {"type": "exported", "value": "x"},
        }
    }
    path, variables = dev_environment(json.dumps(document))
    assert path == "/nix/store/a/bin"
    assert variables == {}


def test_a_path_with_a_relative_folder_is_refused_whole() -> None:
    assert dev_environment(shell(PATH="/nix/store/a/bin:bin:/usr/bin"))[0] == ""


def test_what_nix_did_not_print_as_json_gives_nothing() -> None:
    assert dev_environment("copying path ...") == ("", {})
    assert dev_environment("[]") == ("", {})
    assert dev_environment('{"variables": 3}') == ("", {})


def test_the_command_runs_in_a_scrubbed_environment_and_writes_nothing_into_the_repository() -> None:
    command = print_dev_env_command("/cache/home/acme__shop")
    assert "env -i" in command
    assert f"PATH={NIX_BIN}" in command
    assert "NIX_REMOTE=daemon" in command
    assert "print-dev-env --json --no-write-lock-file" in command
    assert "timeout 600" in command
    assert "2>/cache/home/acme__shop/.nix-last-error" in command, "nix's own messages do not mix with the JSON"
    for secret_holder in ("GH_TOKEN", "ANTHROPIC", "CLAUDE", "$"):
        assert secret_holder not in command.replace('"$out"', "").replace("$({", "").replace("$(", "")


def test_a_workflow_that_installs_nix_or_runs_nix_develop_means_ci_uses_nix() -> None:
    for text in (
        "      - uses: cachix/install-nix-action@v27",
        "      - uses: DeterminateSystems/nix-installer-action@main",
        "        run: nix develop --command npm test",
        "        run: nix flake check",
    ):
        assert ci_uses_nix({".github/workflows/ci.yml": text}), text
    assert not ci_uses_nix({".github/workflows/ci.yml": "        run: npm ci && npm test"})
    assert not ci_uses_nix({"README.md": "nix develop"}), "only a workflow counts"


def test_a_flake_is_recognised_by_its_file() -> None:
    assert has_flake({"flake.nix": "{}"})
    assert not has_flake({"package.json": "{}"})


def test_the_agent_is_told_what_was_made_available_or_why_not() -> None:
    assert "Nix development shell available" in nix_ready(3)
    assert "with 3 of its variables" in nix_ready(3)
    assert "with" not in nix_ready(0).split("path")[1].split(".")[0]
    assert nix_failed("evaluation failed").endswith("could not: evaluation failed.")
