//! Broadcaster Edit Page Component
//!
//! Main page for editing broadcaster settings, managing channels, and viewing stats.
//! Features a modern tabbed interface with Overview, Channels, Settings, and Events tabs.

use leptos::prelude::*;
use crate::server_fns::{get_broadcaster_edit_data, BroadcasterEditData};

#[derive(Debug, Clone, Copy, PartialEq)]
enum Tab {
    Overview,
    Channels,
    Settings,
    Events,
}

impl Tab {
    fn label(&self) -> &'static str {
        match self {
            Tab::Overview => "Overview",
            Tab::Channels => "Channels",
            Tab::Settings => "Settings",
            Tab::Events => "Events",
        }
    }
}

#[component]
pub fn BroadcasterEditPage(broadcaster_id: i32) -> impl IntoView {
    let (active_tab, set_active_tab) = signal(Tab::Overview);

    // Fetch broadcaster data
    let broadcaster_data = Resource::new(
        move || (),
        move |_| async move { get_broadcaster_edit_data(broadcaster_id).await },
    );

    view! {
        <div class="container mt-4">
            <Suspense fallback=move || {
                view! {
                    <div class="text-center">
                        <div class="spinner-border" role="status">
                            <span class="visually-hidden">"Loading..."</span>
                        </div>
                    </div>
                }
            }>
                {move || {
                    broadcaster_data
                        .get()
                        .map(|data| match data {
                            Ok(broadcaster_edit_data) => {
                                view! {
                                    <BroadcasterEditContent
                                        data=broadcaster_edit_data
                                        broadcaster_id=broadcaster_id
                                        active_tab=active_tab
                                        set_active_tab=set_active_tab
                                    />
                                }
                                    .into_any()
                            }
                            Err(e) => {
                                view! {
                                    <div class="alert alert-danger" role="alert">
                                        <h4 class="alert-heading">"Error Loading Broadcaster"</h4>
                                        <p>{format!("Failed to load broadcaster: {}", e)}</p>
                                    </div>
                                }
                                    .into_any()
                            }
                        })
                }}

            </Suspense>
        </div>
    }
}

#[component]
fn BroadcasterEditContent(
    data: BroadcasterEditData,
    broadcaster_id: i32,
    active_tab: ReadSignal<Tab>,
    set_active_tab: WriteSignal<Tab>,
) -> impl IntoView {
    let broadcaster = data.broadcaster.clone();
    let stats = data.stats.clone();

    view! {
        <div class="broadcaster-edit-page">
            // Page Header
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1 class="mb-0">{broadcaster.name.clone()}</h1>
                    <div class="text-muted">"Broadcaster ID: " {broadcaster.id}</div>
                </div>
                <div>
                    {move || {
                        if broadcaster.hidden {
                            view! {
                                <span class="badge bg-warning text-dark">
                                    <i class="bi bi-eye-slash"></i>
                                    " Hidden"
                                </span>
                            }
                                .into_any()
                        } else {
                            view! { <span class="badge bg-success">"Visible"</span> }
                                .into_any()
                        }
                    }}

                </div>
            </div>
            // Stats Cards
            <div class="row mb-4">
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-subtitle mb-2 text-muted">"Channels"</h6>
                            <h3 class="card-title mb-0">{stats.total_channels}</h3>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-subtitle mb-2 text-muted">"Videos"</h6>
                            <h3 class="card-title mb-0">{stats.total_videos}</h3>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-subtitle mb-2 text-muted">"Transcriptions"</h6>
                            <h3 class="card-title mb-0">{stats.total_transcriptions}</h3>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-subtitle mb-2 text-muted">"Storage Used"</h6>
                            <h3 class="card-title mb-0">{format!("{:.1} GB", stats.storage_used_gb)}</h3>
                        </div>
                    </div>
                </div>
            </div>
            // Tab Navigation
            <ul class="nav nav-tabs mb-4">
                {[Tab::Overview, Tab::Channels, Tab::Settings, Tab::Events]
                    .iter()
                    .map(|tab| {
                        let tab = *tab;
                        let is_active = move || active_tab.get() == tab;
                        view! {
                            <li class="nav-item">
                                <a
                                    class=move || {
                                        if is_active() { "nav-link active" } else { "nav-link" }
                                    }

                                    href="#"
                                    on:click=move |e| {
                                        e.prevent_default();
                                        set_active_tab.set(tab);
                                    }
                                >

                                    {tab.label()}
                                </a>
                            </li>
                        }
                    })
                    .collect_view()}

            </ul>
            // Tab Content
            <div class="tab-content">
                {move || match active_tab.get() {
                    Tab::Overview => {
                        view! { <OverviewTab data=data.clone() /> }
                            .into_any()
                    }
                    Tab::Channels => {
                        view! { <ChannelsTab data=data.clone() /> }
                            .into_any()
                    }
                    Tab::Settings => {
                        view! { <SettingsTab data=data.clone() broadcaster_id=broadcaster_id /> }
                            .into_any()
                    }
                    Tab::Events => {
                        view! { <EventsTab broadcaster_id=broadcaster_id /> }
                            .into_any()
                    }
                }}

            </div>
        </div>
    }
}

