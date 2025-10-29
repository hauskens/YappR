
#[cfg(feature = "ssr")]
#[tokio::main]
async fn main() {
    use axum::{Router, extract::{Path, Extension}, response::Response, http::{StatusCode, header}};
    use leptos::logging::log;
    use leptos::prelude::*;
    use leptos::serde_json::Value;
    use leptos_axum::{generate_route_list, LeptosRoutes};
    use yappr_web::app::*;
    use yappr_shared::config::Config;
    use yappr_shared::entities::prelude::*;
    use sea_orm::{Database, DatabaseConnection, EntityTrait};
    use std::sync::Arc;
    use std::path::PathBuf;

    // Handler for thumbnail endpoint
    async fn serve_thumbnail(
        Path(video_id): Path<i32>,
        Extension(db): Extension<Arc<DatabaseConnection>>,
        Extension(config): Extension<Arc<Config>>,
    ) -> Result<Response, StatusCode> {
        // Get video from database
        let video = Video::find_by_id(video_id)
            .one(db.as_ref())
            .await
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
            .ok_or(StatusCode::NOT_FOUND)?;

        // Check if thumbnail exists
        let thumbnail_json = video.thumbnail.ok_or(StatusCode::NOT_FOUND)?;

        // Parse thumbnail JSON to get filename
        let thumbnail_data: Value = leptos::serde_json::from_value(thumbnail_json.clone())
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

        // sqlalchemy_file stores the filename in the "filename" or "name" field
        let filename = thumbnail_data
            .get("filename")
            .or_else(|| thumbnail_data.get("name"))
            .and_then(|v| v.as_str())
            .ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;

        // Build full path to thumbnail
        let thumbnail_path = PathBuf::from(&config.storage_location)
            .join("thumbnails")
            .join(filename);

        // Read thumbnail file
        let content = tokio::fs::read(&thumbnail_path)
            .await
            .map_err(|_| StatusCode::NOT_FOUND)?;

        // Build response with caching headers
        Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, "image/jpeg")
            .header(header::CACHE_CONTROL, "public, max-age=31536000, immutable")
            .body(axum::body::Body::from(content))
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)
    }

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

    let conf = get_configuration(None).unwrap();
    let addr = conf.leptos_options.site_addr;
    let leptos_options = conf.leptos_options;

    // Generate the list of routes in your Leptos App
    let routes = generate_route_list(App);

    // Create app state with database connection
    let db = Arc::new(db);

    let app = Router::new()
        .route("/api/thumbnails/{video_id}", axum::routing::get(serve_thumbnail))
        .leptos_routes(&leptos_options, routes, {
            let leptos_options = leptos_options.clone();
            move || shell(leptos_options.clone())
        })
        .fallback(leptos_axum::file_and_error_handler(shell))
        .with_state(leptos_options)
        .layer(axum::Extension(db))
        .layer(axum::Extension(config));

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