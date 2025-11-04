#[cfg(feature = "ssr")]
use axum::http::StatusCode;
#[cfg(feature = "ssr")]
use yappr_web::auth::AuthSession;

#[cfg(feature = "ssr")]
async fn handle_logout(
    mut auth: AuthSession,
) -> Result<axum::response::Json<LogoutResponse>, StatusCode> {
    if auth.logout().await.is_err() {
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }

    Ok(axum::response::Json(LogoutResponse {
        success: true,
        message: "Logout successful".to_string(),
    }))
}

#[cfg(feature = "ssr")]
async fn handle_current_user(auth: AuthSession) -> axum::response::Json<Option<UserInfo>> {
    let user = auth.user;
    axum::response::Json(user.map(|u| UserInfo {
        id: u.0.id,
        name: u.0.name.clone(),
        avatar_url: u.0.avatar_url.clone(),
    }))
}

#[cfg(feature = "ssr")]
async fn protected_route(auth: AuthSession) -> Result<String, StatusCode> {
    match auth.user {
        Some(user) => Ok(format!(
            "Hello, {}! This is a protected route.",
            user.0.name
        )),
        None => Err(StatusCode::UNAUTHORIZED),
    }
}

#[cfg(feature = "ssr")]
#[derive(serde::Serialize)]
struct LogoutResponse {
    success: bool,
    message: String,
}

#[cfg(feature = "ssr")]
#[derive(serde::Serialize, Clone)]
struct UserInfo {
    id: i32,
    name: String,
    avatar_url: Option<String>,
}

#[cfg(feature = "ssr")]
async fn handle_discord_callback(
    query: axum::extract::Query<yappr_web::auth::oauth_handlers::CallbackParams>,
    config: axum::Extension<std::sync::Arc<yappr_shared::config::Config>>,
    oauth_state: axum::Extension<yappr_web::auth::oauth_state::OAuthState>,
    auth_session: yappr_web::auth::AuthSession,
) -> Result<impl axum::response::IntoResponse, axum::http::StatusCode> {
    yappr_web::auth::oauth_handlers::handle_oauth_callback(
        yappr_web::auth::oauth_clients::OAuthProvider::Discord,
        query,
        config,
        oauth_state,
        auth_session,
    )
    .await
}

#[cfg(feature = "ssr")]
async fn handle_twitch_callback(
    query: axum::extract::Query<yappr_web::auth::oauth_handlers::CallbackParams>,
    config: axum::Extension<std::sync::Arc<yappr_shared::config::Config>>,
    oauth_state: axum::Extension<yappr_web::auth::oauth_state::OAuthState>,
    auth_session: yappr_web::auth::AuthSession,
) -> Result<impl axum::response::IntoResponse, axum::http::StatusCode> {
    yappr_web::auth::oauth_handlers::handle_oauth_callback(
        yappr_web::auth::oauth_clients::OAuthProvider::Twitch,
        query,
        config,
        oauth_state,
        auth_session,
    )
    .await
}

