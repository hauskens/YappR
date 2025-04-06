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
        import ./packages { pkgs = nixpkgs.legacyPackages.${system}; });

      formatter =
        forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);
    };
}
