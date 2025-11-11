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
    (flake-utils.lib.eachDefaultSystem (
      system:
      let
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs {
          inherit system overlays;
        };

        inherit (pkgs) lib;

        # Extract version from workspace Cargo.toml
        cargoToml = lib.importTOML ./Cargo.toml;
        version = cargoToml.workspace.package.version;
        rustToolchain = pkgs.rust-bin.stable.latest.default.override {
          extensions = [
            "rust-src"
            "rust-analyzer"
            "clippy"
            "rustc"
          ];
        };
        buildInputs =
          with pkgs;
          [
            openssl
          ]
          ++ lib.optional stdenv.isLinux [
            strace
          ]
          ++ lib.optionals pkgs.stdenv.isDarwin [
            pkgs.libiconv
          ];
        craneLib = crane.mkLib pkgs;
        src = craneLib.cleanCargoSource ./.;

        # Common arguments
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

        npmDeps = pkgs.buildNpmPackage {
          pname = "yappr-npm-deps";
          version = "1.0.0";
          src = ./crates/web;

          npmDepsHash = "sha256-mJMEfwlfE7V8LmnyMb61hs0oKZbF7I0m6RtqRQdff3U=";

          installPhase = ''
            mkdir -p $out
            cp -r public/vendor $out/
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
        twitch-bot = craneLib.buildPackage (
          individualCrateArgs
          // {
            pname = "twitch-bot";
            cargoExtraArgs = "--bin twitch-bot --no-default-features --features twitch";
            src = fileSetForCrate ./crates/bots;
          }
        );
        discord-bot = craneLib.buildPackage (
          individualCrateArgs
          // {
            pname = "discord-bot";
            cargoExtraArgs = "--bin discord-bot --no-default-features --features discord";
            src = fileSetForCrate ./crates/bots;
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
              mkdir -p crates/web/public/vendor
              cp -r ${npmDeps}/vendor/* crates/web/public/vendor/
            '';
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
                    "ico"
                    "png"
                    "svg"
                  ]
                ) ./crates/web)
              ];
            };
            meta = {
              mainProgram = "yappr-web";
            };
          }
        );

        # Container image for web application
        web-container = pkgs.dockerTools.buildLayeredImage {
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
              "3000/tcp" = { };
            };
            WorkingDir = "/";
            Labels = {
              "org.opencontainers.image.version" = version;
              "org.opencontainers.image.title" = "yappr-web";
              "org.opencontainers.image.description" = "YappR Web Application";
            };
          };
        };
        twitch-bot-container = pkgs.dockerTools.buildLayeredImage {
          name = "yappr-twitch-bot";
          tag = "latest";

          contents = [
            twitch-bot
            pkgs.cacert
          ];

          config = {
            Cmd = [ "${twitch-bot}/bin/twitch-bot" ];
            Env = [
              "SERVICE_NAME=twitch-bot"
            ];
            Labels = {
              "org.opencontainers.image.version" = version;
              "org.opencontainers.image.title" = "yappr-twitch-bot";
              "org.opencontainers.image.description" = "YappR Twitch Bot";
            };
          };
        };
        discord-bot-container = pkgs.dockerTools.buildLayeredImage {
          name = "yappr-discord-bot";
          tag = "latest";

          contents = [
            discord-bot
            pkgs.cacert
          ];

          config = {
            Cmd = [ "${discord-bot}/bin/discord-bot" ];
            Env = [
              "SERVICE_NAME=discord-bot"
            ];
            Labels = {
              "org.opencontainers.image.version" = version;
              "org.opencontainers.image.title" = "yappr-discord-bot";
              "org.opencontainers.image.description" = "YappR Discord Bot";
            };
          };
        };

        # Extract container image names (packages ending with -container)
        containerPackages = {
          inherit web-container twitch-bot-container discord-bot-container;
        };
        imageNames = map (name: lib.removeSuffix "-container" name) (lib.attrNames containerPackages);
        imagesArrayBash = lib.concatMapStringsSep "\n  " (name: ''"${name}"'') imageNames;

        # Deployment script with auto-populated image names and version from Cargo.toml
        yappr-deploy = pkgs.writeShellApplication {
          name = "yappr-deploy";
          runtimeInputs = [ pkgs.docker pkgs.nix ];
          text = ''
            # Auto-generated from flake packages
            IMAGES=(
              ${imagesArrayBash}
            )

            # Version from Cargo.toml workspace
            VERSION="${version}"

            usage() {
              echo "Usage: yappr-deploy <image>"
              echo ""
              echo "Available images:"
              for img in "''${IMAGES[@]}"; do
                echo "  - $img"
              done
              echo ""
              echo "Environment variables:"
              echo "  DOCKER_REGISTRY - Docker registry to push to (required)"
              echo ""
              echo "Current version: $VERSION (from Cargo.toml)"
              echo ""
              echo "Example:"
              echo "  export DOCKER_REGISTRY=your-registry.azurecr.io"
              echo "  yappr-deploy web"
              echo ""
              echo "This will push:"
              echo "  - your-registry.azurecr.io/yappr-web:latest"
              echo "  - your-registry.azurecr.io/yappr-web:$VERSION"
              exit 1
            }

            if [ $# -eq 0 ]; then
              usage
            fi

            IMAGE=$1

            # Check for DOCKER_REGISTRY
            if [ -z "''${DOCKER_REGISTRY:-}" ]; then
              echo "Error: DOCKER_REGISTRY environment variable is not set"
              echo "Example: export DOCKER_REGISTRY=your-registry.azurecr.io"
              exit 1
            fi

            IMAGE_FULL_NAME="yappr-''${IMAGE}"
            CONTAINER_TARGET="''${IMAGE}-container"

            echo "🔨 Building $CONTAINER_TARGET (version $VERSION)..."
            nix build ".#$CONTAINER_TARGET" >/dev/null

            echo "📦 Loading image into Docker..."
            docker load < result >/dev/null

            echo "🏷️  Tagging images..."
            docker tag "''${IMAGE_FULL_NAME}:latest" "''${DOCKER_REGISTRY}/''${IMAGE_FULL_NAME}:latest"
            docker tag "''${IMAGE_FULL_NAME}:latest" "''${DOCKER_REGISTRY}/''${IMAGE_FULL_NAME}:$VERSION"

            echo "🚀 Pushing to registry..."
            docker push "''${DOCKER_REGISTRY}/''${IMAGE_FULL_NAME}:latest" >/dev/null
            docker push "''${DOCKER_REGISTRY}/''${IMAGE_FULL_NAME}:$VERSION" >/dev/null

            echo "✅ Successfully deployed ''${IMAGE_FULL_NAME}:latest and ''${IMAGE_FULL_NAME}:$VERSION to ''${DOCKER_REGISTRY}"
          '';
        };
      in
      {
        checks = {
          # Build the crates as part of `nix flake check` for convenience
          inherit cli web twitch-bot discord-bot;

          clippy = craneLib.cargoClippy (
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
          fmt = craneLib.cargoFmt {
            inherit src;
          };

          toml-fmt = craneLib.taploFmt {
            src = pkgs.lib.sources.sourceFilesBySuffices src [ ".toml" ];
            # taplo arguments can be further customized below as needed
            # taploExtraArgs = "--config ./taplo.toml";
          };

          # tests
          nextest = craneLib.cargoNextest (
            commonArgs
            // {
              inherit cargoArtifacts;
              partitions = 1;
              partitionType = "count";
              cargoNextestPartitionsExtraArgs = "--no-tests=pass";
            }
          );
        };

        packages = {
          inherit cli web twitch-bot twitch-bot-container web-container discord-bot discord-bot-container yappr-deploy;
          default = web;
        };

        apps = {
          cli = flake-utils.lib.mkApp {
            drv = cli;
          };
          twitch-bot = flake-utils.lib.mkApp {
            drv = twitch-bot;
          };
          web = flake-utils.lib.mkApp {
            drv = web;
          };
          discord-bot = flake-utils.lib.mkApp {
            drv = discord-bot;
          };
        };

        devShells.default = craneLib.devShell {
          checks = self.checks.${system};
          LIBCLANG_PATH = "${pkgs.llvmPackages_latest.libclang.lib}/lib";
          BINDGEN_EXTRA_CLANG_ARGS = with pkgs; 
            "-isystem ${llvmPackages_latest.libclang.lib}/lib/clang/${lib.versions.major (lib.getVersion llvmPackages_latest.clang)}/include " +
            "-isystem ${glibc.dev}/include";


          buildInputs = with pkgs; [
              vulkan-loader
            ];
          nativeBuildInputs = with pkgs; [
            rustToolchain
            pkg-config
            openssl
            cmake
            gcc
            glibc.dev
            
            # Clang/LLVM for bindgen - use consistent version
            llvmPackages_latest.clang
            llvmPackages_latest.libclang.lib
            
            # Vulkan for whisper-rs
            vulkan-headers
            vulkan-tools
            shaderc
          ];
          packages =
            with pkgs;
            [
              rustToolchain
              cmake
              gcc
              pkg-config
              vulkan-headers
              vulkan-tools
              shaderc
              taplo
              nodejs
              yappr-deploy

            ]
            ++ buildInputs;
          shellHook = ''
            # For rust-analyzer 'hover' tooltips to work.
            export RUST_SRC_PATH="${rustToolchain}/lib/rustlib/src/rust/library";
          '';
        };
      }
    ))
    // {
      # System-independent outputs
      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        {
          imports = [ ./modules/yappr.nix ];

          # Provide default package from this flake
          config = lib.mkIf config.services.yappr.enable {
            services.yappr.package = lib.mkDefault self.packages.${pkgs.system}.web;
          };
        };

      # Overlay for other flakes to use
      overlays.default = final: prev: {
        yappr-web = self.packages.${prev.system}.web;
        yappr-cli = self.packages.${prev.system}.cli;
        yappr-twitch-bot = self.packages.${prev.system}.twitch-bot;
        yappr-discord-bot = self.packages.${prev.system}.discord-bot;
      };
    };
}