#[cfg(feature = "ssr")]
#[tokio::main]
async fn main() {
    use axum::{Router, http::header};
    use axum_login::AuthManagerLayerBuilder;
    use leptos::logging::log;
    use leptos::prelude::*;
    use leptos_axum::{LeptosRoutes, generate_route_list};
    use sea_orm::{Database, DatabaseConnection};
    use std::{net::SocketAddr, sync::Arc};
    use tower_http::set_header::SetResponseHeaderLayer;
    use tower_sessions::{Expiry, SessionManagerLayer};
    use tower_sessions_sqlx_store::{PostgresStore, sqlx::PgPool};
    use yappr_shared::config::Config;
    use yappr_web::app::*;
    use yappr_web::auth::Backend;
    use yappr_web::auth::oauth_clients::OAuthProvider;
    use yappr_web::auth::oauth_handlers::handle_oauth_login;
    use yappr_web::auth::oauth_state::OAuthState;
    use yappr_web::routes;

    // CSRF Protection is provided by:
    // 1. OAuth state parameter for authentication flow (see oauth_handlers.rs)
    // 2. SameSite=Lax session cookies (prevents cross-site requests)
    // 3. HTTPS-only cookies in production (prevents MITM)

    // Initialize tracing
    tracing_subscriber::fmt::init();

    // Load configuration
    let config = Config::load();
    let config = Arc::new(config);

    // Create database connection
    log!("Connecting to database...");
    let db: DatabaseConnection = Database::connect(&config.database.url)
        .await
        .expect("Failed to connect to database");
    log!("Database connected successfully!");

    // Set up session store using PostgreSQL
    log!("Setting up session store...");
    let pool = PgPool::connect(&config.database.url)
        .await
        .expect("Failed to connect to database for session store");
    let session_store = PostgresStore::new(pool);
    session_store
        .migrate()
        .await
        .expect("Failed to run session store migrations");

    // Session layer with 7 day expiry and secure cookie settings
    let session_layer = SessionManagerLayer::new(session_store)
        .with_expiry(Expiry::OnInactivity(time::Duration::days(30)))
        .with_http_only(config.debug)
        .with_same_site(tower_sessions::cookie::SameSite::Lax)
        .with_secure(!config.debug); // Use secure cookies in production only

    // Create app state with database connection
    let db = Arc::new(db);

    // Auth backend
    let backend = Backend::new(db.clone(), config.session_secret.clone());
    let auth_layer = AuthManagerLayerBuilder::new(backend, session_layer).build();

    // OAuth state manager
    let oauth_state = OAuthState::new();

    let mut conf = get_configuration(None).unwrap();
    let addr = SocketAddr::new(config.server_host, config.server_port);
    conf.leptos_options.site_addr = addr;
    let leptos_options = conf.leptos_options;

    // Generate the list of routes in your Leptos App
    let routes = generate_route_list(App);

    log!("Registering thumbnail route: /api/thumbnails/{{video_id}}");

    let mut app = Router::new()
        .route(
            "/api/thumbnails/{video_id}",
            axum::routing::get(routes::serve_thumbnail),
        )
        .route("/api/logout", axum::routing::post(handle_logout))
        .route("/api/current-user", axum::routing::get(handle_current_user))
        .route("/api/protected", axum::routing::get(protected_route))
        // OAuth routes
        .route(
            "/auth/discord",
            axum::routing::get(
                |config: axum::Extension<Arc<Config>>, oauth_state: axum::Extension<OAuthState>| {
                    handle_oauth_login(OAuthProvider::Discord, config, oauth_state)
                },
            ),
        )
        .route(
            "/auth/discord/callback",
            axum::routing::get(handle_discord_callback),
        )
        .route(
            "/auth/twitch",
            axum::routing::get(
                |config: axum::Extension<Arc<Config>>, oauth_state: axum::Extension<OAuthState>| {
                    handle_oauth_login(OAuthProvider::Twitch, config, oauth_state)
                },
            ),
        )
        .route(
            "/auth/twitch/callback",
            axum::routing::get(handle_twitch_callback),
        )
        .leptos_routes(&leptos_options, routes, {
            let leptos_options = leptos_options.clone();
            move || shell(leptos_options.clone())
        })
        .fallback(leptos_axum::file_and_error_handler(shell))
        .with_state(leptos_options)
        .layer(axum::Extension(db))
        .layer(axum::Extension(oauth_state))
        .layer(auth_layer);

    // Add HSTS header in production only
    if !config.debug {
        app = app.layer(SetResponseHeaderLayer::if_not_present(
            header::STRICT_TRANSPORT_SECURITY,
            header::HeaderValue::from_static("max-age=31536000; includeSubDomains"),
        ));
    }

    // Add config extension after HSTS middleware
    let app = app.layer(axum::Extension(config));

    log!("listening on http://{}", &addr);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app.into_make_service())
        .await
        .unwrap();
}

#[cfg(not(feature = "ssr"))]
pub fn main() {
    // no client-side main function
    // unless we want this to work with e.g., Trunk for pure client-side testing
    // see lib.rs for hydration function instead
}