#[component]
fn OverviewTab(data: BroadcasterEditData) -> impl IntoView {
    let profile_image_url = data.broadcaster.profile_image_url.clone();
    let broadcaster_name = data.broadcaster.name.clone();
    let broadcaster_id = data.broadcaster.id;
    let broadcaster_hidden = data.broadcaster.hidden;
    let channels = data.channels.clone();
    let has_channels = !channels.is_empty();

    view! {
        <div class="overview-tab">
            <h3>"Broadcaster Overview"</h3>

            // Broadcaster Info Card
            <div class="card mb-4">
                <div class="card-header">"Information"</div>
                <div class="card-body">
                    {move || {
                        if let Some(ref image_url) = profile_image_url {
                            view! {
                                <div class="mb-3">
                                    <img src=image_url alt="Profile" class="img-thumbnail" style="max-width: 200px;"/>
                                </div>
                            }
                                .into_any()
                        } else {
                            view! { <div></div> }
                                .into_any()
                        }
                    }}

                    <dl class="row mb-0">
                        <dt class="col-sm-3">"Name"</dt>
                        <dd class="col-sm-9">{broadcaster_name}</dd>

                        <dt class="col-sm-3">"ID"</dt>
                        <dd class="col-sm-9">{broadcaster_id}</dd>

                        <dt class="col-sm-3">"Visibility"</dt>
                        <dd class="col-sm-9">
                            {if broadcaster_hidden { "Hidden" } else { "Visible" }}
                        </dd>
                    </dl>
                </div>
            </div>

            // Quick Channel Summary
            <div class="card">
                <div class="card-header">"Channels"</div>
                <div class="card-body">
                    {if !has_channels {
                        view! {
                            <p class="text-muted mb-0">"No channels configured."</p>
                        }
                            .into_any()
                    } else {
                        view! {
                            <ul class="list-group list-group-flush">
                                {channels
                                    .into_iter()
                                    .map(|channel| {
                                        view! {
                                            <li class="list-group-item">
                                                <div class="d-flex justify-content-between align-items-center">
                                                    <div>
                                                        <strong>{channel.name.clone()}</strong>
                                                        " "
                                                        <span class="badge bg-secondary">{channel.platform_name.clone()}</span>
                                                        " "
                                                        <span class="badge bg-info">{channel.main_video_type.clone()}</span>
                                                    </div>
                                                    {move || {
                                                        if let Some(ref last_active) = channel.last_active {
                                                            view! {
                                                                <small class="text-muted">
                                                                    "Last active: " {last_active.clone()}
                                                                </small>
                                                            }
                                                                .into_any()
                                                        } else {
                                                            view! { <span></span> }
                                                                .into_any()
                                                        }
                                                    }}

                                                </div>
                                            </li>
                                        }
                                    })
                                    .collect_view()}

                            </ul>
                        }
                            .into_any()
                    }}

                </div>
            </div>
        </div>
    }
}

#[component]
fn ChannelsTab(data: BroadcasterEditData) -> impl IntoView {
    let channels = data.channels.clone();
    let has_channels = !channels.is_empty();

    view! {
        <div class="channels-tab">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h3>"Manage Channels"</h3>
                <button class="btn btn-primary">
                    <i class="bi bi-plus-circle"></i>
                    " Add Channel"
                </button>
            </div>

            {if !has_channels {
                view! {
                    <div class="alert alert-info">
                        "No channels configured. Add a channel to get started."
                    </div>
                }
                    .into_any()
            } else {
                view! {
                    <div class="row">
                        {channels
                            .into_iter()
                            .map(|channel| {
                                view! {
                                    <div class="col-md-6 mb-3">
                                        <div class="card">
                                            <div class="card-header">
                                                <div class="d-flex justify-content-between align-items-center">
                                                    <div>
                                                        <strong>{channel.name.clone()}</strong>
                                                        " "
                                                        <span class="badge bg-secondary">{channel.platform_name.clone()}</span>
                                                    </div>
                                                    <div class="btn-group btn-group-sm">
                                                        <button class="btn btn-outline-secondary" title="Edit">
                                                            <i class="bi bi-pencil"></i>
                                                        </button>
                                                        <button class="btn btn-outline-danger" title="Delete">
                                                            <i class="bi bi-trash"></i>
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                            <div class="card-body">
                                                <dl class="row mb-0 small">
                                                    <dt class="col-sm-4">"Platform ID"</dt>
                                                    <dd class="col-sm-8">
                                                        <code class="small">{channel.platform_channel_id.clone()}</code>
                                                    </dd>

                                                    <dt class="col-sm-4">"Main Type"</dt>
                                                    <dd class="col-sm-8">
                                                        <span class="badge bg-info">{channel.main_video_type.clone()}</span>
                                                    </dd>

                                                    {move || {
                                                        if let Some(ref last_active) = channel.last_active {
                                                            view! {
                                                                <>
                                                                    <dt class="col-sm-4">"Last Active"</dt>
                                                                    <dd class="col-sm-8">{last_active.clone()}</dd>
                                                                </>
                                                            }
                                                                .into_any()
                                                        } else {
                                                            view! { <></> }
                                                                .into_any()
                                                        }
                                                    }}

                                                    {move || {
                                                        if let Some(ref settings) = channel.settings {
                                                            view! {
                                                                <>
                                                                    <dt class="col-sm-4">"Settings"</dt>
                                                                    <dd class="col-sm-8">
                                                                        {if settings.chat_collection_enabled {
                                                                            view! {
                                                                                <span class="badge bg-success me-1">"Chat"</span>
                                                                            }
                                                                                .into_any()
                                                                        } else {
                                                                            view! { <span></span> }
                                                                                .into_any()
                                                                        }}
                                                                        {if settings.content_queue_enabled {
                                                                            view! {
                                                                                <span class="badge bg-success">"Queue"</span>
                                                                            }
                                                                                .into_any()
                                                                        } else {
                                                                            view! { <span></span> }
                                                                                .into_any()
                                                                        }}

                                                                    </dd>
                                                                </>
                                                            }
                                                                .into_any()
                                                        } else {
                                                            view! { <></> }
                                                                .into_any()
                                                        }
                                                    }}

                                                </dl>
                                            </div>
                                        </div>
                                    </div>
                                }
                            })
                            .collect_view()}

                    </div>
                }
                    .into_any()
            }}

        </div>
    }
}

