use crate::server_fns::{
    BulkLinkParams, ChannelVideosPageData, bulk_auto_link_videos, fetch_all_channel_videos,
    fetch_channel_videos, get_channel_videos_page_data,
};
use leptos::prelude::*;
use leptos::web_sys;
use leptos_router::hooks::use_params_map;

/// Wrapper component to extract channel ID from URL params
#[component]
pub fn ChannelVideosPage() -> impl IntoView {
    let params = use_params_map();

    view! {
        {move || {
            let id_str = params.read().get("id").unwrap_or_default();
            match id_str.parse::<i32>() {
                Ok(channel_id) => {
                    view! { <ChannelVideosView channel_id=channel_id/> }
                        .into_any()
                }
                Err(_) => {
                    view! {
                        <div class="container mt-4">
                            <div class="alert alert-danger">
                                "Invalid channel ID: " {id_str}
                            </div>
                        </div>
                    }
                        .into_any()
                }
            }
        }}
    }
}

/// Main channel videos view
#[component]
fn ChannelVideosView(channel_id: i32) -> impl IntoView {
    // Resource to fetch channel videos page data
    let page_data = Resource::new(
        move || channel_id,
        |id| async move { get_channel_videos_page_data(id).await },
    );

    // Signals for bulk linking form
    let (margin_sec, set_margin_sec) = signal(10);
    let (min_duration, set_min_duration) = signal(300);
    let (date_margin_hours, set_date_margin_hours) = signal(48);

    // Action to fetch new videos
    let fetch_videos_action = Action::new(move |channel_id: &i32| {
        let id = *channel_id;
        async move { fetch_channel_videos(id).await }
    });

    // Action to fetch all videos
    let fetch_all_videos_action = Action::new(move |channel_id: &i32| {
        let id = *channel_id;
        async move { fetch_all_channel_videos(id).await }
    });

    // Action to bulk auto-link videos
    let bulk_link_action = Action::new(move |(id, params): &(i32, BulkLinkParams)| {
        let channel_id = *id;
        let params = params.clone();
        async move { bulk_auto_link_videos(channel_id, params).await }
    });

    view! {
        <div class="container my-4">
            <Suspense fallback=move || {
                view! {
                    <div class="d-flex justify-content-center my-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">"Loading channel videos..."</span>
                        </div>
                    </div>
                }
            }>
                {move || Suspend::new(async move {
                    match page_data.await {
                        Ok(data) => {
                            view! { <ChannelVideosContent
                                data=data
                                channel_id=channel_id
                                margin_sec=margin_sec
                                set_margin_sec=set_margin_sec
                                min_duration=min_duration
                                set_min_duration=set_min_duration
                                date_margin_hours=date_margin_hours
                                set_date_margin_hours=set_date_margin_hours
                                fetch_videos_action=fetch_videos_action
                                fetch_all_videos_action=fetch_all_videos_action
                                bulk_link_action=bulk_link_action
                            /> }.into_any()
                        }
                        Err(e) => {
                            view! {
                                <div class="alert alert-danger">
                                    "Error loading channel videos: " {e.to_string()}
                                </div>
                            }
                                .into_any()
                        }
                    }
                })}
            </Suspense>
        </div>
    }
}

