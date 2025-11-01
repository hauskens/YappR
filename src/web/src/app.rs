use leptos::prelude::*;
use leptos_meta::{provide_meta_context, MetaTags, Script, Stylesheet, Title};
use leptos_router::{
    components::{Route, Router, Routes},
    StaticSegment,
};
use leptos::server_fn::ServerFnError;
use leptos::task::spawn_local;
use crate::components::channel::ChannelsPage;
use crate::components::dark_mode_toggle::DarkModeToggle;
use crate::components::search::search_page::SearchPage;
use crate::components::login::{LoginPage, ProtectedPage};

pub fn shell(options: LeptosOptions) -> impl IntoView {
    view! {
        <!DOCTYPE html>
        <html lang="en">
            <head>
                <meta charset="utf-8"/>
                <meta name="viewport" content="width=device-width, initial-scale=1"/>
                <meta property="og:title" content="YappR"/>
                <meta property="og:description" content="Stream content search - Find specific moments and get timestamped links to VODs"/>
                <meta property="og:url" content="https://yappr.app"/>
                <meta property="og:type" content="website"/>
                <script>
                    "(function(){try{var theme=localStorage.getItem('theme');if(theme){document.documentElement.setAttribute('data-bs-theme',theme);}}catch(e){}})()"
                </script>
                <AutoReload options=options.clone() />
                <HydrationScripts options/>
                <MetaTags/>
            </head>
            <body>
                <App/>
            </body>
        </html>
    }
}

#[server]
pub async fn get_platform_video_by_ids(id: String) -> Result<String, ServerFnError> {
    let mut id = id;
    id.insert(0, 't');
    Ok(id)
}

