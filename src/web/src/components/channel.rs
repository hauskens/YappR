use leptos::prelude::*;
use crate::server_fns::{get_channels, get_channels_by_platform, ChannelData};

#[component]
pub fn ChannelsPage() -> impl IntoView {
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
        <div class="container my-4">
            <div class="row">
                <div class="col">
                    <h1 class="mb-4">"Channels from Database"</h1>

                    <div class="mb-4">
                        <div class="row align-items-center">
                            <div class="col-auto">
                                <label for="platform-filter" class="col-form-label">"Filter by platform:"</label>
                            </div>
                            <div class="col-auto">
                                <select
                                    id="platform-filter"
                                    class="form-select"
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
                        </div>
                    </div>

                    <Suspense fallback=move || {
                        view! {
                            <div class="d-flex justify-content-center my-5">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">"Loading channels..."</span>
                                </div>
                            </div>
                        }
                    }>
                        {move || Suspend::new(async move {
                            channels.await.map(|channels_result| {
                                view! {
                                    <div>
                                        {
                                            if channels_result.is_empty() {
                                                view! {
                                                    <div class="alert alert-info" role="alert">
                                                        <em>"No channels found. Add some channels to your database to see them here!"</em>
                                                    </div>
                                                }.into_any()
                                            } else {
                                                view! {
                                                    <>
                                                        <div class="alert alert-success mb-4" role="alert">
                                                            <strong>{channels_result.len()}" channels found"</strong>
                                                        </div>
                                                        <div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
                                                            {channels_result
                                                                .into_iter()
                                                                .map(|channel| {
                                                                    view! {
                                                                        <div class="col">
                                                                            <ChannelCard channel=channel/>
                                                                        </div>
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
            </div>
        </div>
    }
}

#[component]
pub fn ChannelCard(channel: ChannelData) -> impl IntoView {
    // Determine badge class and border color based on platform
    let (badge_class, border_class) = match channel.platform_name.as_str() {
        "youtube" => ("bg-danger", "border-danger"),
        "twitch" => ("bg-primary", "border-primary"),
        _ => ("bg-secondary", "border-secondary"),
    };

    view! {
        <div class=format!("card h-100 {}", border_class) style="border-width: 2px;">
            <div class="card-body">
                <h5 class="card-title">{channel.name.clone()}</h5>
                <h6 class="card-subtitle mb-3">
                    <span class=format!("badge {}", badge_class)>
                        {channel.platform_name.clone()}
                    </span>
                </h6>
                <ul class="list-group list-group-flush mb-2">
                    <li class="list-group-item px-0 py-2">
                        <small class="text-muted">"Channel ID: "</small>
                        <code class="small">{channel.platform_channel_id.clone()}</code>
                    </li>
                    <li class="list-group-item px-0 py-2">
                        <small class="text-muted">"Platform Ref: "</small>
                        <code class="small">{channel.platform_ref.clone()}</code>
                    </li>
                    <li class="list-group-item px-0 py-2">
                        <small class="text-muted">"Broadcaster ID: "</small>
                        <span class="small">{channel.broadcaster_id}</span>
                    </li>
                    <li class="list-group-item px-0 py-2">
                        <small class="text-muted">"Internal ID: "</small>
                        <span class="small">{channel.id}</span>
                    </li>
                </ul>
            </div>
        </div>
    }
}