/// Channel videos content component
#[component]
fn ChannelVideosContent(
    data: ChannelVideosPageData,
    channel_id: i32,
    margin_sec: ReadSignal<i32>,
    set_margin_sec: WriteSignal<i32>,
    min_duration: ReadSignal<i32>,
    set_min_duration: WriteSignal<i32>,
    date_margin_hours: ReadSignal<i32>,
    set_date_margin_hours: WriteSignal<i32>,
    fetch_videos_action: Action<i32, Result<String, ServerFnError>>,
    fetch_all_videos_action: Action<i32, Result<String, ServerFnError>>,
    bulk_link_action: Action<(i32, BulkLinkParams), Result<String, ServerFnError>>,
) -> impl IntoView {
    let channel = data.channel.clone();
    let videos = data.videos.clone();
    let permissions = data.permissions.clone();

    view! {
        <div>
            // Header
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1 class="display-5">"Videos on Channel: " {channel.name.clone()}</h1>
                    <p class="text-muted">
                        "Total Videos: " {data.total_videos} " | Videos with Transcriptions: " {data.transcription_count}
                    </p>
                </div>
                <a href="/channels" class="btn btn-secondary">
                    <i class="bi bi-arrow-left me-2"></i>
                    "Back to Channels"
                </a>
            </div>

            // Admin Controls Section
            {if permissions.can_bulk_link || permissions.can_fetch_videos {
                view! {
                    <div class="card mb-4">
                        <div class="card-header">
                            <button
                                class="btn btn-link text-decoration-none w-100 text-start p-0"
                                type="button"
                                data-bs-toggle="collapse"
                                data-bs-target="#adminControls"
                            >
                                <i class="bi bi-gear-fill me-2"></i>
                                "Admin Controls"
                                <i class="bi bi-chevron-down float-end"></i>
                            </button>
                        </div>
                        <div id="adminControls" class="collapse">
                            <div class="card-body">
                                // Bulk Video Linking
                                {if permissions.can_bulk_link && channel.source_channel.is_some() {
                                    let source_name = channel.source_channel.as_ref().unwrap().name.clone();
                                    view! {
                                        <div class="mb-3">
                                            <button
                                                class="btn btn-primary"
                                                type="button"
                                                data-bs-toggle="collapse"
                                                data-bs-target="#linkingOptions"
                                            >
                                                <i class="bi bi-link-45deg me-2"></i>
                                                "Bulk Video Linking"
                                            </button>
                                            <div class="collapse mt-3" id="linkingOptions">
                                                <div class="card">
                                                    <div class="card-body">
                                                        <h6 class="card-title">"Link Videos based on title parsing and duration matching"</h6>
                                                        <p class="card-text text-muted small">
                                                            "Uses duration matching + title date parsing to link videos between channels. "
                                                            "Will link videos from " <strong>{source_name}</strong> "."
                                                        </p>

                                                        <div class="row">
                                                            <div class="col-md-4">
                                                                <div class="mb-3">
                                                                    <label for="bulk_margin_sec" class="form-label">"Duration Margin (seconds)"</label>
                                                                    <input
                                                                        type="number"
                                                                        class="form-control form-control-sm"
                                                                        id="bulk_margin_sec"
                                                                        min="0"
                                                                        max="20"
                                                                        prop:value=move || margin_sec.get()
                                                                        on:input=move |ev| {
                                                                            if let Ok(val) = event_target_value(&ev).parse::<i32>() {
                                                                                set_margin_sec.set(val);
                                                                            }
                                                                        }
                                                                    />
                                                                    <div class="form-text">"±seconds tolerance for video duration"</div>
                                                                </div>
                                                            </div>
                                                            <div class="col-md-4">
                                                                <div class="mb-3">
                                                                    <label for="bulk_min_duration" class="form-label">"Min Duration (seconds)"</label>
                                                                    <input
                                                                        type="number"
                                                                        class="form-control form-control-sm"
                                                                        id="bulk_min_duration"
                                                                        min="60"
                                                                        prop:value=move || min_duration.get()
                                                                        on:input=move |ev| {
                                                                            if let Ok(val) = event_target_value(&ev).parse::<i32>() {
                                                                                set_min_duration.set(val);
                                                                            }
                                                                        }
                                                                    />
                                                                    <div class="form-text">"Skip videos shorter than this"</div>
                                                                </div>
                                                            </div>
                                                            <div class="col-md-4">
                                                                <div class="mb-3">
                                                                    <label for="bulk_date_margin_hours" class="form-label">"Date Margin (hours)"</label>
                                                                    <input
                                                                        type="number"
                                                                        class="form-control form-control-sm"
                                                                        id="bulk_date_margin_hours"
                                                                        min="1"
                                                                        max="168"
                                                                        prop:value=move || date_margin_hours.get()
                                                                        on:input=move |ev| {
                                                                            if let Ok(val) = event_target_value(&ev).parse::<i32>() {
                                                                                set_date_margin_hours.set(val);
                                                                            }
                                                                        }
                                                                    />
                                                                    <div class="form-text">"Max time difference for date matches"</div>
                                                                </div>
                                                            </div>
                                                        </div>

                                                        <button
                                                            class="btn btn-success"
                                                            on:click=move |_| {
                                                                if web_sys::window().map(|w| w.confirm_with_message(
                                                                        "This will automatically link all videos where BOTH Duration AND Date matches are found. No manual confirmation required. Continue?"
                                                                    ).unwrap_or(false))
                                                                    .unwrap_or(false)
                                                                {
                                                                    bulk_link_action.dispatch((channel_id, BulkLinkParams {
                                                                        margin_sec: margin_sec.get(),
                                                                        min_duration: min_duration.get(),
                                                                        date_margin_hours: date_margin_hours.get(),
                                                                    }));
                                                                }
                                                            }
                                                        >
                                                            <i class="bi bi-lightning-fill me-2"></i>
                                                            "Bulk Auto-Link (Duration + Date Matches Only)"
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    }.into_any()
                                } else {
                                    view! { <div></div> }.into_any()
                                }}
                            </div>
                        </div>
                    </div>
                }.into_any()
            } else {
                view! { <div></div> }.into_any()
            }}

            <hr/>

            // Fetch Videos Buttons
            <div class="mb-3">
                {if permissions.can_fetch_videos {
                    view! {
                        <button
                            class="btn btn-primary me-2"
                            on:click=move |_| {
                                if web_sys::window().map(|w| w.confirm_with_message(
                                        "This will look for new videos on this channel. Results are instant. Continue?"
                                    ).unwrap_or(false))
                                    .unwrap_or(false)
                                {
                                    fetch_videos_action.dispatch(channel_id);
                                }
                            }
                        >
                            <i class="bi bi-arrow-repeat me-2"></i>
                            "Look for new videos on channel"
                        </button>
                    }.into_any()
                } else {
                    view! { <div></div> }.into_any()
                }}

                {if permissions.can_fetch_all_videos {
                    view! {
                        <button
                            class="btn btn-primary"
                            on:click=move |_| {
                                if web_sys::window().map(|w| w.confirm_with_message(
                                        "This will look for ALL videos on this channel. Results are instant. Continue?"
                                    ).unwrap_or(false))
                                    .unwrap_or(false)
                                {
                                    fetch_all_videos_action.dispatch(channel_id);
                                }
                            }
                        >
                            <i class="bi bi-arrow-clockwise me-2"></i>
                            "Look for all videos on channel"
                        </button>
                    }.into_any()
                } else {
                    view! { <div></div> }.into_any()
                }}
            </div>

            <hr/>

            // Videos Table
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="bi bi-collection-play me-2"></i>
                        "Videos"
                    </h5>
                </div>
                <div class="card-body p-0">
                    {if videos.is_empty() {
                        view! {
                            <div class="text-center text-muted py-5">
                                <i class="bi bi-collection-play fs-1 mb-2"></i>
                                <p>"No videos found for this channel."</p>
                            </div>
                        }.into_any()
                    } else {
                        view! {
                            <div class="table-responsive">
                                <table class="table table-striped table-hover mb-0">
                                    <thead>
                                        <tr>
                                            <th scope="col">"Thumbnail"</th>
                                            <th scope="col">"Title"</th>
                                            <th scope="col">"Duration"</th>
                                            <th scope="col">"Transcriptions"</th>
                                            <th scope="col">"Status"</th>
                                            <th scope="col">"Linked Status"</th>
                                            <th scope="col">"Published"</th>
                                            <th scope="col">"Estimated Upload"</th>
                                            <th scope="col">"Actions"</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {videos.into_iter().filter(|v| v.active).map(|video| {
                                            let video_id = video.id;
                                            let has_transcriptions = !video.transcriptions.is_empty();
                                            let has_processed_transcriptions = video.transcriptions.iter().any(|t| t.processed);
                                            let has_unprocessed_transcriptions = video.transcriptions.iter().any(|t| !t.processed);
                                            let has_segments = video.segment_count > 0;

                                            view! {
                                                <tr>
                                                    <td>
                                                        <img
                                                            src={format!("/thumbnails/{}", video_id)}
                                                            alt="Thumbnail"
                                                            style="max-width:100%; max-height:250px;"
                                                        />
                                                    </td>
                                                    <td>
                                                        <span
                                                            class="d-inline-block text-truncate"
                                                            style="max-width: 30vw;"
                                                            title={video.title.clone()}
                                                        >
                                                            {video.title.clone()}
                                                        </span>
                                                    </td>
                                                    <td>{format!("{}s", video.duration)}</td>
                                                    <td>
                                                        {if has_transcriptions {
                                                            if has_processed_transcriptions {
                                                                view! { <span class="badge bg-success">"Processed"</span> }.into_any()
                                                            } else {
                                                                view! { <span class="badge bg-warning">"Not processed"</span> }.into_any()
                                                            }
                                                        } else {
                                                            view! { <span class="text-muted">"None"</span> }.into_any()
                                                        }}
                                                    </td>
                                                    <td>
                                                        {if video.has_audio {
                                                            view! { <span class="badge bg-info">"Has audio"</span> }.into_any()
                                                        } else if let Some(ref source) = video.source_video {
                                                            view! {
                                                                <a href={format!("/videos/{}", source.id)}>
                                                                    "Linked with source"
                                                                </a>
                                                            }.into_any()
                                                        } else {
                                                            view! { <span class="text-muted">"No audio"</span> }.into_any()
                                                        }}
                                                    </td>
                                                    <td>
                                                        {if let Some(ref source) = video.source_video {
                                                            view! {
                                                                <div>
                                                                    <span class="badge bg-success">
                                                                        <i class="bi bi-link-45deg me-1"></i>
                                                                        "Linked"
                                                                    </span>
                                                                    <br/>
                                                                    <small class="text-muted">
                                                                        <a
                                                                            href={format!("/videos/{}", source.id)}
                                                                            class="text-decoration-none"
                                                                        >
                                                                            {if source.title.len() > 30 {
                                                                                format!("{}...", &source.title[..30])
                                                                            } else {
                                                                                source.title.clone()
                                                                            }}
                                                                        </a>
                                                                    </small>
                                                                </div>
                                                            }.into_any()
                                                        } else {
                                                            view! {
                                                                <span class="badge bg-secondary">
                                                                    <i class="bi bi-x-circle me-1"></i>
                                                                    "Not Linked"
                                                                </span>
                                                            }.into_any()
                                                        }}
                                                    </td>
                                                    <td>{video.uploaded.clone()}</td>
                                                    <td>
                                                        {video.estimated_upload_time.unwrap_or_else(|| "N/A".to_string())}
                                                    </td>
                                                    <td>
                                                        <div class="d-flex flex-column gap-1">
                                                            <a
                                                                class="btn btn-sm btn-primary"
                                                                href={format!("/videos/{}", video_id)}
                                                            >
                                                                <i class="bi bi-pencil me-1"></i>
                                                                "Edit Video"
                                                            </a>

                                                            {if permissions.can_process_videos {
                                                                if !has_segments && !has_transcriptions {
                                                                    view! {
                                                                        <button
                                                                            class="btn btn-sm btn-success"
                                                                            title="Run in background: This will queue up full processing of video"
                                                                        >
                                                                            <i class="bi bi-play-fill me-1"></i>
                                                                            "Start full processing"
                                                                        </button>
                                                                    }.into_any()
                                                                } else {
                                                                    view! { <div></div> }.into_any()
                                                                }
                                                            } else {
                                                                view! { <div></div> }.into_any()
                                                            }}

                                                            {if permissions.can_process_videos && !has_segments && has_unprocessed_transcriptions {
                                                                view! {
                                                                    <button
                                                                        class="btn btn-sm btn-info"
                                                                        title="Quick task that parses the transcription and makes it searchable"
                                                                    >
                                                                        <i class="bi bi-search me-1"></i>
                                                                        "Make searchable"
                                                                    </button>
                                                                }.into_any()
                                                            } else {
                                                                view! { <div></div> }.into_any()
                                                            }}

                                                            {if permissions.can_process_videos && video.has_audio && !has_transcriptions {
                                                                view! {
                                                                    <button
                                                                        class="btn btn-sm btn-warning"
                                                                        title="Transcribe audio, this will take long time"
                                                                    >
                                                                        <i class="bi bi-file-text me-1"></i>
                                                                        "Process audio"
                                                                    </button>
                                                                }.into_any()
                                                            } else if permissions.can_process_videos && !video.has_audio {
                                                                view! {
                                                                    <button
                                                                        class="btn btn-sm btn-secondary"
                                                                        title={format!("Download audio from {}", channel.platform_name)}
                                                                    >
                                                                        <i class="bi bi-download me-1"></i>
                                                                        {format!("Fetch audio from {}", channel.platform_name)}
                                                                    </button>
                                                                }.into_any()
                                                            } else {
                                                                view! { <div></div> }.into_any()
                                                            }}
                                                        </div>
                                                    </td>
                                                </tr>
                                            }
                                        }).collect_view()}
                                    </tbody>
                                </table>
                            </div>
                        }.into_any()
                    }}
                </div>
            </div>

            // Action results
            <div class="mt-3">
                {move || {
                    if let Some(result) = fetch_videos_action.value().get() {
                        match result {
                            Ok(msg) => view! {
                                <div class="alert alert-success" role="alert">
                                    {msg}
                                </div>
                            }.into_any(),
                            Err(e) => view! {
                                <div class="alert alert-danger" role="alert">
                                    "Error: " {e.to_string()}
                                </div>
                            }.into_any(),
                        }
                    } else {
                        view! { <div></div> }.into_any()
                    }
                }}

                {move || {
                    if let Some(result) = fetch_all_videos_action.value().get() {
                        match result {
                            Ok(msg) => view! {
                                <div class="alert alert-success" role="alert">
                                    {msg}
                                </div>
                            }.into_any(),
                            Err(e) => view! {
                                <div class="alert alert-danger" role="alert">
                                    "Error: " {e.to_string()}
                                </div>
                            }.into_any(),
                        }
                    } else {
                        view! { <div></div> }.into_any()
                    }
                }}

                {move || {
                    if let Some(result) = bulk_link_action.value().get() {
                        match result {
                            Ok(msg) => view! {
                                <div class="alert alert-success" role="alert">
                                    {msg}
                                </div>
                            }.into_any(),
                            Err(e) => view! {
                                <div class="alert alert-danger" role="alert">
                                    "Error: " {e.to_string()}
                                </div>
                            }.into_any(),
                        }
                    } else {
                        view! { <div></div> }.into_any()
                    }
                }}
            </div>
        </div>
    }
}
