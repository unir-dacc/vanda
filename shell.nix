{ pkgs ? import <nixpkgs> { } }:
with pkgs;

mkShell {
  name = "dbNGEN";

# Add executable packages to the nix-shell environment.
  packages = with pkgs; [
    python311
    pipenv
  ];

# Bash statements that are executed by nix-shell.
  shellHook = ''
    pipenv shell
    pre-commit install
    '';
  DJANGO_SETTINGS_MODULE="dbNGEN.settings_dev";
}
