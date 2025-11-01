use leptos::prelude::*;
use leptos::server_fn::ServerFnError;

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
pub struct UserInfo {
    pub id: i32,
    pub name: String,
    pub avatar_url: Option<String>,
}

// Server functions for auth operations
#[server]
pub async fn logout_user() -> Result<(), ServerFnError> {
    use crate::auth::AuthSession;
    use leptos_axum::extract;

    let mut auth: AuthSession = extract().await?;

    auth.logout().await
        .map_err(|e| ServerFnError::new(format!("Logout error: {:?}", e)))?;

    Ok(())
}

#[server]
pub async fn get_current_user() -> Result<Option<UserInfo>, ServerFnError> {
    use crate::auth::AuthSession;
    use leptos_axum::extract;

    let auth: AuthSession = extract().await?;

    Ok(auth.user.map(|u| UserInfo {
        id: u.0.id,
        name: u.0.name.clone(),
        avatar_url: u.0.avatar_url.clone(),
    }))
}

#[server]
pub async fn get_protected_content() -> Result<String, ServerFnError> {
    use crate::auth::AuthSession;
    use leptos_axum::extract;

    let auth: AuthSession = extract().await?;

    match auth.user {
        Some(user) => Ok(format!("Hello, {}! This is a protected route.", user.0.name)),
        None => Err(ServerFnError::new("Unauthorized")),
    }
}

#[component]
pub fn LoginPage() -> impl IntoView {
    let message = RwSignal::new(String::new());
    let trigger_reload = RwSignal::new(0);

    // Use a resource to fetch current user (handles SSR properly)
    let current_user_resource = Resource::new(
        move || trigger_reload.get(),
        |_| async move {
            get_current_user().await.ok().flatten()
        }
    );

    // Action for logout (handle async properly without spawn_local)
    let logout_action = Action::new(move |_: &()| async move {
        match logout_user().await {
            Ok(_) => {
                message.set("Logged out successfully".to_string());
                trigger_reload.update(|n| *n += 1);
                Ok(())
            }
            Err(e) => {
                message.set(format!("Logout error: {:?}", e));
                Err("Logout error")
            }
        }
    });

    let on_logout = move |_| {
        logout_action.dispatch(());
    };

    view! {
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h3 class="mb-0">"Login Demo"</h3>
                        </div>
                        <div class="card-body">
                            <Suspense fallback=move || view! {
                                <div class="d-flex justify-content-center">
                                    <div class="spinner-border" role="status">
                                        <span class="visually-hidden">"Loading..."</span>
                                    </div>
                                </div>
                            }>
                                {move || match current_user_resource.get().flatten() {
                                    Some(user) => view! {
                                    <div>
                                        <div class="alert alert-success">
                                            <h4>"Welcome, " {user.name.clone()} "!"</h4>
                                            <p>"You are currently logged in."</p>
                                            {user.avatar_url.clone().map(|avatar| view! {
                                                <img src={avatar} alt="Avatar" class="rounded-circle" width="64" height="64"/>
                                            })}
                                        </div>
                                        <button
                                            type="button"
                                            class="btn btn-danger"
                                            on:click=on_logout
                                        >
                                            "Logout"
                                        </button>
                                        <a href="/protected" class="btn btn-primary ms-2">"Visit Protected Page"</a>
                                    </div>
                                }.into_any(),
                                None => view! {
                                    <div>
                                        <div class="alert alert-info mb-4">
                                            <p class="mb-0">"Choose a login method to continue"</p>
                                        </div>

                                        <div class="d-grid gap-3">
                                            <a
                                                href="/auth/discord"
                                                rel="external"
                                                class="btn btn-lg d-flex align-items-center justify-content-center gap-2"
                                                style="background-color: #5865F2; color: white;"
                                            >
                                                <i class="bi bi-discord"></i>
                                                "Login with Discord"
                                            </a>

                                            <a
                                                href="/auth/twitch"
                                                rel="external"
                                                class="btn btn-lg d-flex align-items-center justify-content-center gap-2"
                                                style="background-color: #9146FF; color: white;"
                                            >
                                                <i class="bi bi-twitch"></i>
                                                "Login with Twitch"
                                            </a>
                                        </div>
                                    </div>
                                }.into_any()
                                }}
                            </Suspense>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    }
}

#[component]
pub fn ProtectedPage() -> impl IntoView {
    // Use a resource to fetch protected content (handles SSR properly)
    let protected_resource = Resource::new(|| (), |_| async move {
        get_protected_content().await
    });

    view! {
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header">
                            <h3 class="mb-0">"Protected Page"</h3>
                        </div>
                        <div class="card-body">
                            <Suspense fallback=move || view! {
                                <div class="spinner-border" role="status">
                                    <span class="visually-hidden">"Loading..."</span>
                                </div>
                            }>
                                {move || match protected_resource.get() {
                                    Some(Ok(text)) => view! {
                                        <div class="alert alert-success">
                                            <i class="bi bi-check-circle me-2"></i>
                                            {text}
                                        </div>
                                    }.into_any(),
                                    Some(Err(err)) => view! {
                                        <div class="alert alert-danger">
                                            <i class="bi bi-x-circle me-2"></i>
                                            {format!("Error: {:?}", err)}
                                            <hr/>
                                            <p class="mb-0">
                                                <a href="/login" class="alert-link">"Please login first"</a>
                                            </p>
                                        </div>
                                    }.into_any(),
                                    None => view! {
                                        <div class="spinner-border" role="status">
                                            <span class="visually-hidden">"Loading..."</span>
                                        </div>
                                    }.into_any()
                                }}
                            </Suspense>
                            <a href="/login" class="btn btn-secondary">"Back to Login"</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    }
}
