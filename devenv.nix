{ pkgs, lib, config, inputs, ... }:

let
  buildInputs = with pkgs; [
    stdenv.cc.cc
    libuv
    zlib
  ];
  cargo-leptos-custom = pkgs.rustPlatform.buildRustPackage rec {
    pname = "cargo-leptos";
    version = "0.2.44";
    src = pkgs.fetchFromGitHub {
    owner = "leptos-rs";
    repo = "cargo-leptos";
    rev = "v${version}";
    hash = "sha256-SjpfM963Zux+H5QhK8prvDLuI56fP5PqX5gcVbthRx5=";
  };
  checkFlags = [
    # requires network access, thanks nixpkgs for figuring this out
    "--skip=server::web::proxy::test::add_proxy"
    "--skip=server::web::proxy::test::add_proxy_trailing_slash"
  ];

  cargoHash = "sha256-Da9ei4yAOfhSQmQgrUDZCmMeJXTfGnYhI1+L0JT/ECs=";

  # https://github.com/leptos-rs/cargo-leptos#dependencies
  buildFeatures = [ "no_downloads" ]; # cargo-leptos will try to install missing dependencies on its own otherwise
  doCheck = false; 
  };
  # wasm-bindgen-cli-custom = pkgs.rustPlatform.buildRustPackage rec {
  #   pname = "wasm-bindgen-cli";
  #   version = "0.2.102";
  #   src = pkgs.fetchCrate {
  #     inherit pname version;
  #     sha256 = "sha256-onynh0cGDko4RhNHfhvV9xlnyj+H7aPrwcBRIQm24so=";
  #   };
  #   cargoHash = "sha256-zNK9ihmX2TaHyXY8KuVXHPFGnCp8VouvLiZs7mBvbtM=";
  #   nativeBuildInputs = [ pkgs.pkg-config ];
  #   buildInputs = [ pkgs.openssl ];
  #   OPENSSL_NO_VENDOR = 1;
  # };
in
{

  # https://devenv.sh/packages/
  packages = with pkgs; [ 
    git 
    zsh 
    python3Packages.psycopg2
    psqlodbc
    wasm-pack
    #wasm-bindgen-cli-custom
    cargo-leptos-custom
    cargo-watch
    cargo-edit
    cargo-machete
    # cargo-leptos
    lld
    trunk
    pkg-config
    openssl
    sea-orm-cli
    # (import ./scripts/cargo.nix {pkgs = pkgs;})
    # dioxus-cli
    ];

  languages = {
    python = {
      enable = true;
      package = pkgs.python312;
      uv = {
        enable = true;
        sync.enable = true;
      };
    };
    rust = {
      enable = true;
      channel = "stable";
      targets = [ "wasm32-unknown-unknown" ];
      components = [ "rustc" "cargo" "clippy" "rustfmt" "rust-analyzer" ];
    };
    javascript = {
      enable = true;
      bun = {
        enable = true;
        install.enable = true;
      };
    };
    # typescript.enable = true;
  };

  env = {
    LD_LIBRARY_PATH = "${lib.makeLibraryPath buildInputs}";
  };

  dotenv.enable = true;

  enterShell = ''
    . .devenv/state/venv/bin/activate
  '';

  scripts = {
    ",db:new".exec = "alembic revision --autogenerate -m '$@'";
    ",db:upgrade".exec = "alembic upgrade head";
    ",db:downgrade".exec = "alembic downgrade -1";
    ",db:seaorm".exec = "sea-orm-cli generate entity -o src/entities --database-url $DATABASE_URL";
  };

}
