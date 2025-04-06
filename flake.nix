{
  description = "ye";
  inputs = { nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable"; };

  outputs = { self, nixpkgs, ... }@inputs:
    let
      inherit (self) outputs;
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      packages = forAllSystems (system:
        import ./default.nix { pkgs = nixpkgs.legacyPackages.${system}; });

      formatter =
        forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);
      devShells.x86_64-linux.default = let arch = "x86_64-linux";
      in with nixpkgs.legacyPackages.${arch};
      mkShell {
        buildInputs = with pkgs; [ uv python3 ffmpeg python3Packages.alembic ];
      };

    };
}
