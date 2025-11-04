use crate::server_fns::{
    VideoDetailData, get_chat_logs, get_transcription_segments, get_video_detail,
};
use leptos::prelude::*;
use leptos_router::hooks::use_params_map;

/// Wrapper component to extract video ID from URL params
#[component]
pub fn VideoPage() -> impl IntoView {
    let params = use_params_map();

    view! {
        {move || {
            let id_str = params.read().get("id").unwrap_or_default();
            match id_str.parse::<i32>() {
                Ok(video_id) => {
                    view! { <VideoDetail video_id=video_id/> }
                        .into_any()
                }
                Err(_) => {
                    view! {
                        <div class="container mt-4">
                            <div class="alert alert-danger">
                                "Invalid video ID: " {id_str}
                            </div>
                        </div>
                    }
                        .into_any()
                }
            }
        }}
    }
}

/// Main video detail component
#[component]
fn VideoDetail(video_id: i32) -> impl IntoView {
    // Resource to fetch video data
    let video_resource = Resource::new(
        move || video_id,
        |id| async move { get_video_detail(id).await },
    );

    view! {
        <div class="container my-4">
            <Suspense fallback=move || {
                view! {
                    <div class="d-flex justify-content-center my-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">"Loading video..."</span>
                        </div>
                    </div>
                }
            }>
                {move || Suspend::new(async move {
                    match video_resource.await {
                        Ok(video) => {
                            view! { <VideoContent video=video video_id=video_id/> }.into_any()
                        }
                        Err(e) => {
                            view! {
                                <div class="alert alert-danger">
                                    "Error loading video: " {e.to_string()}
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

/// Video content component
#[component]
fn VideoContent(video: VideoDetailData, video_id: i32) -> impl IntoView {
    // Signal to track if transcription segments are loaded
    let (segments_loaded, set_segments_loaded) = signal(false);
    let (chat_loaded, set_chat_loaded) = signal(false);

    // Conditionally load transcription segments
    let segments_resource = Resource::new(
        move || (video_id, segments_loaded.get()),
        |(id, loaded)| async move {
            if loaded {
                get_transcription_segments(id).await.ok()
            } else {
                None
            }
        },
    );

    // Conditionally load chat logs
    let chat_resource = Resource::new(
        move || (video_id, chat_loaded.get()),
        |(id, loaded)| async move {
            if loaded {
                get_chat_logs(id).await.ok()
            } else {
                None
            }
        },
    );

    // Inactive video check
    if !video.active {
        return view! {
            <div class="container">
                <h1>"Video is not active"</h1>
                <p>"This video is not available, likely disabled on " {video.platform_name.clone()} " or deleted"</p>
            </div>
        }
        .into_any();
    }

    view! {
        <div>
            // Back button
            <a class="btn btn-primary mb-3" role="button" href={format!("/channels/{}/videos", video.channel.id)}>
                "Back to Channel"
            </a>

            <hr/>

            // Video Title and Thumbnail
            <div class="row mb-4">
                <div class="col-md-4">
                    <h3>{video.title.clone()}</h3>
                    // Admin actions dropdown could go here
                </div>

                <div class="col-md-8">
                    // Platform badge
                    <a href={video.platform_url.clone()} target="_blank" class="btn btn-primary">
                        "View on " {video.platform_name.clone()}
                    </a>
                    <br/><br/>

                    // Source video linking info
                    {if let Some(source) = &video.source_video {
                        view! {
                            <div class="card mb-3">
                                <div class="card-header">
                                    <h6 class="mb-0">"Linked to Source Video"</h6>
                                </div>
                                <div class="card-body">
                                    <h6 class="card-title">{source.title.clone()}</h6>
                                    <p class="text-muted mb-2">
                                        "Uploaded: " {source.uploaded.clone()}
                                        <br/>
                                        "Duration: " {source.duration} " seconds"
                                        <br/>
                                        "Channel: " {source.channel.name.clone()}
                                    </p>
                                </div>
                            </div>
                        }.into_any()
                    } else {
                        view! { <div></div> }.into_any()
                    }}

                    <p>"Uploaded: " {video.uploaded.clone()}</p>
                </div>
            </div>

            // Chat Messages Section
            <div class="card mb-4">
                <div class="card-header">
                    <h4 class="mb-0">
                        <button
                            class="btn btn-link text-decoration-none w-100 text-start"
                            type="button"
                            data-bs-toggle="collapse"
                            data-bs-target="#chatMessagesCollapse"
                        >
                            <i class="bi bi-chat-dots me-2"></i>
                            "Chat Messages"
                            <i class="bi bi-chevron-down float-end"></i>
                        </button>
                    </h4>
                </div>
                <div id="chatMessagesCollapse" class="collapse">
                    <div class="card-body">
                        {move || if !chat_loaded.get() {
                            view! {
                                <button
                                    class="btn btn-primary"
                                    on:click=move |_| set_chat_loaded.set(true)
                                >
                                    "Load Chat Logs"
                                </button>
                            }.into_any()
                        } else {
                            view! {
                                <Suspense fallback=|| view! { <p>"Loading chat logs..."</p> }>
                                    {move || Suspend::new(async move {
                                        chat_resource.await.map(|chat_data| {
                                            if chat_data.is_empty() {
                                                view! { <p>"No chat messages found for this video."</p> }.into_any()
                                            } else {
                                                    view! {
                                                        <div class="table-responsive">
                                                            <table class="table table-sm">
                                                                <thead>
                                                                    <tr>
                                                                        <th>"Time"</th>
                                                                        <th>"Username"</th>
                                                                        <th>"Message"</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody>
                                                                    {chat_data.into_iter().map(|log| {
                                                                        view! {
                                                                            <tr>
                                                                                <td>{format!("{:.0}s", log.offset_seconds)}</td>
                                                                                <td>{log.username}</td>
                                                                                <td>{log.message}</td>
                                                                            </tr>
                                                                        }
                                                                    }).collect_view()}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                    }.into_any()
                                                }
                                        })
                                    })}
                                </Suspense>
                            }.into_any()
                        }}
                    </div>
                </div>
            </div>

            // Transcriptions Section
            <div class="card mb-4">
                <div class="card-header">
                    <h4 class="mb-0">
                        <button
                            class="btn btn-link text-decoration-none w-100 text-start"
                            type="button"
                            data-bs-toggle="collapse"
                            data-bs-target="#transcriptionsCollapse"
                        >
                            <i class="bi bi-file-text me-2"></i>
                            "Transcriptions"
                            <span class="badge bg-secondary ms-2">{video.transcriptions.len()}</span>
                            <i class="bi bi-chevron-down float-end"></i>
                        </button>
                    </h4>
                </div>
                <div id="transcriptionsCollapse" class="collapse">
                    <div class="card-body">
                        {if !video.transcriptions.is_empty() {
                            view! {
                                <div class="mb-4">
                                    <h5>"Transcription Files"</h5>
                                    <table class="table table-striped table-sm">
                                        <thead>
                                            <tr>
                                                <th>"ID"</th>
                                                <th>"Type"</th>
                                                <th>"Source"</th>
                                                <th>"Last Updated"</th>
                                                <th>"Processed"</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {video.transcriptions.iter().map(|t| {
                                                view! {
                                                    <tr>
                                                        <td>{t.id}</td>
                                                        <td>{t.file_extension.clone()}</td>
                                                        <td>{t.source_name.clone()}</td>
                                                        <td>{t.last_updated.clone()}</td>
                                                        <td>
                                                            {if t.processed {
                                                                view! { <span class="badge bg-success">"Processed"</span> }.into_any()
                                                            } else {
                                                                view! { <span class="badge bg-warning">"Pending"</span> }.into_any()
                                                            }}
                                                        </td>
                                                    </tr>
                                                }
                                            }).collect_view()}
                                        </tbody>
                                    </table>
                                </div>

                                // Load segments button
                                {if video.transcriptions.iter().any(|t| t.processed) {
                                    view! {
                                        <hr class="my-4"/>
                                        <div>
                                            {move || if !segments_loaded.get() {
                                                view! {
                                                    <button
                                                        class="btn btn-primary"
                                                        on:click=move |_| set_segments_loaded.set(true)
                                                    >
                                                        "Load Transcription Segments"
                                                    </button>
                                                }.into_any()
                                            } else {
                                                view! {
                                                    <Suspense fallback=|| view! { <p>"Loading segments..."</p> }>
                                                        {move || Suspend::new(async move {
                                                            segments_resource.await.map(|segments| {
                                                                if segments.is_empty() {
                                                                    view! { <p>"No segments found."</p> }.into_any()
                                                                } else {
                                                                        view! {
                                                                            <div class="table-responsive">
                                                                                <table class="table table-sm">
                                                                                    <thead>
                                                                                        <tr>
                                                                                            <th>"Time"</th>
                                                                                            <th>"Text"</th>
                                                                                            <th>"Link"</th>
                                                                                        </tr>
                                                                                    </thead>
                                                                                    <tbody>
                                                                                        {segments.into_iter().map(|seg| {
                                                                                            view! {
                                                                                                <tr>
                                                                                                    <td>{format!("{}s", seg.start)}</td>
                                                                                                    <td>{seg.text}</td>
                                                                                                    <td>
                                                                                                        <a href={seg.timestamp_url} target="_blank" class="btn btn-sm btn-primary">
                                                                                                            <i class="bi bi-play"></i>
                                                                                                        </a>
                                                                                                    </td>
                                                                                                </tr>
                                                                                            }
                                                                                        }).collect_view()}
                                                                                    </tbody>
                                                                                </table>
                                                                            </div>
                                                                        }.into_any()
                                                                    }
                                                            })
                                                        })}
                                                    </Suspense>
                                                }.into_any()
                                            }}
                                        </div>
                                    }.into_any()
                                } else {
                                    view! { <div></div> }.into_any()
                                }}
                            }.into_any()
                        } else {
                            view! {
                                <div class="text-center text-muted py-4">
                                    <i class="bi bi-file-text fs-1 mb-2"></i>
                                    <p>"No transcriptions available for this video."</p>
                                </div>
                            }.into_any()
                        }}
                    </div>
                </div>
            </div>
        </div>
    }
    .into_any()
}
