{ pkgs, lib, config, inputs, ... }:

let
  buildInputs = with pkgs; [
    stdenv.cc.cc
    libuv
    zlib
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
    lld
    trunk
    pkg-config
    openssl
    sea-orm-cli
    ];

  languages = {
    python = {
      enable = true;
      uv = {
        enable = true;
        sync.enable = true;
      };
    };
    rust = {
      enable = true;
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
