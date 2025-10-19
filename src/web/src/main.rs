
#[cfg(feature = "ssr")]
#[tokio::main]
async fn main() {
    use axum::Router;
    use leptos::logging::log;
    use leptos::prelude::*;
    use leptos_axum::{generate_route_list, LeptosRoutes};
    use yappr_web::app::*;
    use yappr_shared::config::Config;
    use sea_orm::{Database, DatabaseConnection};
    use std::sync::Arc;

    // Initialize tracing
    tracing_subscriber::fmt::init();

    // Load configuration
    let config = Config::load();

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
        .leptos_routes(&leptos_options, routes, {
            let leptos_options = leptos_options.clone();
            move || shell(leptos_options.clone())
        })
        .fallback(leptos_axum::file_and_error_handler(shell))
        .with_state(leptos_options)
        .layer(axum::Extension(db));

    // run our app with hyper
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