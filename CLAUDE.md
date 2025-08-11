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
- Run unit tests only: `uv run pytest --unit` (skips database setup)
- Run search performance tests: `uv run pytest tests/app/test_search_performance.py --unit -v -s`
- Run performance tests via devenv: `devenv test`
- Test configuration is in `pytest.ini`

### Bot Components
- Run Discord/Twitch bots: `uv run bot/main.py`
- Bots are enabled via `BOT_DISCORD_ENABLED` and `BOT_TWITCH_ENABLED` environment variables

### WebAssembly Module
- Build WebAssembly module: `wasm-pack build --target web`
- Build for bundler: `wasm-pack build --target bundler`
- Output directory: `pkg/` (contains generated JS bindings and WASM file)

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

### Search System Performance
The search functionality (`app/search.py`) has been optimized for high performance:

- **Core Search Function**: `search_v2()` handles both regular and strict (quoted) search queries
- **Optimized Algorithms**: Uses set-based word matching (O(1) lookups) and sliding window for consecutive word search
- **Adjacent Segment Logic**: Automatically includes neighboring segments when search terms appear at segment boundaries
- **Performance**: Processes ~0.03ms per segment (small datasets), ~0.37ms per segment (large datasets)
- **Scalability**: Sub-linear scaling - performance per result improves with larger result sets
- **Search Types**:
  - Regular search: Finds segments containing all search words (any order)
  - Strict search: Finds exact phrase matches using quoted terms (`"hello world"`)

Performance testing suite available in `tests/app/test_search_performance.py` with benchmarks for different dataset sizes.

### Development Notes
- Frontend uses Bootstrap with HTMX for dynamic interactions
- WebSocket support via Flask-SocketIO for real-time updates
- Multi-worker architecture supports distributed transcription processing
- Docker Compose setup includes all necessary services (PostgreSQL, Redis, GPU workers)
- Search optimization focused on pure Python performance - avoided JIT compilation (Numba) due to type conversion overhead