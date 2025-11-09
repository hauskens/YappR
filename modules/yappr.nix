{
  config,
  lib,
  pkgs,
  ...
}:

with lib;

let
  cfg = config.services.yappr;

  isUnixSocket = builtins.typeOf cfg.database.host == "path";
  dbUri =
    if isUnixSocket then
      "postgresql://${cfg.database.name}?host=${toString cfg.database.host}&user=${cfg.database.user}"
    else
      "postgresql://${cfg.database.user}:\${DB_PASSWORD}@${cfg.database.host}:${toString cfg.database.port}/${cfg.database.name}";

  redisUri = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
  exe = lib.getExe cfg.package;

in
{
  options.services.yappr = {
    enable = mkEnableOption "YappR Web Application";

    package = mkOption {
      type = types.package;
      defaultText = literalExpression "pkgs.yappr-web or self.packages.\${pkgs.system}.web";
      description = ''
        The yappr-web package to use.
        Defaults to the package from this flake when using the nixosModule.
        If importing the module directly, you must provide this or apply the overlay.
      '';
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
        type = types.nullOr types.path;
        default = null;
        description = ''
          Path to file containing the PostgreSQL database password.
          This file should contain only the password, with no trailing newline.
          Not required when using Unix socket with peer authentication.
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
      description = "Directory for storing application data (audio files, transcriptions, etc.). Managed by StateDirectory.";
    };

    cacheDir = mkOption {
      type = types.path;
      default = "/var/cache/yappr";
      description = "Directory for storing cache files. Managed by CacheDirectory.";
    };

    auth = {
      appSecret = mkOption {
        type = types.str;
        description = ''
          Application secret key.
          Used for session encryption and other cryptographic operations.
          Generate with: openssl rand -hex 32
        '';
        default = "youshouldchangeme";
        example = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0";
      };

      appUrl = mkOption {
        type = types.str;
        example = "https://yappr.example.com";
        default = "http://localhost:${toString cfg.port}";
        description = "Public URL of the application (used for OAuth redirects).";
      };

      youtube = {
        apiKey = mkOption {
          type = types.nullOr types.str;
          description = "YouTube Data API key.";
          example = "AIzaSyD...";
        };

        apiKeyFile = mkOption {
          type = types.nullOr types.path;
          description = "Path to file containing YouTube Data API key.";
          example = "/run/secrets/yappr-youtube-api-key";
        };
      };

      discord = {
        clientId = mkOption {
          type = types.str;
          description = "Discord OAuth2 client ID.";
          example = "1234567890";
        };
        clientSecret = mkOption {
          type = types.nullOr types.str;
          description = "Discord OAuth2 client secret.";
          example = "1234567890";
        };

        clientSecretFile = mkOption {
          type = types.nullOr types.path;
          description = "Path to file containing Discord OAuth2 client secret.";
          example = "/run/secrets/yappr-discord-client-secret";
        };
      };

      twitch = {
        clientId = mkOption {
          type = types.str;
          description = "Twitch OAuth2 client ID.";
          example = "1234567890";
        };
        clientSecret = mkOption {
          type = types.nullOr types.str;
          description = "Twitch OAuth2 client secret.";
          example = "1234567890";
        };

        clientSecretFile = mkOption {
          type = types.nullOr types.path;
          description = "Path to file containing Twitch OAuth2 client secret.";
          example = "/run/secrets/yappr-twitch-client-secret";
        };
      };
    };

    logging = {
      level = mkOption {
        type = types.enum [
          "DEBUG"
          "INFO"
          "WARNING"
          "ERROR"
          "CRITICAL"
        ];
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
      {
        assertion = (builtins.typeOf cfg.database.host == "string") -> (cfg.database.passwordFile != null);
        message = "services.yappr.database.passwordFile must be set when using TCP connection (string host)";
      }
    ];

    services.postgresql = mkIf cfg.database.createLocally {
      enable = true;

      extensions = extensions: with extensions; [ pgvector ];

      ensureDatabases = [ cfg.database.name ];
      ensureUsers = [
        {
          name = cfg.database.user;
          ensureDBOwnership = true;
        }
      ];
    };

    # Create pgvector extension after database is set up
    systemd.services.yappr-db-setup = mkIf cfg.database.createLocally {
      description = "YappR Database Setup";
      after = [ "postgresql.service" ];
      wants = [ "postgresql.service" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "postgres";
      };

      script = ''
        ${config.services.postgresql.package}/bin/psql -d ${cfg.database.name} -c "CREATE EXTENSION IF NOT EXISTS vector;"
      '';
    };

    services.redis.servers.yappr = mkIf cfg.redis.createLocally {
      enable = true;
      port = cfg.redis.port;
      bind = cfg.redis.host;
    };

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

    systemd.services.yappr-web = {
      description = "YappR Leptos Web Application";
      wantedBy = [ "multi-user.target" ];
      after = [
        "network.target"
      ]
      ++ optional cfg.database.createLocally "yappr-db-setup.service"
      ++ optional cfg.redis.createLocally "redis-yappr.service";
      wants =
        optional cfg.database.createLocally "yappr-db-setup.service"
        ++ optional cfg.redis.createLocally "redis-yappr.service";

      environment = {
        DB_URI = dbUri;
        REDIS_URI = redisUri;

        APP_SECRET = cfg.auth.appSecret;
        APP_URL = cfg.auth.appUrl;
        HOST = cfg.host;
        PORT = toString cfg.port;

        STORAGE_LOCATION = cfg.dataDir;
        CACHE_LOCATION = cfg.cacheDir;

        LOG_LEVEL = cfg.logging.level;

        SERVICE_NAME = "web";
        ENVIRONMENT = cfg.environment;
        TIMEZONE = cfg.timezone;
        DISCORD_CLIENT_ID = cfg.auth.discord.clientId;
        DISCORD_CLIENT_SECRET = cfg.auth.discord.clientSecret;
        TWITCH_CLIENT_ID = cfg.auth.twitch.clientId;
        TWITCH_CLIENT_SECRET = cfg.auth.twitch.clientSecret;
        YOUTUBE_API_KEY = cfg.auth.youtube.apiKey;

        LEPTOS_SITE_ROOT = "${cfg.package}/bin/site";
        LEPTOS_OUTPUT_NAME = "yappr-web";
        LEPTOS_SITE_ADDR = "${cfg.host}:${toString cfg.port}";
        LEPTOS_ENV = "PROD";
      }
      // optionalAttrs (cfg.logging.lokiUrl != null) {
        LOKI_URL = cfg.logging.lokiUrl;
      };

      serviceConfig = {
        ReadWritePaths = optional cfg.database.createLocally [ "/run/postgresql" ];
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        Restart = "always";
        RestartSec = "10s";

        StateDirectory = "yappr yappr/data";
        StateDirectoryMode = "0750";
        CacheDirectory = "yappr";
        CacheDirectoryMode = "0750";

        LoadCredential =
          # Load DB password if provided
          (optional (cfg.database.passwordFile != null) "db-password:${cfg.database.passwordFile}");
      };

      # Minimal script to load secrets from credentials and start the app
      script = ''
        # Load secrets from systemd credentials
        ${optionalString (cfg.database.passwordFile != null) ''
          export DB_PASSWORD=$(cat $CREDENTIALS_DIRECTORY/db-password)
        ''}

        # Start the web server
        exec ${cfg.package}/bin/yappr-web
      '';
    };

    # Open firewall port if binding to 0.0.0.0
    networking.firewall.allowedTCPPorts = mkIf (cfg.host == "0.0.0.0" || cfg.host == "::") [ cfg.port ];
  };
}