#[component]
pub fn App() -> impl IntoView {
    // Provides context that manages stylesheets, titles, meta tags, etc.
    provide_meta_context();

    // Use a local resource to track current user for navbar (loads only on client)
    let current_user_resource = LocalResource::new(|| async move {
        use crate::components::login::get_current_user;
        get_current_user().await.ok().flatten()
    });

    view! {
        <Stylesheet id="bootstrap" href="/vendor/bootstrap/bootstrap.min.css"/>
        <Stylesheet id="bootstrap-icons" href="/vendor/bootstrap-icons/bootstrap-icons.min.css"/>
        <Stylesheet id="leptos" href="/pkg/yappr-web.css"/>
        <Script src="/vendor/bootstrap/bootstrap.bundle.min.js"/>
        <Title text="YappR"/>
        <Router>
            <main class="d-flex flex-column min-vh-100">
                <nav class="navbar navbar-expand-sm bg-body-tertiary sticky-top py-1">
                    <div class="container-fluid">
                        <a class="navbar-brand" href="/">
                            <img src="/logo_48.ico" alt="YappR" width="48" height="48" style="margin-right: 5px;"/>
                            "YappR"
                        </a>

                        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarScroll" aria-controls="navbarScroll" aria-expanded="false" aria-label="Toggle navigation">
                            <span class="navbar-toggler-icon"></span>
                        </button>

                        <div class="collapse navbar-collapse" id="navbarScroll">
                            <div class="navbar-nav me-auto flex-grow-1">
                                // Search Dropdown
                                <div class="nav-item dropdown">
                                    <a class="nav-link dropdown-toggle" href="#" id="searchDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                        "Search"
                                    </a>
                                    <ul class="dropdown-menu" aria-labelledby="searchDropdown">
                                        <li><a class="dropdown-item" href="/search">"Video Search"</a></li>
                                        <li><a class="dropdown-item" href="/chatlog-search">"Chatlog Search"</a></li>
                                    </ul>
                                </div>

                                // Clip Queue Dropdown
                                <div class="nav-item dropdown">
                                    <a class="nav-link dropdown-toggle" href="#" id="queueDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                        "Clip Queue"
                                    </a>
                                    <ul class="dropdown-menu" aria-labelledby="queueDropdown">
                                        <li><a class="dropdown-item" href="/clip-queue">"Clip Queue(beta)"</a></li>
                                        <li><a class="dropdown-item" href="/suggest-content">"Suggest Content"</a></li>
                                    </ul>
                                </div>

                                // Channels link (replacing Home)
                                <a class="nav-link" href="/channels">"Channels"</a>

                                // Broadcasters link
                                <a class="nav-link" href="/broadcasters">"Broadcasters"</a>

                                // Leaderboard link
                                <a class="nav-link" href="/leaderboard">"Leaderboard"</a>

                                // Management Dropdown (for admin/mod users - showing for now)
                                <div class="nav-item dropdown">
                                    <a class="nav-link dropdown-toggle" href="#" id="managementDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                                        "Management"
                                    </a>
                                    <ul class="dropdown-menu" aria-labelledby="managementDropdown">
                                        <li><a class="dropdown-item" href="/management">"Management"</a></li>
                                        <li><a class="dropdown-item" href="/users">"Users"</a></li>
                                        <li><a class="dropdown-item" href="/workers">"Workers"</a></li>
                                        <li><a class="dropdown-item" href="/utils">"Utils"</a></li>
                                    </ul>
                                </div>

                                // About link
                                <a class="nav-link" href="/about">"About"</a>
                            </div>

                            <div class="d-flex align-items-center">
                                <div class="form-check form-switch me-2">
                                    <DarkModeToggle/>
                                </div>
                                <div class="vr"></div>
                                <div class="ms-2">
                                    {move || match current_user_resource.get().flatten() {
                                        Some(user) => view! {
                                            <div class="d-flex align-items-center gap-2">
                                                {user.avatar_url.clone().map(|avatar| view! {
                                                    <img src={avatar} alt="Avatar" class="rounded-circle" width="32" height="32"/>
                                                })}
                                                <span class="text-body">{user.name.clone()}</span>
                                                <a href="/login" class="btn btn-secondary btn-sm">
                                                    "Manage"
                                                </a>
                                            </div>
                                        }.into_any(),
                                        None => view! {
                                            <a href="/login" class="btn btn-primary btn-sm">
                                                <i class="bi bi-box-arrow-in-right me-1"></i>
                                                "Login"
                                            </a>
                                        }.into_any()
                                    }}
                                </div>
                            </div>
                        </div>
                    </div>
                </nav>
                <Routes fallback=|| "Page not found.".into_view()>
                    <Route path=StaticSegment("") view=HomePage/>
                    <Route path=StaticSegment("channels") view=ChannelsPage/>
                    <Route path=StaticSegment("search") view=SearchPage/>
                    <Route path=StaticSegment("login") view=LoginPage/>
                    <Route path=StaticSegment("protected") view=ProtectedPage/>
                </Routes>

                <footer class="footer mt-auto text-center text-white bg-body-tertiary w-100 p-2">
                    <div class="d-flex justify-content-between align-items-center text-body-secondary fs-6">
                        <div></div>
                        <div class="d-flex align-items-center gap-2">
                            <span class="d-flex align-items-center">"Made by Hausken"</span>
                            <span>
                                <a class="github-button" href="https://github.com/hauskens/YappR"
                                   data-color-scheme="no-preference: light; light: light; dark: light;"
                                   data-show-count="true"
                                   data-icon="octicon-star"
                                   aria-label="Star hauskens/YappR on GitHub">
                                   "GitHub"
                                </a>
                            </span>
                        </div>
                        <a href="/about" class="text-muted small">"v0.1.0"</a>
                    </div>
                </footer>
            </main>
        </Router>
    }
}

/// Renders the home page of your application.
#[component]
fn HomePage() -> impl IntoView {
    // Creates a reactive value to update the button
    let count = RwSignal::new(0);
    let (count2, set_count2) = signal(0);
    let on_click = move |_| *count.write() += 1;

    view! {
        <h1>"Welcome to Lepts!"</h1>
        <button on:click=on_click>"Click Me: " {count}</button>
        <button 
            class:red=move || {count2.get() > 5}
            on:click=move |_| {set_count2.set(count2.get() + 1)}
        >"Click Me Double: " {count2}</button>
        <progress
            max="50"
            // signals are functions, so `value=count` and `value=move || count.get()`
            // are interchangeable.
            value=move || count2.get() * 2
        />
        <button on:click=move |_| {
            spawn_local(async move {
                match get_platform_video_by_ids("test".to_string()).await {
                    Ok(result) => {
                        leptos::logging::log!("Server function result: {}", result);
                    }
                    Err(e) => {
                        leptos::logging::error!("Server function error: {:?}", e);
                    }
                }
            });
        }>
            "Clickius: " {count2}
        </button>

    }
}
