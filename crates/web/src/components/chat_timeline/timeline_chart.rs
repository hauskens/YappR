use super::types::{load_tag_categories, TagCategory};
use crate::server_fns::ChatLogData;
use leptos::prelude::*;
use std::collections::HashMap;

#[derive(Clone, Copy, PartialEq)]
pub enum TimeInterval {
    Minutes1,
    Minutes5,
    Minutes10,
    Minutes30,
}

impl TimeInterval {
    pub fn to_minutes(&self) -> i64 {
        match self {
            TimeInterval::Minutes1 => 1,
            TimeInterval::Minutes5 => 5,
            TimeInterval::Minutes10 => 10,
            TimeInterval::Minutes30 => 30,
        }
    }

    pub fn to_seconds(&self) -> f64 {
        (self.to_minutes() * 60) as f64
    }
}

#[derive(Clone, Debug)]
struct TimelineBucket {
    start_offset: f64,          // Seconds from video start
    counts_by_category: HashMap<String, usize>,
    total_count: usize,
    first_message_offset: Option<f64>,
}

fn bucket_messages(
    chat_logs: &[ChatLogData],
    interval: TimeInterval,
    categories: &[TagCategory],
    tagged_messages: &HashMap<i32, String>,
) -> Vec<TimelineBucket> {
    let interval_seconds = interval.to_seconds();
    let mut buckets_map: HashMap<i64, TimelineBucket> = HashMap::new();

    for log in chat_logs {
        // Calculate bucket key
        let bucket_key = (log.offset_seconds / interval_seconds).floor() as i64;
        let bucket_start = (bucket_key as f64) * interval_seconds;

        // Get or create bucket
        let bucket = buckets_map.entry(bucket_key).or_insert_with(|| TimelineBucket {
            start_offset: bucket_start,
            counts_by_category: HashMap::new(),
            total_count: 0,
            first_message_offset: None,
        });

        // Determine category for this message
        if let Some(tag_id) = tagged_messages.get(&log.id) {
            if let Some(category) = categories.iter().find(|c| &c.id == tag_id) {
                *bucket
                    .counts_by_category
                    .entry(category.name.clone())
                    .or_insert(0) += 1;
            }
        } else {
            // Untagged message
            *bucket
                .counts_by_category
                .entry("All Messages".to_string())
                .or_insert(0) += 1;
        }

        bucket.total_count += 1;

        if bucket.first_message_offset.is_none() {
            bucket.first_message_offset = Some(log.offset_seconds);
        }
    }

    // Convert to sorted vector
    let mut buckets: Vec<_> = buckets_map.into_values().collect();
    buckets.sort_by(|a, b| a.start_offset.partial_cmp(&b.start_offset).unwrap());

    buckets
}

fn format_time_offset(offset_seconds: f64) -> String {
    let total_seconds = offset_seconds as i64;
    let hours = total_seconds / 3600;
    let minutes = (total_seconds % 3600) / 60;

    if hours > 0 {
        format!("{}:{:02}", hours, minutes)
    } else {
        format!("{}", minutes)
    }
}

