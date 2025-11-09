# NixOS Module for YappR

This flake provides a NixOS module and overlay for running the YappR Leptos web application as a systemd service.

## Features

- **NixOS Module**: Complete service configuration with `services.yappr`
- **Package Overlay**: Exposes `yappr-web` and `yappr-cli` packages
- **Local PostgreSQL**: Automatically configures PostgreSQL with pgvector extension
- **Local Redis**: Automatically configures Redis for caching
- **Unix Socket Support**: Uses Unix sockets by default for PostgreSQL (better performance)
- **Secret Management**: File-based secret management using systemd LoadCredential
- **Security Hardening**: Systemd service with proper isolation and permissions

## Quick Start

### 1. Import the Flake

Add this flake to your system's `flake.nix` inputs:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

    yappr = {
      # For GitHub (published):
      url = "github:yourusername/yappr";

      # For local development (respects git, excludes untracked files):
      # url = "git+file:///absolute/path/to/yappr";

      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, yappr, ... }: {
    nixosConfigurations.yourhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        yappr.nixosModules.default
        ./configuration.nix
      ];
    };
  };
}
```

**Important for local testing**: Use `git+file://` (not `path:`) for local development. The `git+file://` protocol respects your `.gitignore` and only includes git-tracked files.

### 2. Configure the Service

In your `configuration.nix`:

```nix
{ config, pkgs, ... }:

{
  # Enable the YappR service
  services.yappr = {
    enable = true;

    # Public URL for OAuth redirects
    auth.appUrl = "https://yappr.example.com";

    # Secret files (create these with proper permissions)
    database.passwordFile = "/run/secrets/yappr-db-password";
    auth.secretFile = "/run/secrets/yappr-app-secret";
    auth.discord.clientIdFile = "/run/secrets/yappr-discord-client-id";
    auth.discord.clientSecretFile = "/run/secrets/yappr-discord-client-secret";
    auth.twitch.clientIdFile = "/run/secrets/yappr-twitch-client-id";
    auth.twitch.clientSecretFile = "/run/secrets/yappr-twitch-client-secret";

    # Optional: YouTube API key
    apiKeys.youtubeFile = "/run/secrets/yappr-youtube-api-key";
  };

  # Optional: Configure nginx reverse proxy
  services.nginx = {
    enable = true;
    virtualHosts."yappr.example.com" = {
      forceSSL = true;
      enableACME = true;
      locations."/" = {
        proxyPass = "http://127.0.0.1:3000";
        proxyWebsockets = true;
      };
    };
  };
}
```

### 3. Create Secret Files

Create the required secret files with appropriate permissions:

```bash
# Database password
echo "your-secure-db-password" > /run/secrets/yappr-db-password
chmod 600 /run/secrets/yappr-db-password

# Application secret (generate with: openssl rand -hex 32)
openssl rand -hex 32 > /run/secrets/yappr-app-secret
chmod 600 /run/secrets/yappr-app-secret

# Discord OAuth credentials (from Discord Developer Portal)
echo "your-discord-client-id" > /run/secrets/yappr-discord-client-id
echo "your-discord-client-secret" > /run/secrets/yappr-discord-client-secret

# Twitch OAuth credentials (from Twitch Developer Console)
echo "your-twitch-client-id" > /run/secrets/yappr-twitch-client-id
echo "your-twitch-client-secret" > /run/secrets/yappr-twitch-client-secret

# Optional: YouTube API key (from Google Cloud Console)
echo "your-youtube-api-key" > /run/secrets/yappr-youtube-api-key

chmod 600 /run/secrets/yappr-*
```

### 4. Apply Configuration

```bash
sudo nixos-rebuild switch
```

The service will be available at `http://localhost:3000` (or your configured host/port).

## Configuration Options

### Basic Options

```nix
services.yappr = {
  enable = true;                    # Enable the service
  package = pkgs.yappr-web;         # Package to use (default)
  host = "127.0.0.1";               # Bind address (default: 127.0.0.1)
  port = 3000;                      # Bind port (default: 3000)
  user = "yappr";                   # Service user (default: yappr)
  group = "yappr";                  # Service group (default: yappr)
  timezone = "UTC";                 # Application timezone
  environment = "production";       # Environment name
};
```

### Database Options

```nix
services.yappr.database = {
  # Unix socket (default, recommended for performance)
  host = /run/postgresql;           # Use path for Unix socket

  # OR: TCP connection
  # host = "localhost";             # Use string for TCP
  # port = 5432;

  name = "yappr";                   # Database name
  user = "yappr";                   # Database user
  passwordFile = "/path/to/password"; # REQUIRED: Password file
  createLocally = true;             # Create PostgreSQL locally (default: true)
};
```

