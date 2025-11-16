
# yappr-web (Frontend/Web Service)

**Purpose**: Full-stack web application with SSR (Server-Side Rendering), hydration, and Leptos components.

**Configuration**:
- **Crate Type**: `cdylib` (WASM) + `rlib` (Rust library)
- **Features**:
  - `ssr`: Server-side rendering with Axum (default)
  - `hydrate`: Client-side hydration via WASM

**Architecture**:

```
src/
  main.rs          # Axum server setup, routes, middleware (SSR only)
  lib.rs           # Leptos hydration entry point
  app.rs           # Leptos component tree, routing
  routes.rs        # Custom Axum routes (thumbnails, etc.)
  auth/            # OAuth2 authentication (SSR only)
    - oauth_clients.rs (Discord, Twitch providers)
    - oauth_handlers.rs (OAuth flow)
    - oauth_state.rs (CSRF protection state)
    - auth.rs (Backend, session management)
  components/      # Reusable Leptos components
    - broadcaster/ (Broadcaster page, edit page)
    - search/      (Search UI, full-text search)
    - video/       (Video page)
    - channel.rs, channel_videos.rs
    - login.rs (Protected routes, login page)
  server_fns/      # Server functions (RPC-like calls)
    - broadcasters.rs, search.rs, video.rs
    - types.rs (Shared types with frontend)
```

**Key Technologies**:

1. **Leptos Framework** (v0.8):
   - Full-stack, isomorphic Rust framework
   - Server-Side Rendering (SSR) mode for initial page load
   - Client-side hydration for interactivity
   - Reactive signals and components
   - Meta management (titles, OG tags)

2. **Axum Web Framework** (v0.8):
   - Async, modular web framework
   - Tower middleware support
   - Handler extractors for dependency injection
   - API routes for non-Leptos endpoints (thumbnails, OAuth callbacks)

3. **Authentication**:
   - **OAuth2**: Discord and Twitch providers
   - **Session Management**: Tower-Sessions with PostgreSQL store
   - **Session Duration**: 30 days inactivity expiry
   - **Cookies**: SameSite=Lax, secure in production
   - **CSRF Protection**: OAuth state parameter + session cookies
   - **Authorization**: RBAC via `authorization.rs` service

4. **Server Functions**:
   - Leptos server functions for RPC-like backend calls
   - Serialization: Serde + Serde JSON
   - Authorization checks on each function

5. **Frontend Assets**:
   - **CSS**: SCSS (Bootstrap, Bootswatch themes)
   - **Icons**: Feather Icons
   - **Dark Mode**: LocalStorage-based theme toggle
   - **Charts**: leptos-chartistry

**Main Startup Flow** (`main.rs`):
1. Load config (env vars)
2. Initialize tracing/logging
3. Connect to PostgreSQL database
4. Set up session store with PostgreSQL
5. Create auth layer with Backend
6. Register Axum routes (API, OAuth, Leptos routes)
7. Listen on configured host:porto


### OAuth2 Flow (Web Service)

1. **Login Page**: User clicks "Login with Discord" or "Login with Twitch"
2. **OAuth Initiation** (`/auth/discord`, `/auth/twitch`):
   - Generate random state parameter (CSRF protection)
   - Store state in memory via `OAuthState` manager
   - Redirect to provider's OAuth endpoint
3. **OAuth Callback** (`/auth/discord/callback`, `/auth/twitch/callback`):
   - Verify state parameter matches
   - Exchange authorization code for access token
   - Fetch user profile from provider
   - Create/update User in database
   - Set session cookie via tower-sessions
4. **Protected Routes**:
   - Axum layer checks session cookie
   - Injects `AuthSession` (user info)
   - `#[require_login]` or manual checks