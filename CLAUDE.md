# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Running the Application
- Development with Docker: `docker compose up --build --watch`
- Development with UV: `uv run app/main.py`
- Production: `docker compose up --build`

### Frontend Dependencies
- Install frontend dependencies: `pnpm install && pnpm run build`
- Build frontend assets: `pnpm run build` (runs `./scripts/copy-assets.sh`)

### Database Operations
- Run migrations: `uv run alembic upgrade head`
- Create new migration: `uv run alembic revision --autogenerate -m 'description'`
- Rollback migration: `uv run alembic downgrade -1`

### Testing
- Run tests: `uv run pytest`
- Run specific test: `uv run pytest tests/path/to/test_file.py::test_function`
- Test configuration is in `pytest.ini`

### Bot Components
- Run Discord/Twitch bots: `uv run bot/main.py`
- Bots are enabled via `BOT_DISCORD_ENABLED` and `BOT_TWITCH_ENABLED` environment variables

## Architecture Overview

YappR is a transcription and metadata search platform for YouTube and Twitch content built with:

### Core Components
- **Flask Application** (`app/main.py`): Main web server with FastAPI-style routing
- **Celery Workers**: Background task processing for transcription and audio processing
- **Bot System** (`bot/`): Discord and Twitch bots for community interaction
- **Database**: PostgreSQL with pgvector for semantic search, managed via Alembic migrations

### Key Directories
- `app/models/`: Database models, configuration, and core data structures
- `app/routes/`: HTTP route handlers organized by feature
- `app/services/`: Business logic and external API integrations
- `app/tasks/`: Celery background tasks
- `app/templates/`: Jinja2 HTML templates
- `app/static/`: Frontend assets (CSS, JS, images)
- `bot/`: Discord and Twitch bot implementations
- `tests/`: Test suite using pytest

### Authentication & Authorization
- Discord OAuth2 authentication via Flask-Dance
- Permission system with roles (admin, moderator, user)
- API key authentication for worker services
- Rate limiting for unauthenticated users

### Data Processing Pipeline
1. **Audio Extraction**: yt-dlp downloads audio from YouTube/Twitch
2. **Transcription**: WhisperX processes audio on GPU workers
3. **Storage**: Transcriptions stored in PostgreSQL with vector embeddings
4. **Search**: Full-text search via PostgreSQL tsvector + semantic search via pgvector

### Configuration
All configuration is centralized in `app/models/config.py` and loaded from environment variables. Key settings include API keys for YouTube/Twitch/Discord, database connections, transcription settings, and storage locations.

### External Dependencies
- **YouTube Data API**: Channel and video metadata
- **Twitch API**: Stream and video information
- **Discord API**: User authentication and bot functionality
- **Redis**: Caching and Celery message broker
- **WhisperX**: Audio transcription (requires NVIDIA GPU)

### Development Notes
- Frontend uses Bootstrap with HTMX for dynamic interactions
- WebSocket support via Flask-SocketIO for real-time updates
- Multi-worker architecture supports distributed transcription processing
- Docker Compose setup includes all necessary services (PostgreSQL, Redis, GPU workers)