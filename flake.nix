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
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      crane,
      flake-utils,
      advisory-db,
      rust-overlay,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs {
          inherit system overlays;
        };

        inherit (pkgs) lib;
        rustToolchain = pkgs.rust-bin.stable.latest.default.override {
            extensions = [
              "rust-src"
              "rust-analyzer"
              "clippy"
              "rustc"
            ];
          };
          buildInputs = with pkgs; [
            openssl
        ] ++ lib.optional stdenv.isLinux [
            strace
          ]
          ++ lib.optionals pkgs.stdenv.isDarwin [
            pkgs.libiconv
          ];
        craneLib = crane.mkLib pkgs;
        # unfilteredRoot = ./.; # The original, unfiltered source
        src = craneLib.cleanCargoSource ./.;

        # Common arguments can be set here to avoid repeating them later
        commonArgs = {
          inherit src buildInputs;
          strictDeps = true;

          nativeBuildInputs = with pkgs; [
            binaryen
            cargo-leptos
            dart-sass
            lld
            makeWrapper
            pkg-config
            wasm-bindgen-cli
            wasm-pack
          ];
          # ENV = 123;
        };

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
              (craneLib.fileset.commonCargoSources ./crates/shared)
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

        npmDeps = pkgs.buildNpmPackage {
          pname = "yappr-npm-deps";
          version = "1.0.0";
          src = ./crates/web;

          npmDepsHash = "sha256-mJMEfwlfE7V8LmnyMb61hs0oKZbF7I0m6RtqRQdff3U=";

          dontNpmBuild = true;
          npmFlags = [ "--legacy-peer-deps" ];

          # Just install node_modules, don't build anything
          installPhase = ''
            mkdir -p $out
            cp -r node_modules $out/
          '';
        };

        cli = craneLib.buildPackage (
          individualCrateArgs
          // {
            pname = "yappr-cli";
            cargoExtraArgs = "--bin yappr-cli";
            src = fileSetForCrate ./crates/cli;
          }
        );
        web = craneLib.buildPackage (
          individualCrateArgs
          // {
            pname = "yappr-web";
            cargoExtraArgs = "-p yappr-web";
            doNotPostBuildInstallCargoBinaries = true;

            # Copy frontend assets from npm package before building
            preBuild = ''
              mkdir -p crates/web/public/vendor/bootstrap
              mkdir -p crates/web/public/vendor/feather-icons
              mkdir -p crates/web/public/images

              # Copy Bootstrap CSS and JS
              cp ${npmDeps}/node_modules/bootstrap/dist/css/bootstrap.min.css crates/web/public/vendor/bootstrap/
              cp ${npmDeps}/node_modules/bootstrap/dist/css/bootstrap.min.css.map crates/web/public/vendor/bootstrap/ 2>/dev/null || true
              cp ${npmDeps}/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js crates/web/public/vendor/bootstrap/
              cp ${npmDeps}/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js.map crates/web/public/vendor/bootstrap/ 2>/dev/null || true

              # Copy Feather Icons
              cp ${npmDeps}/node_modules/feather-icons/dist/feather.min.js crates/web/public/vendor/feather-icons/ 2>/dev/null || true
            '';

          #   buildPhaseCargoCommand = ''
          #   mkdir -p $out/pkg

          #   HOME=$(mktemp -d fake-homeXXXX) wasm-pack build -t nodejs --out-dir $out/pkg
          # '';
          buildPhaseCargoCommand = "cargo leptos build --release -vvv";
          installPhaseCommand = ''
              mkdir -p $out/bin
              cp target/release/yappr-web $out/bin/
              cp -r target/site $out/bin/
              wrapProgram $out/bin/yappr-web \
                --set LEPTOS_SITE_ROOT $out/bin/site
            '';
            src = lib.fileset.toSource {
            root = ./.;
            fileset = lib.fileset.unions [
              ./Cargo.toml
              ./Cargo.lock
              (craneLib.fileset.commonCargoSources ./crates/shared)
              (craneLib.fileset.commonCargoSources ./crates/web)
              (lib.fileset.fileFilter (
              file:
              lib.any file.hasExt [
                "html"
                "scss"
                "js"
                "ts"
                "css"
                "json"
                "yaml"
              ]
            ) ./crates/web)
            ];
          };
          }
        );

        # Container image for web application
        webContainer = pkgs.dockerTools.buildLayeredImage {
          name = "yappr-web";
          tag = "latest";

          contents = [
            web
            pkgs.cacert
          ];

          config = {
            Cmd = [ "${web}/bin/yappr-web" ];
            Env = [
              "LEPTOS_SITE_ROOT=${web}/bin/site"
            ];
            ExposedPorts = {
              "3000/tcp" = {};
            };
            WorkingDir = "/";
          };
        };
      in
      {
        checks = {
          # Build the crates as part of `nix flake check` for convenience
          inherit cli web;

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
          # my-workspace-fmt = craneLib.cargoFmt {
          #   inherit src;
          # };

          # my-workspace-toml-fmt = craneLib.taploFmt {
          #   src = pkgs.lib.sources.sourceFilesBySuffices src [ ".toml" ];
          #   # taplo arguments can be further customized below as needed
          #   # taploExtraArgs = "--config ./taplo.toml";
          # };

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
        };

        packages = {
          inherit cli web webContainer;
          default = web;
        };

        apps = {
          cli = flake-utils.lib.mkApp {
            drv = cli;
          };
          web = flake-utils.lib.mkApp {
            drv = web;
          };
        };

        devShells.default = craneLib.devShell {
          checks = self.checks.${system};
          # env = {
          #   LD_LIBRARY_PATH = "${lib.makeLibraryPath}";
          # };
          LIBCLANG_PATH = pkgs.lib.makeLibraryPath [ pkgs.llvmPackages_latest.libclang.lib ];
          # BINDGEN_EXTRA_CLANG_ARGS = with pkgs; ''
          #       -isystem ${llvmPackages.libclang.lib}/lib/clang/${lib.getVersion clang}/include
          #       -isystem ${llvmPackages.libclang.out}/lib/clang/${lib.getVersion clang}/include
          #       -isystem ${glibc.dev}/include
          #     '';
        #  LIBCLANG_PATH = pkgs.lib.makeLibraryPath [ buildInputs ]; 
        #  LD_LIBRARY_PATH = "${pkgs.lib.makeLibraryPath buildInputs}";
          # NIX_CFLAGS_COMPILE = "-isystem ${pkgs.glibc.dev}/include";
          nativeBuildInputs = [
            rustToolchain
          ];
          packages = with pkgs; [
            taplo
            nodejs
          ] ++ buildInputs;
          shellHook = ''
              # For rust-analyzer 'hover' tooltips to work.
              export RUST_SRC_PATH="${rustToolchain}/lib/rustlib/src/rust/library";
            '';
        };
      }
    );
}
