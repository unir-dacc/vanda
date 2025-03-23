{
  description = "NixOS environment";

  inputs = { nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable"; };

  outputs = { self, nixpkgs, }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };

    in {
      devShell.${system} = with pkgs;

        mkShell rec {
          packages = [ python312 pipenv nodejs pyright ruff ];
          shellHook = ''
            pipenv shell --fancy
            pre-commit install
          '';
        };
    };
}