#[component]
pub fn TimelineChart(
    #[prop(into)] chat_logs: Signal<Vec<ChatLogData>>,
    platform_url: String,
    platform_name: String,
) -> impl IntoView {
    let (selected_interval, set_selected_interval) = signal(TimeInterval::Minutes5);
    let (categories, set_categories) = signal(Vec::<TagCategory>::new());
    let (tagged_messages, set_tagged_messages) = signal(HashMap::new());

    // Load categories and tagged messages on mount
    Effect::new(move |_| {
        set_categories.set(load_tag_categories());
        set_tagged_messages.set(load_tagged_messages());
    });

    // Listen for tag category changes
    #[cfg(feature = "hydrate")]
    Effect::new(move |_| {
        use wasm_bindgen::closure::Closure;
        use wasm_bindgen::JsCast;

        if let Some(window) = web_sys::window() {
            let listener = Closure::wrap(Box::new(move |_event: web_sys::Event| {
                set_categories.set(load_tag_categories());
            }) as Box<dyn FnMut(_)>);

            let _ = window.add_event_listener_with_callback(
                "tagCategoriesChanged",
                listener.as_ref().unchecked_ref(),
            );

            listener.forget();
        }
    });

    let on_interval_change = move |ev| {
        let value = event_target_value(&ev);
        let interval = match value.as_str() {
            "1" => TimeInterval::Minutes1,
            "5" => TimeInterval::Minutes5,
            "10" => TimeInterval::Minutes10,
            "30" => TimeInterval::Minutes30,
            _ => TimeInterval::Minutes5,
        };
        set_selected_interval.set(interval);
    };

    view! {
        <div class="timeline-chart-component">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5>"Chat Timeline"</h5>
                <div class="d-flex align-items-center">
                    <label class="form-label me-2 mb-0">"Interval:"</label>
                    <select
                        class="form-select form-select-sm"
                        style="width: auto;"
                        on:change=on_interval_change
                        prop:value=move || selected_interval.get().to_minutes().to_string()
                    >
                        <option value="1">"1 minute"</option>
                        <option value="5">"5 minutes"</option>
                        <option value="10">"10 minutes"</option>
                        <option value="30">"30 minutes"</option>
                    </select>
                </div>
            </div>

            {move || {
                let logs = chat_logs.get();
                if logs.is_empty() {
                    view! {
                        <div class="text-center text-muted py-5">
                            "No chat data available for timeline visualization"
                        </div>
                    }.into_any()
                } else {
                    let cats = categories.get();
                    let tagged = tagged_messages.get();
                    let buckets = bucket_messages(
                        &logs,
                        selected_interval.get(),
                        &cats,
                        &tagged,
                    );

                    view! {
                        <div class="chart-container" style="width: 100%;">
                            // Info line
                            <div class="mb-2 small text-muted">
                                {format!("{} time buckets, {} total messages", buckets.len(), logs.len())}
                            </div>

                            // Chart area
                            <div class="border rounded" style="position: relative; height: 350px; overflow: hidden;">
                                {
                                    let max_count = buckets.iter().map(|b| b.total_count).max().unwrap_or(1);

                                    view! {
                                        <>
                                            // Y-axis scale
                                            <div style="position: absolute; left: 5px; top: 20px; bottom: 30px; width: 40px; display: flex; flex-direction: column; justify-content: space-between;">
                                                <div class="text-muted" style="font-size: 0.65rem; text-align: right; padding-right: 5px;">{max_count}</div>
                                                <div class="text-muted" style="font-size: 0.65rem; text-align: right; padding-right: 5px;">{max_count / 2}</div>
                                                <div class="text-muted" style="font-size: 0.65rem; text-align: right; padding-right: 5px;">"0"</div>
                                            </div>

                                            // Y-axis label
                                            <div class="text-muted" style="writing-mode: vertical-lr; transform: rotate(180deg); position: absolute; left: 0px; top: 50%; transform: translateY(-50%) rotate(180deg); font-size: 0.65rem;">
                                                "Messages"
                                            </div>

                                            // Chart content
                                            <div style="display: flex; justify-content: space-around; align-items: flex-end; height: calc(100% - 50px); margin: 20px 10px 30px 50px; gap: 1px;">
                                                {

                                            buckets.iter().map(|bucket| {
                                                let height_pct = if max_count > 0 {
                                                    (bucket.total_count as f64 / max_count as f64 * 100.0).max(2.0)
                                                } else {
                                                    2.0
                                                };

                                                let timestamp_offset = bucket.first_message_offset.unwrap_or(bucket.start_offset);

                                                view! {
                                                    <div style="display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 15px; height: 100%;">
                                                        // Bar container that grows to fill space
                                                        <div style="width: 100%; flex: 1; display: flex; flex-direction: column; justify-content: flex-end;">
                                                            // Bar with click handler
                                                            <div
                                                                style=format!(
                                                                    "background-color: #007bff; width: 100%; height: {}%; border-radius: 2px 2px 0 0; transition: background-color 0.2s; cursor: pointer;",
                                                                    height_pct
                                                                )
                                                            title=format!("{}: {} messages (click to view)", format_time_offset(bucket.start_offset), bucket.total_count)
                                                            class="chart-bar"
                                                            on:click={
                                                                let platform_url = platform_url.clone();
                                                                let platform_name = platform_name.clone();
                                                                let offset_seconds = timestamp_offset;
                                                                move |_| {
                                                                    #[cfg(feature = "hydrate")]
                                                                    {
                                                                        let seconds = offset_seconds as u64;
                                                                        let url = if platform_name.to_lowercase().contains("youtube") {
                                                                            if platform_url.contains('?') {
                                                                                format!("{}&t={}s", platform_url, seconds)
                                                                            } else {
                                                                                format!("{}?t={}s", platform_url, seconds)
                                                                            }
                                                                        } else if platform_name.to_lowercase().contains("twitch") {
                                                                            let hours = seconds / 3600;
                                                                            let minutes = (seconds % 3600) / 60;
                                                                            let secs = seconds % 60;
                                                                            let time_str = if hours > 0 {
                                                                                format!("{}h{}m{}s", hours, minutes, secs)
                                                                            } else if minutes > 0 {
                                                                                format!("{}m{}s", minutes, secs)
                                                                            } else {
                                                                                format!("{}s", secs)
                                                                            };
                                                                            if platform_url.contains('?') {
                                                                                format!("{}&t={}", platform_url, time_str)
                                                                            } else {
                                                                                format!("{}?t={}", platform_url, time_str)
                                                                            }
                                                                        } else {
                                                                            if platform_url.contains('?') {
                                                                                format!("{}&t={}", platform_url, seconds)
                                                                            } else {
                                                                                format!("{}?t={}", platform_url, seconds)
                                                                            }
                                                                        };

                                                                        if let Some(window) = web_sys::window() {
                                                                            let _ = window.open_with_url_and_target(&url, "_blank");
                                                                        }
                                                                    }
                                                                }
                                                            }
                                                        >
                                                        </div>
                                                        </div>

                                                        // Time label below bar
                                                        <div class="text-muted" style="font-size: 0.6rem; margin-top: 2px; height: 25px; white-space: nowrap; transform: rotate(-45deg); transform-origin: center;">
                                                            {format_time_offset(bucket.start_offset)}
                                                        </div>
                                                    </div>
                                                }
                                            }).collect_view()
                                        }
                                            </div>

                                            // X-axis label
                                            <div class="text-muted" style="text-align: center; font-size: 0.65rem; position: absolute; bottom: 5px; left: 50%;">
                                                "Time"
                                            </div>
                                        </>
                                    }
                                }
                            </div>

                            // Add hover effect via style tag
                            <style>
                                ".chart-bar:hover { background-color: #0056b3 !important; }"
                            </style>
                        </div>
                    }.into_any()
                }
            }}
        </div>
    }
}
