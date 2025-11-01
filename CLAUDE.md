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
- `app/services/`: Business logic services for core application functionality
- `app/tasks/`: Celery background tasks
- `app/templates/`: Jinja2 HTML templates with Bootstrap styling
- `app/static/`: Frontend assets (CSS, JS, images)
- `bot/`: Discord and Twitch bot implementations
- `tests/`: Test suite using pytest

### Service Architecture (`app/services/`)
The application uses a service-oriented architecture with specialized services handling different domains:

- **broadcaster.py**: Manages broadcaster profiles, transcription statistics, and channel relationships
- **channel.py**: Handles channel operations, video fetching, linking, and management 
- **content_queue.py**: Manages the clip submission and review queue system with weight-based scoring
- **file_recovery.py**: Provides file recovery functionality for audio and metadata restoration
- **moderation.py**: Comprehensive moderation system with bans, timeouts, and permissions
- **platform.py**: Abstract platform services for YouTube and Twitch API integrations
- **transcription.py**: Handles transcription processing, parsing (VTT/JSON), and format conversion
- **user.py**: User management, permissions, role-based access control, and authentication
- **video.py**: Video operations, URL generation, timestamp linking, and platform-specific handling

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

### Frontend Design & Styling
The application features a modern, responsive design using:

- **Bootstrap 5**: Component-based CSS framework for consistent styling
- **HTMX**: Dynamic interactions without complex JavaScript
- **Card-based layouts**: Clean, organized information presentation
- **Accordion components**: Collapsible sections for content organization
- **Badge system**: Visual indicators for status, roles, and categories
- **Responsive grid**: Mobile-friendly layout with Bootstrap's grid system
- **Custom color scheme**: Platform-specific theming (Twitch purple, YouTube red)
- **Typography**: Clean, readable text with proper hierarchy
- **Interactive elements**: Hover effects, tooltips, and smooth transitions

Template structure follows standard Bootstrap patterns with semantic HTML and accessibility considerations.

## Rust/Leptos Web Application

The application is being migrated from Flask/Python to Leptos/Rust for improved performance and type safety. The Rust codebase is organized in `src/` with the following structure:

### Rust Project Structure
```
src/
├── shared/          # Shared library (business logic, services, entities)
│   ├── entities/    # SeaORM database entities (auto-generated from DB schema)
│   ├── services/    # Business logic services (broadcaster, channel, user, etc.)
│   ├── models/      # Domain models and DTOs
│   ├── external/    # External API clients (YouTube, Twitch, Discord)
│   └── config.rs    # Configuration management
├── web/             # Leptos web application
│   ├── src/
│   │   ├── components/     # UI components
│   │   ├── auth/          # Authentication and OAuth
│   │   ├── server_fns.rs  # Server functions (API endpoints)
│   │   ├── app.rs         # Main app with routes
│   │   └── main.rs        # Server entry point (Axum)
│   └── public/      # Static assets
└── wasm/            # WebAssembly modules
```

### Leptos Web Framework (`src/web/`)

**Technology Stack:**
- **Leptos 0.8**: Reactive web framework with server-side rendering
- **Axum**: HTTP server (backend)
- **SeaORM**: Database ORM with PostgreSQL
- **Tower Sessions**: Session management with PostgreSQL store
- **Axum-Login**: Authentication system
- **OpenID Connect**: OAuth2 authentication (Discord, Twitch)

**Development Commands:**
- Build web app: `cargo leptos build`
- Run dev server: `cargo leptos watch`
- Check compilation: `cargo check --features ssr`
- Working directory: `cd src/web`

### Component Organization Pattern

**Simple Features** (single component):
```rust
// src/web/src/components/feature_name.rs
#[component]
pub fn FeaturePage() -> impl IntoView { ... }
```

**Complex Features** (multiple components):
```
src/web/src/components/feature_name/
├── mod.rs              # Exports: pub use feature_page::FeaturePage;
├── feature_page.rs     # Main page component
├── feature_card.rs     # Card/list item component
└── feature_form.rs     # Form component (if needed)
```

**Component Best Practices:**
- Use signals for reactive state: `let (state, set_state) = signal(initial);`
- Use Resources for server data: `Resource::new(deps, async_fn)`
- Use Suspense for loading states
- Use `.into_any()` when branching view types
- Keep components focused and composable
- Match Bootstrap grid classes from original templates

**Example Component Structure:**
```rust
#[component]
pub fn BroadcasterPage() -> impl IntoView {
    let (search_term, set_search_term) = signal(String::new());

    let broadcasters = Resource::new(
        || (),
        |_| async move { get_broadcasters_with_auth().await },
    );

    view! {
        <div class="container py-4">
            <Suspense fallback=move || view! { /* loading spinner */ }>
                {move || Suspend::new(async move {
                    broadcasters.await.map(|data| {
                        // Render data
                    })
                })}
            </Suspense>
        </div>
    }
}
```

### Server Functions (`src/web/src/server_fns.rs`)

Server functions are the API layer between client and server, defined with the `#[server]` macro.

**Structure:**
1. **DTOs at top**: Serializable data transfer objects
2. **From implementations**: Convert entities to DTOs
3. **Server functions**: Annotated with `#[server(Name, "/api")]`

