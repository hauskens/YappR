{
  description = "Build a cargo workspace";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

    crane.url = "github:ipetkov/crane";

    flake-utils.url = "github:numtide/flake-utils";

    advisory-db = {
      url = "github:rustsec/advisory-db";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      crane,
      flake-utils,
      advisory-db,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        inherit (pkgs) lib;

        craneLib = crane.mkLib pkgs;
        src = craneLib.cleanCargoSource ./.;

        # Common arguments can be set here to avoid repeating them later
        commonArgs = {
          inherit src;
          strictDeps = true;

          nativeBuildInputs = with pkgs; [
            pkg-config
            pnpm
            nodejs
          ];

          buildInputs = with pkgs; [
            # Add additional build inputs here
            openssl
          ]
          ++ lib.optionals pkgs.stdenv.isDarwin [
            # Additional darwin specific inputs can be set here
            pkgs.libiconv
          ];

          # Additional environment variables can be set directly
          # MY_CUSTOM_VAR = "some value";
        };

        # Build *just* the cargo dependencies (of the entire workspace),
        # so we can reuse all of that work (e.g. via cachix) when running in CI
        # It is *highly* recommended to use something like cargo-hakari to avoid
        # cache misses when building individual top-level-crates
        cargoArtifacts = craneLib.buildDepsOnly commonArgs;

        individualCrateArgs = commonArgs // {
          inherit cargoArtifacts;
          inherit (craneLib.crateNameFromCargoToml { inherit src; }) version;
          # NB: we disable tests since we'll run them all via cargo-nextest
          doCheck = false;
        };

        fileSetForCrate =
          crate:
          lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [
              ./Cargo.toml
              ./Cargo.lock
              (craneLib.fileset.commonCargoSources ./shared)
              (craneLib.fileset.commonCargoSources crate)
            ];
          };

        # Build the top-level crates of the workspace as individual derivations.
        # This allows consumers to only depend on (and build) only what they need.
        # Though it is possible to build the entire workspace as a single derivation,
        # so this is left up to you on how to organize things
        #
        # Note that the cargo workspace must define `workspace.members` using wildcards,
        # otherwise, omitting a crate (like we do below) will result in errors since
        # cargo won't be able to find the sources for all members.
        cli = craneLib.buildPackage (
          individualCrateArgs
          // {
            pname = "yappr-cli";
            cargoExtraArgs = "-p yappr-cli";
            src = fileSetForCrate ./cli;
          }
        );
        # my-server = craneLib.buildPackage (
        #   individualCrateArgs
        #   // {
        #     pname = "my-server";
        #     cargoExtraArgs = "-p my-server";
        #     src = fileSetForCrate ./src/;
        #   }
        # );
      in
      {
        checks = {
          # Build the crates as part of `nix flake check` for convenience
          inherit cli;

          # Run clippy (and deny all warnings) on the workspace source,
          # again, reusing the dependency artifacts from above.
          #
          # Note that this is done as a separate derivation so that
          # we can block the CI if there are issues here, but not
          # prevent downstream consumers from building our crate by itself.
          my-workspace-clippy = craneLib.cargoClippy (
            commonArgs
            // {
              inherit cargoArtifacts;
              cargoClippyExtraArgs = "--all-targets -- --deny warnings";
            }
          );

          # my-workspace-doc = craneLib.cargoDoc (
          #   commonArgs
          #   // {
          #     inherit cargoArtifacts;
          #     # This can be commented out or tweaked as necessary, e.g. set to
          #     # `--deny rustdoc::broken-intra-doc-links` to only enforce that lint
          #     env.RUSTDOCFLAGS = "--deny warnings";
          #   }
          # );

          # Check formatting
          my-workspace-fmt = craneLib.cargoFmt {
            inherit src;
          };

          my-workspace-toml-fmt = craneLib.taploFmt {
            src = pkgs.lib.sources.sourceFilesBySuffices src [ ".toml" ];
            # taplo arguments can be further customized below as needed
            # taploExtraArgs = "--config ./taplo.toml";
          };

          # # Audit dependencies
          # my-workspace-audit = craneLib.cargoAudit {
          #   inherit src advisory-db;
          # };

          # Audit licenses
          # my-workspace-deny = craneLib.cargoDeny {
          #   inherit src;
          # };

          # Run tests with cargo-nextest
          # Consider setting `doCheck = false` on other crate derivations
          # if you do not want the tests to run twice
          # my-workspace-nextest = craneLib.cargoNextest (
          #   commonArgs
          #   // {
          #     inherit cargoArtifacts;
          #     partitions = 1;
          #     partitionType = "count";
          #     cargoNextestPartitionsExtraArgs = "--no-tests=pass";
          #   }
          # );

          # # Ensure that cargo-hakari is up to date
          # my-workspace-hakari = craneLib.mkCargoDerivation {
          #   inherit src;
          #   pname = "my-workspace-hakari";
          #   cargoArtifacts = null;
          #   doInstallCargoArtifacts = false;

          #   buildPhaseCargoCommand = ''
          #     cargo hakari generate --diff  # workspace-hack Cargo.toml is up-to-date
          #     cargo hakari manage-deps --dry-run  # all workspace crates depend on workspace-hack
          #     cargo hakari verify
          #   '';

          #   nativeBuildInputs = [
          #     pkgs.cargo-hakari
          #   ];
          # };
        };

        packages = {
          inherit cli;
        };

        apps = {
          cli = flake-utils.lib.mkApp {
            drv = cli;
          };
        };

        devShells.default = craneLib.devShell {
          checks = self.checks.${system};
          # LD_LIBRARY_PATH = "${lib.makeLibraryPath}";
          # LIBCLANG_PATH = pkgs.lib.makeLibraryPath [ pkgs.llvmPackages_latest.libclang.lib ];
          # BINDGEN_EXTRA_CLANG_ARGS = with pkgs; ''
          #       -isystem ${llvmPackages.libclang.lib}/lib/clang/${lib.getVersion clang}/include
          #       -isystem ${llvmPackages.libclang.out}/lib/clang/${lib.getVersion clang}/include
          #       -isystem ${glibc.dev}/include
          #     '';
          
          # NIX_CFLAGS_COMPILE = "-isystem ${pkgs.glibc.dev}/include";
          packages = with pkgs; [
            taplo
            cargo-hakari
          ];
        };
      }
    );
}
