use leptos::prelude::*;
use leptos::web_sys;
use leptos::server_fn::ServerFnError;

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
pub struct UserInfo {
    pub id: i32,
    pub name: String,
    pub avatar_url: Option<String>,
}

// Server functions for auth operations
#[server]
pub async fn login_user(username: String) -> Result<Option<UserInfo>, ServerFnError> {
    use crate::auth::AuthSession;
    use leptos_axum::extract;

    let mut auth: AuthSession = extract().await?;

    let creds = crate::auth::Credentials { username };
    let user = auth.authenticate(creds).await
        .map_err(|e| ServerFnError::new(format!("Auth error: {:?}", e)))?;

    if let Some(user) = user {
        auth.login(&user).await
            .map_err(|e| ServerFnError::new(format!("Login error: {:?}", e)))?;

        Ok(Some(UserInfo {
            id: user.0.id,
            name: user.0.name.clone(),
            avatar_url: user.0.avatar_url.clone(),
        }))
    } else {
        Ok(None)
    }
}

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
    let username = RwSignal::new(String::new());
    let message = RwSignal::new(String::new());
    let trigger_reload = RwSignal::new(0);

    // Use a resource to fetch current user (handles SSR properly)
    let current_user_resource = Resource::new(
        move || trigger_reload.get(),
        |_| async move {
            get_current_user().await.ok().flatten()
        }
    );

    // Actions for login/logout (handle async properly without spawn_local)
    let login_action = Action::new(move |username: &String| {
        let username = username.clone();
        async move {
            match login_user(username).await {
                Ok(Some(user)) => {
                    message.set("Login successful".to_string());
                    trigger_reload.update(|n| *n += 1);
                    Ok(user)
                }
                Ok(None) => {
                    message.set("User not found".to_string());
                    Err("User not found")
                }
                Err(e) => {
                    message.set(format!("Error: {:?}", e));
                    Err("Login error")
                }
            }
        }
    });

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

    let on_submit = move |ev: web_sys::SubmitEvent| {
        ev.prevent_default();
        login_action.dispatch(username.get());
    };

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

                                        // Keep demo login as fallback for development
                                        <details class="mt-4">
                                            <summary class="text-muted small" style="cursor: pointer;">"Demo Login (Development)"</summary>
                                            <form on:submit=on_submit class="mt-3">
                                                <div class="mb-3">
                                                    <label for="username" class="form-label">"Username"</label>
                                                    <input
                                                        type="text"
                                                        class="form-control"
                                                        id="username"
                                                        placeholder="Enter username"
                                                        on:input=move |ev| {
                                                            username.set(event_target_value(&ev));
                                                        }
                                                        prop:value=move || username.get()
                                                    />
                                                </div>
                                                <button type="submit" class="btn btn-sm btn-secondary">
                                                    "Demo Login"
                                                </button>
                                            </form>
                                        </details>

                                        {move || {
                                            let msg = message.get();
                                            if !msg.is_empty() {
                                                view! {
                                                    <div class="alert alert-warning mt-3">
                                                        {msg}
                                                    </div>
                                                }.into_any()
                                            } else {
                                                view! { <div></div> }.into_any()
                                            }
                                        }}
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