**Note**: The module automatically detects Unix socket vs TCP based on the type:
- **Path** (e.g., `/run/postgresql`): Uses Unix socket connection
- **String** (e.g., `"localhost"`): Uses TCP connection

### Redis Options

```nix
services.yappr.redis = {
  host = "localhost";               # Redis host
  port = 6379;                      # Redis port
  createLocally = true;             # Create Redis locally (default: true)
};
```

### Storage Options

```nix
services.yappr = {
  dataDir = "/var/lib/yappr/data";   # Data directory (audio, transcriptions)
  cacheDir = "/var/lib/yappr/cache"; # Cache directory
};
```

### Authentication Options

```nix
services.yappr.auth = {
  appUrl = "https://yappr.example.com";  # REQUIRED: Public URL
  secretFile = "/path/to/secret";        # REQUIRED: App secret

  discord = {
    clientIdFile = "/path/to/id";        # REQUIRED: Discord client ID
    clientSecretFile = "/path/to/secret"; # REQUIRED: Discord client secret
  };

  twitch = {
    clientIdFile = "/path/to/id";        # REQUIRED: Twitch client ID
    clientSecretFile = "/path/to/secret"; # REQUIRED: Twitch client secret
  };
};
```

### API Keys

```nix
services.yappr.apiKeys = {
  youtubeFile = "/path/to/key";     # Optional: YouTube Data API key
};
```

### Logging Options

```nix
services.yappr.logging = {
  level = "INFO";                   # DEBUG, INFO, WARNING, ERROR, CRITICAL
  lokiUrl = "http://localhost:3100/loki/api/v1/push"; # Optional: Loki endpoint
};
```

## Using the Overlay

You can also use the overlay to add yappr packages to your system:

```nix
{
  nixpkgs.overlays = [ yappr.overlays.default ];

  environment.systemPackages = with pkgs; [
    yappr-web  # Web application
    yappr-cli  # CLI tool
  ];
}
```

## Advanced Examples

### External PostgreSQL Database

To use an external PostgreSQL database instead of creating one locally:

```nix
services.yappr.database = {
  host = "db.example.com";  # External database host
  port = 5432;
  name = "yappr";
  user = "yappr";
  passwordFile = "/run/secrets/yappr-db-password";
  createLocally = false;    # Don't create local PostgreSQL
};
```

### Custom Port and Public Binding

To bind to all interfaces on a custom port:

```nix
services.yappr = {
  host = "0.0.0.0";         # Bind to all interfaces
  port = 8080;              # Custom port
};

# Firewall will be automatically opened for this port
```

### Development Environment

For a development/staging environment:

```nix
services.yappr = {
  environment = "staging";
  logging.level = "DEBUG";
  timezone = "Europe/Oslo";
};
```

## Service Management

### Check Service Status

```bash
systemctl status yappr-web
```

### View Logs

```bash
journalctl -u yappr-web -f
```

### Restart Service

```bash
systemctl restart yappr-web
```

## OAuth Setup

### Discord OAuth

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to OAuth2 settings
4. Add redirect URI: `https://your-domain.com/login/discord/authorized`
5. Copy Client ID and Client Secret to secret files

### Twitch OAuth

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console/apps)
2. Register a new application
3. Set OAuth Redirect URL: `https://your-domain.com/login/twitch/authorized`
4. Copy Client ID and Client Secret to secret files

### YouTube API (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Copy API key to secret file

## Security Considerations

- All secrets are loaded via systemd `LoadCredential` (never in Nix store)
- Service runs as unprivileged `yappr` user
- Filesystem access is restricted via systemd security features
- PostgreSQL uses Unix sockets by default (better security than TCP)
- Database password is never exposed in process list

## Troubleshooting

### Service fails to start

Check logs for errors:
```bash
journalctl -u yappr-web -n 50
```

### Database connection issues

Verify PostgreSQL is running and accessible:
```bash
systemctl status postgresql
sudo -u yappr psql -d yappr -c "SELECT 1"
```

### OAuth redirect errors

Ensure `auth.appUrl` matches your public domain and OAuth redirect URIs are correctly configured in Discord/Twitch developer portals.

## Migration from Docker

If you're migrating from the Docker setup:

1. Export your database: `pg_dump yappr > backup.sql`
2. Configure the NixOS module as shown above
3. Import database: `sudo -u postgres psql yappr < backup.sql`
4. Copy data directory: `cp -r /old/data/* /var/lib/yappr/data/`
5. Restart service: `systemctl restart yappr-web`
