{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.yappr;

  # Build database URI from configuration
  # Format: postgresql://database?host=/socket/path&user=user&password=pass (Unix socket)
  # Format: postgresql://user:password@host:port/database (TCP)
  # Password is loaded at runtime from file
  isUnixSocket = builtins.typeOf cfg.database.host == "path";
  dbUri =
    if isUnixSocket
    then "postgresql://${cfg.database.name}?host=${toString cfg.database.host}&user=${cfg.database.user}&password=\${DB_PASSWORD}"
    else "postgresql://${cfg.database.user}:\${DB_PASSWORD}@${cfg.database.host}:${toString cfg.database.port}/${cfg.database.name}";

  # Redis URI
  redisUri = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";

in
{
  options.services.yappr = {
    enable = mkEnableOption "YappR Leptos web application";

    package = mkOption {
      type = types.package;
      default = pkgs.yappr-web;
      defaultText = literalExpression "pkgs.yappr-web";
      description = "The yappr-web package to use.";
    };

    host = mkOption {
      type = types.str;
      default = "127.0.0.1";
      example = "0.0.0.0";
      description = "Host address to bind the web server to.";
    };

    port = mkOption {
      type = types.port;
      default = 3000;
      description = "Port to bind the web server to.";
    };

    database = {
      host = mkOption {
        type = types.either types.path types.str;
        default = /run/postgresql;
        description = ''
          PostgreSQL database host.
          Use a path (e.g., /run/postgresql) for Unix socket connection (default).
          Use a string (e.g., "localhost" or "127.0.0.1") for TCP connection.
        '';
      };

      port = mkOption {
        type = types.port;
        default = 5432;
        description = "PostgreSQL database port.";
      };

      name = mkOption {
        type = types.str;
        default = "yappr";
        description = "PostgreSQL database name.";
      };

      user = mkOption {
        type = types.str;
        default = "yappr";
        description = "PostgreSQL database user.";
      };

      passwordFile = mkOption {
        type = types.path;
        description = ''
          Path to file containing the PostgreSQL database password.
          This file should contain only the password, with no trailing newline.
        '';
        example = "/run/secrets/yappr-db-password";
      };

      createLocally = mkOption {
        type = types.bool;
        default = true;
        description = ''
          Whether to create the PostgreSQL database locally.
          If true, a PostgreSQL service will be configured with pgvector extension.
        '';
      };
    };

    redis = {
      host = mkOption {
        type = types.str;
        default = "localhost";
        description = "Redis host.";
      };

      port = mkOption {
        type = types.port;
        default = 6379;
        description = "Redis port.";
      };

      createLocally = mkOption {
        type = types.bool;
        default = true;
        description = "Whether to create a Redis service locally.";
      };
    };

    dataDir = mkOption {
      type = types.path;
      default = "/var/lib/yappr/data";
      description = "Directory for storing application data (audio files, transcriptions, etc.).";
    };

    cacheDir = mkOption {
      type = types.path;
      default = "/var/lib/yappr/cache";
      description = "Directory for storing cache files.";
    };

    auth = {
      secretFile = mkOption {
        type = types.path;
        description = ''
          Path to file containing the application secret key.
          Used for session encryption and other cryptographic operations.
          Generate with: openssl rand -hex 32
        '';
        example = "/run/secrets/yappr-app-secret";
      };

      appUrl = mkOption {
        type = types.str;
        example = "https://yappr.example.com";
        description = "Public URL of the application (used for OAuth redirects).";
      };

      discord = {
        clientIdFile = mkOption {
          type = types.path;
          description = "Path to file containing Discord OAuth2 client ID.";
          example = "/run/secrets/yappr-discord-client-id";
        };

        clientSecretFile = mkOption {
          type = types.path;
          description = "Path to file containing Discord OAuth2 client secret.";
          example = "/run/secrets/yappr-discord-client-secret";
        };
      };

      twitch = {
        clientIdFile = mkOption {
          type = types.path;
          description = "Path to file containing Twitch OAuth2 client ID.";
          example = "/run/secrets/yappr-twitch-client-id";
        };

        clientSecretFile = mkOption {
          type = types.path;
          description = "Path to file containing Twitch OAuth2 client secret.";
          example = "/run/secrets/yappr-twitch-client-secret";
        };
      };
    };

    apiKeys = {
      youtubeFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to file containing YouTube Data API key (optional).";
        example = "/run/secrets/yappr-youtube-api-key";
      };
    };

    logging = {
      level = mkOption {
        type = types.enum [ "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL" ];
        default = "INFO";
        description = "Logging level for the application.";
      };

      lokiUrl = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Loki endpoint URL for centralized logging (optional).";
        example = "http://localhost:3100/loki/api/v1/push";
      };
    };

    timezone = mkOption {
      type = types.str;
      default = "UTC";
      example = "Europe/Oslo";
      description = "Timezone for the application.";
    };

    environment = mkOption {
      type = types.str;
      default = "production";
      description = "Application environment (production, staging, development).";
    };

    user = mkOption {
      type = types.str;
      default = "yappr";
      description = "User account under which yappr runs.";
    };

    group = mkOption {
      type = types.str;
      default = "yappr";
      description = "Group under which yappr runs.";
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.auth.appUrl != "";
        message = "services.yappr.auth.appUrl must be set";
      }
    ];

    # Create PostgreSQL database locally if requested
    services.postgresql = mkIf cfg.database.createLocally {
      enable = true;

      # Enable pgvector extension
      extraPlugins = with pkgs.postgresql.pkgs; [ pgvector ];

      # Ensure database and user are created
      ensureDatabases = [ cfg.database.name ];
      ensureUsers = [
        {
          name = cfg.database.user;
          ensureDBOwnership = true;
        }
      ];

      # Enable pgvector extension for the database
      initialScript = pkgs.writeText "yappr-init.sql" ''
        \c ${cfg.database.name}
        CREATE EXTENSION IF NOT EXISTS vector;
      '';
    };

    # Create Redis service locally if requested
    services.redis.servers.yappr = mkIf cfg.redis.createLocally {
      enable = true;
      port = cfg.redis.port;
      bind = cfg.redis.host;
    };

    # Create user and group
    users.users = mkIf (cfg.user == "yappr") {
      yappr = {
        isSystemUser = true;
        group = cfg.group;
        description = "YappR service user";
        home = "/var/lib/yappr";
        createHome = true;
      };
    };

    users.groups = mkIf (cfg.group == "yappr") {
      yappr = { };
    };

    # Create systemd service
    systemd.services.yappr-web = {
      description = "YappR Leptos Web Application";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ]
        ++ optional cfg.database.createLocally "postgresql.service"
        ++ optional cfg.redis.createLocally "redis-yappr.service";
      wants = optional cfg.database.createLocally "postgresql.service"
        ++ optional cfg.redis.createLocally "redis-yappr.service";

      # Set up state directories
      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        Restart = "always";
        RestartSec = "10s";
        WorkingDirectory = cfg.dataDir;

        # State directories
        StateDirectory = "yappr";
        StateDirectoryMode = "0750";

        # Load secrets from files
        LoadCredential = [
          "db-password:${cfg.database.passwordFile}"
          "app-secret:${cfg.auth.secretFile}"
          "discord-client-id:${cfg.auth.discord.clientIdFile}"
          "discord-client-secret:${cfg.auth.discord.clientSecretFile}"
          "twitch-client-id:${cfg.auth.twitch.clientIdFile}"
          "twitch-client-secret:${cfg.auth.twitch.clientSecretFile}"
        ] ++ optional (cfg.apiKeys.youtubeFile != null) "youtube-api-key:${cfg.apiKeys.youtubeFile}";

        # Security hardening
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ cfg.dataDir cfg.cacheDir ];
      };

      # Build environment variables
      script = ''
        # Read secrets from credentials
        export DB_PASSWORD=$(cat $CREDENTIALS_DIRECTORY/db-password)
        export APP_SECRET=$(cat $CREDENTIALS_DIRECTORY/app-secret)
        export DISCORD_CLIENT_ID=$(cat $CREDENTIALS_DIRECTORY/discord-client-id)
        export DISCORD_CLIENT_SECRET=$(cat $CREDENTIALS_DIRECTORY/discord-client-secret)
        export TWITCH_CLIENT_ID=$(cat $CREDENTIALS_DIRECTORY/twitch-client-id)
        export TWITCH_CLIENT_SECRET=$(cat $CREDENTIALS_DIRECTORY/twitch-client-secret)
        ${optionalString (cfg.apiKeys.youtubeFile != null) ''
          export YOUTUBE_API_KEY=$(cat $CREDENTIALS_DIRECTORY/youtube-api-key)
        ''}

        # Database configuration
        export DB_URI="${dbUri}"

        # Redis configuration
        export REDIS_URI="${redisUri}"

        # Application configuration
        export APP_URL="${cfg.auth.appUrl}"
        export HOST="${cfg.host}"
        export PORT="${toString cfg.port}"

        # OAuth redirect URIs
        export DISCORD_REDIRECT_URI="${cfg.auth.appUrl}/login/discord/authorized"
        export TWITCH_REDIRECT_URI="${cfg.auth.appUrl}/login/twitch/authorized"

        # Storage paths
        export STORAGE_LOCATION="${cfg.dataDir}"
        export CACHE_LOCATION="${cfg.cacheDir}"

        # Logging configuration
        export LOG_LEVEL="${cfg.logging.level}"
        ${optionalString (cfg.logging.lokiUrl != null) ''
          export LOKI_URL="${cfg.logging.lokiUrl}"
        ''}

        # Service metadata
        export SERVICE_NAME="web"
        export ENVIRONMENT="${cfg.environment}"
        export TIMEZONE="${cfg.timezone}"

        # Leptos configuration
        export LEPTOS_SITE_ROOT="${cfg.package}/bin/site"
        export LEPTOS_OUTPUT_NAME="yappr-web"
        export LEPTOS_SITE_ADDR="${cfg.host}:${toString cfg.port}"
        export LEPTOS_ENV="PROD"

        # Start the web server
        exec ${cfg.package}/bin/yappr-web
      '';

      # Pre-start: ensure directories exist
      preStart = ''
        mkdir -p ${cfg.dataDir}
        mkdir -p ${cfg.cacheDir}
        chown -R ${cfg.user}:${cfg.group} ${cfg.dataDir}
        chown -R ${cfg.user}:${cfg.group} ${cfg.cacheDir}
      '';
    };

    # Open firewall port if binding to 0.0.0.0
    networking.firewall.allowedTCPPorts = mkIf (cfg.host == "0.0.0.0" || cfg.host == "::") [ cfg.port ];
  };
}