#[component]
fn SettingsTab(data: BroadcasterEditData, broadcaster_id: i32) -> impl IntoView {
    let profile_image_url = data.broadcaster.profile_image_url.clone().unwrap_or_default();
    let broadcaster_hidden = data.broadcaster.hidden;
    let settings = data.settings.clone();

    view! {
        <div class="settings-tab">
            <h3>"Broadcaster Settings"</h3>

            <div class="card mb-4">
                <div class="card-header">"General Settings"</div>
                <div class="card-body">
                    <form>
                        <div class="mb-3">
                            <label for="profile-image-url" class="form-label">
                                "Profile Image URL"
                            </label>
                            <input
                                type="url"
                                class="form-control"
                                id="profile-image-url"
                                value=profile_image_url
                            />
                            <div class="form-text">"URL to the broadcaster's profile image"</div>
                        </div>

                        <div class="mb-3 form-check">
                            <input
                                type="checkbox"
                                class="form-check-input"
                                id="hidden"
                                checked=broadcaster_hidden
                            />
                            <label class="form-check-label" for="hidden">
                                "Hide broadcaster from public listings"
                            </label>
                        </div>

                        <button type="submit" class="btn btn-primary">
                            "Save Settings"
                        </button>
                    </form>
                </div>
            </div>

            <div class="card">
                <div class="card-header">"Discord Integration"</div>
                <div class="card-body">
                    {move || {
                        if let Some(ref broadcaster_settings) = settings {
                            view! {
                                <form>
                                    <div class="mb-3">
                                        <label for="discord-channel-id" class="form-label">
                                            "Discord Channel ID"
                                        </label>
                                        <input
                                            type="text"
                                            class="form-control"
                                            id="discord-channel-id"
                                            value=broadcaster_settings
                                                .linked_discord_channel_id
                                                .map(|id| id.to_string())
                                                .unwrap_or_default()
                                        />
                                        {if broadcaster_settings.linked_discord_channel_verified {
                                            view! {
                                                <div class="form-text text-success">
                                                    <i class="bi bi-check-circle"></i>
                                                    " Verified"
                                                </div>
                                            }
                                                .into_any()
                                        } else {
                                            view! {
                                                <div class="form-text">"Not yet verified"</div>
                                            }
                                                .into_any()
                                        }}

                                    </div>

                                    <div class="mb-3 form-check">
                                        <input
                                            type="checkbox"
                                            class="form-check-input"
                                            id="disable-voting"
                                            checked=broadcaster_settings.linked_discord_disable_voting
                                        />
                                        <label class="form-check-label" for="disable-voting">
                                            "Disable voting"
                                        </label>
                                    </div>

                                    <div class="mb-3 form-check">
                                        <input
                                            type="checkbox"
                                            class="form-check-input"
                                            id="threads-enabled"
                                            checked=broadcaster_settings.linked_discord_threads_enabled
                                        />
                                        <label class="form-check-label" for="threads-enabled">
                                            "Enable threads"
                                        </label>
                                    </div>

                                    <button type="submit" class="btn btn-primary">
                                        "Save Discord Settings"
                                    </button>
                                </form>
                            }
                                .into_any()
                        } else {
                            view! {
                                <p class="text-muted">"No Discord settings configured."</p>
                            }
                                .into_any()
                        }
                    }}

                </div>
            </div>
        </div>
    }
}

#[component]
fn EventsTab(broadcaster_id: i32) -> impl IntoView {
    view! {
        <div class="events-tab">
            <h3>"Event Log"</h3>
            <div class="alert alert-info">
                "Events table will be implemented in a future update. Broadcaster ID: " {broadcaster_id}
            </div>
        </div>
    }
}
