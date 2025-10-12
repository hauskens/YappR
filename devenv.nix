{ pkgs, lib, config, inputs, ... }:

let
  buildInputs = with pkgs; [
    stdenv.cc.cc
    libuv
    zlib


    clang
    libclang.lib
    llvmPackages.libclang
    llvmPackages.libclang.lib
    llvmPackages.bintools
    gcc
    glibc.dev
    cmake
    pkg-config
  ];

in
{

  # https://devenv.sh/packages/
  packages = with pkgs; [ 
    git 
    zsh 
    python3Packages.psycopg2
    psqlodbc
    wasm-pack
    cargo-watch
    cargo-edit
    cargo-machete
    lld
    trunk
    pkg-config
    openssl
    sea-orm-cli
    ] ++ buildInputs;

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
      # targets = [ "wasm32-unknown-unknown" ];
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
    LIBCLANG_PATH = pkgs.lib.makeLibraryPath [ pkgs.llvmPackages_latest.libclang.lib ];
    BINDGEN_EXTRA_CLANG_ARGS = with pkgs; ''
          -isystem ${llvmPackages.libclang.lib}/lib/clang/${lib.getVersion clang}/include
          -isystem ${llvmPackages.libclang.out}/lib/clang/${lib.getVersion clang}/include
          -isystem ${glibc.dev}/include
        '';
    
    NIX_CFLAGS_COMPILE = "-isystem ${pkgs.glibc.dev}/include";
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
