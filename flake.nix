{
  description = "Shelf SDLC Agents: development shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      # `nix develop` (or direnv, with `direnv allow`) gives every contributor the same toolchains, CI's included.
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          # NixOS cannot run the dev server that temporalio downloads: tests use this one instead.
          SHELF_TEMPORAL_DEV_SERVER = "${pkgs.temporal-cli}/bin/temporal";
          packages = with pkgs; [
            git
            gh
            jq
            python313
            ruff
            pyright
            uv
            temporal-cli
          ];
        };
      });
    };
}
