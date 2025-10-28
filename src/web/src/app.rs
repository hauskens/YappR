use leptos::prelude::*;
use leptos_meta::{provide_meta_context, MetaTags, Script, Stylesheet, Title};
use leptos_router::{
    components::{Route, Router, Routes},
    StaticSegment,
};
use leptos::server_fn::ServerFnError;
use leptos::task::spawn_local;
use crate::server_fns::{get_channels, get_channels_by_platform, ChannelData};

pub fn shell(options: LeptosOptions) -> impl IntoView {
    view! {
        <!DOCTYPE html>
        <html lang="en">
            <head>
                <meta charset="utf-8"/>
                <meta name="viewport" content="width=device-width, initial-scale=1"/>
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

    view! {
        // Bootstrap CSS
        <Stylesheet id="bootstrap" href="/vendor/bootstrap/bootstrap.min.css"/>

        // injects a stylesheet into the document <head>
        // id=leptos means cargo-leptos will hot-reload this stylesheet
        <Stylesheet id="leptos" href="/pkg/yappr-web.css"/>

        // Bootstrap JS bundle (includes Popper)
        <Script src="/vendor/bootstrap/bootstrap.bundle.min.js"/>

        // sets the document title
        <Title text="Welcome to LeptOS"/>

        // content for this welcome page
        <Router>
            <main>
                <nav style="padding: 20px; background: #f0f0f0; margin-bottom: 20px;">
                    <a href="/" style="margin-right: 20px;">"Home"</a>
                    <a href="/channels">"Channels"</a>
                </nav>
                <Routes fallback=|| "Page not found.".into_view()>
                    <Route path=StaticSegment("") view=HomePage/>
                    <Route path=StaticSegment("channels") view=ChannelsPage/>
                </Routes>
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

/// Renders the channels page with a list of channels from the database
#[component]
fn ChannelsPage() -> impl IntoView {
    // Signal for the selected platform filter
    let (selected_platform, set_selected_platform) = signal(String::from("all"));

    // Resource that fetches channels based on the selected platform
    let channels = Resource::new(
        move || selected_platform.get(),
        |platform| async move {
            if platform == "all" {
                get_channels().await
            } else {
                get_channels_by_platform(platform).await
            }
        },
    );

    view! {
        <div style="padding: 20px;">
            <h1>"Channels from Database"</h1>
            <p>"This demonstrates the full Leptos stack working with your SeaORM entities and services!"</p>

            <div style="margin: 20px 0;">
                <label for="platform-filter">"Filter by platform: "</label>
                <select
                    id="platform-filter"
                    on:change=move |ev| {
                        let value = event_target_value(&ev);
                        set_selected_platform.set(value);
                    }
                >
                    <option value="all">"All Platforms"</option>
                    <option value="youtube">"YouTube"</option>
                    <option value="twitch">"Twitch"</option>
                </select>
            </div>

            <Suspense fallback=move || {
                view! { <p>"Loading channels..."</p> }
            }>
                {move || Suspend::new(async move {
                    channels.await.map(|channels_result| {
                        view! {
                            <div>
                                {
                                    if channels_result.is_empty() {
                                        view! {
                                            <p><em>"No channels found. Add some channels to your database to see them here!"</em></p>
                                        }.into_any()
                                    } else {
                                        view! {
                                            <>
                                                <p><strong>{channels_result.len()}" channels found"</strong></p>
                                                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; margin-top: 20px;">
                                                    {channels_result
                                                        .into_iter()
                                                        .map(|channel| {
                                                            view! {
                                                                <ChannelCard channel=channel/>
                                                            }
                                                        })
                                                        .collect_view()}
                                                </div>
                                            </>
                                        }.into_any()
                                    }
                                }
                            </div>
                        }
                    })
                })}
            </Suspense>
        </div>
    }
}

/// Component to display a single channel as a card
#[component]
fn ChannelCard(channel: ChannelData) -> impl IntoView {
    // Determine background color based on platform
    let platform_color = match channel.platform_name.as_str() {
        "youtube" => "#FF0000",
        "twitch" => "#9146FF",
        _ => "#333333",
    };

    view! {
        <div style=format!(
            "border: 2px solid {}; border-radius: 8px; padding: 15px; background: white;",
            platform_color,
        )>
            <h3 style="margin: 0 0 10px 0;">{channel.name.clone()}</h3>
            <div style="font-size: 0.9em; color: #666;">
                <p style="margin: 5px 0;">
                    <strong>"Platform: "</strong>
                    <span
                        style=format!(
                            "background: {}; color: white; padding: 2px 8px; border-radius: 3px;",
                            platform_color,
                        )
                    >
                        {channel.platform_name.clone()}
                    </span>
                </p>
                <p style="margin: 5px 0;">
                    <strong>"Channel ID: "</strong>
                    <code>{channel.platform_channel_id.clone()}</code>
                </p>
                <p style="margin: 5px 0;">
                    <strong>"Platform Ref: "</strong>
                    <code>{channel.platform_ref.clone()}</code>
                </p>
                <p style="margin: 5px 0;">
                    <strong>"Broadcaster ID: "</strong>
                    {channel.broadcaster_id}
                </p>
                <p style="margin: 5px 0;">
                    <strong>"Internal ID: "</strong>
                    {channel.id}
                </p>
            </div>
        </div>
    }
}