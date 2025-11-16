# YappR - Metadata and Transcription Search

A self-hosted, open-source platform for searching and transcribing audio from YouTube and Twitch, with integrated clip queue management.

> **Note**: This project is migrating from Python to Rust. The current Rust implementation is not production-ready for the web service, but the bots are.

## Overview

YappR is a metadata and transcription search tool that allows you to store and query metadata from various YouTube and Twitch channels. The project provides a flexible and extensible framework for storing and processing transcription data with a modern, type-safe Rust architecture.

## Key Features

### Transcription Search
- Advanced search across transcriptions from YouTube and Twitch content
- Full-text search with PostgreSQL tsvector and semantic search via pgvector
- Support for exact phrase matching using quotes
- Optimized for short clips (8-12 seconds) with distinctive keywords

### Clip Queue Management
- **Integrated Bots**: Twitch and Discord bots that listen for clip links
- **Community-Powered**: Hands-off highlight curation powered by your community
- **24/7 Submissions**: Users can share clips even when streamers are offline
- **Moderator Integration**: Twitch moderators have automatic permissions
- **Voting System**: Community-driven voting with reaction-based weighting

### Technical Features
- Full-stack web application with Server-Side Rendering (SSR)
- OAuth2 authentication (Discord and Twitch)
- Type-safe async job queue with NATS
- Real-time bot integrations Twitch and Discord
- GPU-accelerated transcription (WhisperX)
- Scalable architecture with feature-gated compilation

## Architecture

YappR is built as a **type-safe, feature-gated Rust monorepo** consisting of:

1. **Web Service** (`yappr-web`): Full-stack Leptos/Axum application with OAuth2 authentication
2. **Bot Services** (`yappr-bot`): Twitch and Discord bot integrations
3. **Async Workers** (`worker`): NATS-based job queue for background processing
4. **Shared Library** (`yappr-shared`): Database models, business logic, and API clients
5. **CLI Tools** (`yappr-cli`): Admin utilities and debugging tools

### High-Level Architecture Overview

YappR follows a **multi-service, feature-gated monorepo architecture** using Rust with PostgreSQL, NATS for async job queues, and Leptos for the web frontend.

```
┌─────────────────────────────────────────────────────────────┐
│                    WEB SERVICE (Leptos)                     │
│  SSR + Hydration with Axum backend, OAuth2 auth (Discord/   │
│  Twitch), Server Functions, Search, Broadcaster Management  │
└────────────────────┬────────────────────────────────────────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
┌──────▼──────┐  ┌───▼────────┐  ┌▼──────────────┐
│   BOTS      │  │  WORKERS   │  │  CLI          │
│ (Twitch,    │  │ (NATS-based│  │ (Admin/Debug  │
│  Discord)   │  │  job queue)│  │  Commands)    │
└──────┬──────┘  └───┬────────┘  └┬──────────────┘
       │             │            │
       └─────────────┼────────────┘
                     │
       ┌─────────────┴──────────────┐
       │                            │
   ┌───▼──────────────────┐   ┌────▼─────────────┐
   │   SHARED LIBRARY     │   │  NATS MESSAGE    │
   │ (Database, Services, │   │  BROKER          │
   │  Entities, Config,   │   │  (Job Queue)     │
   │  External APIs)      │   └──────────────────┘
   └───┬──────────────────┘
       │
   ┌───▼──────────────────┐
   │  POSTGRESQL DB       │
   │  + pgvector          │
   │  (SeaORM + Sessions) │
   └──────────────────────┘
```


## Technologies

### Current Stack (Rust)
- **Language**: Rust (Edition 2024)
- **Web Framework**: Leptos 0.8 (SSR + hydration) with Axum 0.8
- **Database**: PostgreSQL 17+ with pgvector extension
- **ORM**: SeaORM 1.1
- **Message Queue**: NATS with JetStream
- **APIs**: Twitch API, YouTube Data API v3
- **Bot Frameworks**: Serenity (Discord), twitch_api (Twitch EventSub)
- **Authentication**: OAuth2 (Discord, Twitch) with tower-sessions
- **Logging**: tracing with Grafana Loki integration
- **Build System**: Nix flakes for reproducible builds

### Legacy Stack (Python - being phased out)
- Flask, Celery, Alembic
- Discord.py, TwitchAPI
- WhisperX (GPU transcription - being migrated)

## Quick Start

### Using Nix (Recommended)

```bash
# Enter development environment
nix develop

# Build the web service
nix build .#web

# Run the web service
nix run .#web
```

### Using Docker Compose

```bash
# Start all services (PostgreSQL, NATS, web service)
docker compose up --build

# Start with watch mode (hot reload)
docker compose up --build --watch
```

### Using Cargo

```bash
# Build all crates
cargo build

# Run the web service
cargo leptos watch

# Run Twitch bot
cargo run -p yappr-bot --bin twitch-bot --no-default-features --features twitch

# Run Discord bot
cargo run -p yappr-bot --bin discord-bot --no-default-features --features discord
```

## Configuration

Configuration is managed through environment variables with type-safe validation. Create a `.env` file in the project root:

### Required Configuration

```bash
# Application
SERVICE_NAME=yappr-web
ENVIRONMENT=development
DEBUG=true

# Database (PostgreSQL 17+ with pgvector)
DB_URI=postgresql://postgres:password@localhost:5432/yappr
DB_MAX_CONNECTIONS=10
DB_MIN_CONNECTIONS=2

# Session Management
SESSION_SECRET=your-random-secret-key-here

# NATS (for async jobs)
NATS_URL=nats://localhost:4222
```

