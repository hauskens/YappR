# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# YappR - Rust Codebase Architecture

YappR is a self-hosted, open-source platform for searching, transcribing, and clip queue management for YouTube and Twitch content. This document describes the Rust codebase architecture (note: the project is migrating from Python to Rust).

## Important Notes

- **New files and Nix**: When you create new Rust files, you must add them to git tracking (`git add <filename>`) before running `nix build .#<project-name>`, otherwise Nix won't see them.
- **Transcription crate**: `crates/transcription` is excluded from the workspace due to GPU dependencies. Build it separately if needed.
- **Feature flags**: Pay attention to feature flags when building.
- **Shared crate**: `yappr-shared` is a shared crate that is used by all services. It contains database models, business logic, and API clients. Anything that could be shared between services should go in this crate.

## Technology Stack
- **Database**: PostgreSQL 17+ (pgvector/pgvector:pg17)
- **ORM**: SeaORM 1.1 (auto-generates Rust entities)
- **Session Storage**: PostgreSQL via tower-sessions-sqlx-store
- **Vector Search**: pgvector extension (semantic search on transcriptions)
- **Migrations**: Previously Alembic (Python), now using SeaORM

# Key Patterns & Design Decisions
## 1. Feature-Gated Architecture

All platform-specific code (Twitch, YouTube, Discord) is behind feature flags to have minimal dependencies when features are not needed.
Use feature flags on file-level if possible instead of code-level.

## 2. Shared Library Architecture

Single `yappr-shared` crate provides:
- Database entities and queries
- Configuration management
- External API clients (Twitch, YouTube)
- Services (business logic)
- Job definitions

This allows all services (web, bots, cli, worker) to share code without duplication.

## 3. Type-Safe Job Queue

Uses Rust's type system to ensure:
- Jobs map to correct subjects and response types
- Serialization handled transparently
- Zero runtime overhead

## 4. Structured Logging

Uses `tracing` crate with:
- Log levels (info, debug, warn, error)
- Contextual fields via macros (`#[instrument]`)
- Grafana Loki integration for production logging
- Consistent logging across all services


# High-Level Architecture Overview

1. **Web Service** (`yappr-web`): Full-stack Leptos/Axum application, frontend and backend for web application
2. **Bot Services** (`yappr-bot`): Twitch and Discord bot integrations
3. **Async Workers** (`worker`): NATS-based job queue for background processing
4. **Shared Library** (`yappr-shared`): Shared database models, business logic, and API clients
5. **CLI Tools** (`yappr-cli`): Admin utilities and debugging tools

## yappr-shared (Shared Library)

**Purpose**: Core abstractions, database models, and business logic shared by all services.

**Structure**:
```
src/
  config.rs          # Environment-based configuration system
  database.rs        # SeaORM database connection setup
  entities/          # Auto-generated SeaORM entities from DB schema
  services/          # Business logic layer
    - authorization.rs (RBAC, channel permissions)
    - broadcaster.rs (Broadcaster/Channel management)
    - channel.rs (Channel queries)
    - video.rs (Video metadata queries)
    - content.rs, content_queue.rs (Clip management)
    - transcription.rs (Transcription processing)
    - search.rs (Full-text + semantic search via pgvector)
    - moderation.rs (Moderation actions)
    - segment.rs (Video segments)
    - user.rs (User management)
  external/          # Platform API clients
    - api_client.rs (Trait-based abstraction)
    - twitch/        (Twitch API wrapper)
    - youtube/       (YouTube API wrapper)
  models/            # Domain model types
  jobs.rs            # Type-safe NATS job definitions
  nats.rs            # NATS client wrapper
```

**Key Features**:
- **Configuration Management**: Environment variables with validation, metadata, and defaults via `ConfigField<T>` wrapper
- **Feature Gating**:
  - `database`: SeaORM entities and services
  - `twitch`, `youtube`, `discord`: Platform-specific code
  - `job-queue`: NATS job queue support
  - `loki`: Grafana Loki logging

**Database Layer**:
- Uses **SeaORM** ORM (sea-orm 1.1)
- Entities auto-generated from database schema
- Key entities: `Video`, `Channel`, `Broadcaster`, `User`, `Transcription`, `Segments`, `Permissions`
- Session management via `tower-sessions-sqlx-store` (PostgreSQL-backed)
- Database connection pooling with configurable min/max connections

**Services Architecture**:
Each service module provides:
- Database queries via SeaORM
- Business logic and validation
- Result types using `DbErr` or custom errors
- Example: `VideoService::get_by_channel()` fetches videos for a specific channel

## Core Entities
1. **Broadcaster**: Top-level account, which usually represents a content creator or community
2. **Channel**: Platform-specific channel (Twitch stream, YouTube channel)
3. **Video**: Video/VOD metadata with duration, type, platform reference
4. **Transcription**: Full transcription text with timestamps (tsvector for FTS) of a video
5. **Segments**: Timestamped segments from transcriptions
6. **User**: User with Discord/Twitch identity, can be authenticated.
7. **Permissions**: RBAC - user/broadcaster/channel-level permissions
8. **ContentQueue**: User-submitted clips for curation/voting
9. **Chatlogs**: Chat messages from Platforms
10. **ModerationActions**: Bans, timeouts, deletions of users
