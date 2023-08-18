{ pkgs ? import <nixpkgs> { } }:
with pkgs;

mkShell {
	name = "dbNGEN";

# Add executable packages to the nix-shell environment.
	packages = with pkgs; [
		python311
		pipenv
		nodePackages.prettier
		nodePackages.stylelint
	];

# Bash statements that are executed by nix-shell.
	shellHook = ''
		fish -C "source $HOME/.local/share/virtualenvs/dbNGEN-vrAsR5f0/bin/activate.fish"
		'';
}