### OAuth2 Configuration (for web service)

```bash
# Discord OAuth2
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret

# Twitch OAuth2
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
```

### Bot Configuration

```bash
# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token

# Twitch Bot (requires OAuth2 credentials above)
TWITCH_BOT_USER_ID=your_twitch_bot_user_id
```

### Optional Configuration

```bash
# YouTube API
YOUTUBE_API_KEY=your_youtube_api_key

# Logging (Grafana Loki)
LOKI_URL=http://localhost:3100/loki/api/v1/push

# Storage
STORAGE_LOCATION=/var/lib/yappr/data

# Transcription (GPU required)
TRANSCRIPTION_DEVICE=cuda
TRANSCRIPTION_MODEL=large-v2
```

See [CLAUDE.md](./CLAUDE.md) for complete configuration reference.

## API Key Setup

### YouTube API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the YouTube Data API v3
4. Create credentials → API key
5. Copy the API key and set it as `YOUTUBE_API_KEY`

### Twitch API Keys
1. Go to [Twitch Developer Console](https://dev.twitch.tv/console/apps)
2. Create a new application
3. Set the OAuth redirect URI to `{APP_URL}/auth/twitch/callback`
4. Copy the Client ID and Client Secret
5. Set them as `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`

### Discord API Keys
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to OAuth2 settings
4. Add redirect URI: `{APP_URL}/auth/discord/callback`
5. Copy the Client ID and Client Secret
6. Set them as `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET`
7. For the bot: Go to Bot section, create a bot, and copy the token as `DISCORD_BOT_TOKEN`

## Development

### Building

```bash
# Build all crates
cargo build

# Build specific crate
cargo build -p yappr-web
cargo build -p yappr-bot --no-default-features --features twitch

# Build with Nix
nix build .#web
nix build .#twitch-bot
```

### Running

```bash
# Web service with hot reload
cargo leptos watch

# Individual services
cargo run -p yappr-cli
cargo run -p worker
```

### Testing

```bash
# Run all tests
cargo test

# Run tests for specific crate
cargo test -p yappr-shared

# Run all checks (tests, clippy, fmt)
nix flake check
```

### Code Quality

```bash
# Format code
cargo fmt

# Run linter
cargo clippy --all-targets -- --deny warnings

# Check with Nix
nix build .#fmt
nix build .#clippy
```

## Deployment

### Using Nix (Recommended)

The project includes a custom deployment script that builds Docker images and pushes them to your registry:

```bash
# Set your registry
export DOCKER_REGISTRY=your-registry.azurecr.io

# Deploy web service
yappr-deploy web

# Deploy bots
yappr-deploy twitch-bot
yappr-deploy discord-bot
```

This will:
1. Build the Nix package
2. Create a Docker image
3. Tag with `latest` and version from `Cargo.toml`
4. Push to your registry

### Using Docker Compose

For local deployment or testing:

```bash
docker compose up --build
```

## Project Structure

```
yappr/
├── crates/
│   ├── web/          # Full-stack Leptos web application
│   ├── bots/         # Twitch and Discord bots
│   ├── shared/       # Shared library (database, services, config)
│   ├── worker/       # NATS job queue worker
│   ├── cli/          # Command-line tools
│   └── transcription/ # GPU transcription (excluded from workspace)
├── flake.nix         # Nix build configuration
├── Cargo.toml        # Workspace configuration
├── docker-compose.yml # Local development setup
├── CLAUDE.md         # Detailed architecture documentation
└── README.md         # This file
```

## Database

YappR uses PostgreSQL 17+ with the pgvector extension for:
- Relational data storage (SeaORM)
- Full-text search (tsvector)
- Semantic search (vector embeddings)
- Session storage (tower-sessions)

The database schema includes entities for:
- Broadcasters and Channels
- Videos and Transcriptions
- Users and Permissions
- Content Queue and Voting
- Chat Logs and Moderation

## Search Features

YappR provides advanced search capabilities:

- **Full-Text Search**: PostgreSQL tsvector for fast keyword matching
- **Semantic Search**: pgvector for AI-powered content discovery
- **Exact Phrase Matching**: Use quotes for strict matching
- **Time-Range Filtering**: Search within specific time periods
- **Channel Filtering**: Search within specific channels or broadcasters

## Attribution

This project was originally inspired by and would not have happened without the project [SqueexVodSearch](https://github.com/lawrencehook/SqueexVodSearch) by [@lawrencehook](https://github.com/lawrencehook).

Special thanks to [@yellowbear](https://www.youtube.com/@yellllowbear) and [@ACB](https://www.twitch.tv/acb_x) for invaluable inspiration and feedback.

Also thanks to [NLQotes](https://github.com/irinelul/NLQuotes) for inspiration to use `tsvector` in PostgreSQL.

Some code, comments, and documentation were generated or refined with the help of large-language-model tools. All outputs were reviewed and integrated by the project maintainer.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting (`cargo test`, `cargo clippy`, `cargo fmt`)
5. Submit a pull request

For major changes, please open an issue first to discuss what you would like to change.

## License

YappR is released under the **GNU General Public License (GPL) version 2**.
