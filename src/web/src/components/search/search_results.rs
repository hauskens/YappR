use leptos::prelude::*;
use crate::server_fns::{VideoResultData, SegmentResultData};
use chrono::DateTime;

fn format_date(timestamp: i64) -> String {
    DateTime::from_timestamp(timestamp, 0)
        .unwrap()
        .format("%b %d, %Y")
        .to_string()
}

/// Helper function to get platform badge HTML
fn get_platform_badge(platform_name: &str) -> (String, &'static str) {
    match platform_name.to_lowercase().as_str() {
        "youtube" => ("YouTube".to_string(), "danger"),  // Bootstrap red
        "twitch" => ("Twitch".to_string(), "primary"),   // Bootstrap blue/purple
        _ => (platform_name.to_string(), "secondary"),
    }
}

/// Render a single segment result
#[component]
fn SegmentItem(segment: SegmentResultData) -> impl IntoView {
    let url = segment.url.clone();
    let start_time = segment.start_time;
    let formatted_text = segment.formatted_text.clone();

    view! {
        <div class="list-group-item">
            <a
                class="card-text link-primary"
                target="_blank"
                href={url}
            >
                {format!("{}s", start_time)}
            </a>
            <span>" - "{formatted_text}</span>
        </div>
    }
}

/// Render a single video card with its segments
#[component]
fn VideoCard(video_result: VideoResultData) -> impl IntoView {
    let video_id = video_result.video.id.to_string();
    let platform_name = video_result.video.platform_name.clone();
    let (badge_text, badge_color) = get_platform_badge(&platform_name);

    view! {
        <div class="col">
            <div class="card mb-3 shadow" style="width: 325px;">
                // Thumbnail
                <img
                    src={format!("/api/thumbnails/{}", video_id)}
                    alt="Video thumbnail"
                    style="max-width:100%; max-height:250px;"
                    loading="lazy"
                />

                <div class="card-body">
                    // Title
                    <h5 class="card-title">{video_result.video.title.clone()}</h5>

                    // Platform badge and date
                    <div class="mb-2">
                        <span class={format!("badge bg-{} me-2", badge_color)}>
                            {badge_text}
                        </span>
                        <span class="text-muted">
                            {format!("- {}", format_date(video_result.video.uploaded))}
                        </span>
                    </div>

                    // Segments list (scrollable)
                    <div style="max-height: 400px; overflow-y: auto">
                        <div class="list-group list-group-flush">
                            {video_result.segment_results.into_iter().map(|segment| {
                                view! {
                                    <SegmentItem segment={segment} />
                                }
                            }).collect::<Vec<_>>()}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    }
}

/// Search results display component
#[component]
pub fn SearchResults(
    /// The search results to display
    #[prop(into)]
    results: Signal<Option<Vec<VideoResultData>>>,
    /// Whether the search is currently loading
    #[prop(into)]
    loading: Signal<bool>,
) -> impl IntoView {
    view! {
        <div class="mt-4">
            {move || {
                if loading.get() {
                    view! {
                        <div class="d-flex justify-content-center my-5">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">"Searching..."</span>
                            </div>
                        </div>
                    }
                        .into_any()
                } else if let Some(res) = results.get() {
                    if res.is_empty() {
                        view! {
                            <div class="alert alert-info" role="alert">
                                <p class="fw-bold">"No results found"</p>
                                <ul class="mb-0">
                                    <li>"Search for keywords, not sentences"</li>
                                    <li>"Less words = more results"</li>
                                    <li>"Avoid filler words, like \"um\", \"uh\", \"like\", \"so\", \"you know\", etc."</li>
                                    <li>"Remember that transcriptions are not 100% accurate"</li>
                                </ul>
                            </div>
                        }
                            .into_any()
                    } else {
                        let result_count = res.len();
                        let segment_count: usize = res
                            .iter()
                            .map(|r| r.segment_results.len())
                            .sum();
                        view! {
                            <div class="alert alert-success mb-4" role="alert">
                                <strong>
                                    {format!("Found {} segments in {} videos", segment_count, result_count)}
                                </strong>
                            </div>

                            // Video cards grid
                            <div class="row mb-1">
                                {res.into_iter().map(|video_result| {
                                    view! {
                                        <VideoCard video_result={video_result} />
                                    }
                                }).collect::<Vec<_>>()}
                            </div>
                        }
                            .into_any()
                    }
                } else {
                    view! {
                        <div class="text-center text-muted">
                            <p>"Enter a search term and click Search to begin."</p>
                        </div>
                    }
                        .into_any()
                }
            }}

        </div>
    }
}