**Pattern for Server Functions:**
```rust
/// Serializable DTO
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FeatureData {
    pub id: i32,
    pub name: String,
}

#[cfg(feature = "ssr")]
impl From<entity::Model> for FeatureData {
    fn from(model: entity::Model) -> Self { ... }
}

/// Server function with authentication
#[server(GetFeatures, "/api")]
pub async fn get_features_with_auth() -> Result<Vec<FeatureData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;

    // Extract database connection
    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await?;

    // Extract authentication session
    let auth_session = extract::<crate::auth::AuthSession>().await?;

    // Load authorization context
    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await?
    } else {
        AuthContext::anonymous()
    };

    // Call service layer
    let data = FeatureService::get_all(&db).await?;

    // Filter based on permissions
    let filtered = auth_context.filter_visible_features(data);

    Ok(filtered.into_iter().map(FeatureData::from).collect())
}
```

**Key Principles:**
- Always extract DB from `Extension<Arc<DatabaseConnection>>`
- Use `AuthSession` for authenticated endpoints
- Load `AuthContext` for permission checks
- Call service layer (from `yappr_shared::services`)
- Return serializable DTOs, never database entities
- Filter sensitive data server-side, not client-side

### Authorization Pattern

**Authorization System** (`yappr_shared::services::authorization`):
```rust
// Load user's authorization context
let auth_context = AuthContext::load(&db, user).await?;

// Check permissions
if auth_context.is_admin() { ... }
if auth_context.is_moderator() { ... }
if auth_context.has_channel_role(channel_id, &ChannelRole::Mod) { ... }

// Filter data based on visibility
let visible = auth_context.filter_visible_broadcasters(all_broadcasters);

// Require specific permissions
auth_context.require_admin()?;
auth_context.require_channel_role(channel_id, &ChannelRole::Owner)?;
```

**Security Rules:**
1. **Never trust client-side filtering** - always filter on server
2. **Check permissions in server functions** - not in components
3. **Use AuthContext** - provides consistent authorization logic
4. **Filter by ban status** - exclude content from banned channels
5. **Verify active status** - check user is not banned/disabled

### Flask to Leptos Migration Pattern

When migrating a Flask page to Leptos, follow this workflow:

**1. Analyze Flask Route** (`app/routes/*.py`)
- Identify the route handler
- Note authentication/permission requirements
- Identify data fetching logic
- Review template structure

**2. Check Service Layer** (`src/shared/src/services/*.rs`)
- Verify service exists in Rust (or port from Python)
- Ensure all needed queries are available
- Add new service methods if needed

**3. Create Components** (`src/web/src/components/`)
- Create directory structure (simple vs complex)
- Implement page component with Resource
- Implement sub-components (cards, forms)
- Match Bootstrap classes from original template
- Preserve responsive grid layouts

**4. Add Server Function** (`src/web/src/server_fns.rs`)
- Define DTO for data transfer
- Implement From trait to convert entities
- Create server function with `#[server]` macro
- Extract database and auth session
- Call service layer
- Filter based on permissions
- Return DTOs

**5. Register Component** (`src/web/src/components/mod.rs`)
```rust
pub mod feature_name;  // or pub mod feature_name { ... }
```

**6. Add Route** (`src/web/src/app.rs`)
```rust
use crate::components::feature::FeaturePage;

// In Routes:
<Route path=StaticSegment("feature") view=FeaturePage/>
```

**7. Test Compilation**
```bash
cd src/web
cargo check --features ssr
cargo leptos watch  # For full dev server
```

**Migration Checklist:**
- [ ] Service layer methods ported to Rust
- [ ] DTOs defined in server_fns.rs
- [ ] Server function with authentication
- [ ] Permission filtering implemented
- [ ] Ban status filtering (if applicable)
- [ ] Component structure matches original
- [ ] Bootstrap classes preserved
- [ ] Responsive grid layout maintained
- [ ] Loading states with Suspense
- [ ] Empty states handled
- [ ] Error states handled
- [ ] Route registered in app.rs
- [ ] Compilation successful

**Completed Migrations:**
- `/channels` - Channel listing with platform filtering
- `/search` - Video search with transcription results
- `/broadcasters` - Broadcaster listing with search and permission filtering
- `/login` - OAuth authentication (Discord, Twitch)

### Shared Services (`src/shared/src/services/`)

The service layer contains all business logic and is shared between web app and other components:

- **authorization.rs**: AuthContext, permission checking, role-based access control
- **broadcaster.rs**: Broadcaster CRUD operations (simple, no auth)
- **channel.rs**: Channel operations, video fetching, platform integration
- **content.rs**: Content management
- **content_queue.rs**: Clip queue management
- **content_submission.rs**: Submission handling
- **moderation.rs**: Ban/timeout operations, moderation actions
- **search.rs**: Transcription search (ported from Python)
- **segment.rs**: Segment operations
- **transcription.rs**: Transcription processing
- **user.rs**: User management
- **video.rs**: Video operations

**Service Conventions:**
- Services are stateless structs with associated functions
- All methods take `&DatabaseConnection` as first parameter
- Use `#[instrument]` for tracing
- Return `Result<T, DbErr>` for database operations
- Use custom error types when needed (e.g., `AuthError`)

### Development Notes
- Multi-worker architecture supports distributed transcription processing  
- Docker Compose setup includes all necessary services (PostgreSQL, Redis, GPU workers)
- Search optimization focused on pure Python performance - avoided JIT compilation (Numba) due to type conversion overhead
- Service layer provides clean separation between business logic and web routes
- when writing log lines, use 'extra' argument instead of f-strings
- When using Optional types, use Type | None instead of Optional[Type]