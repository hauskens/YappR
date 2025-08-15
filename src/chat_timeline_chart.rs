use yew::prelude::*;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};

use chrono::{DateTime, Utc, Timelike};
use wasm_bindgen::{JsValue, JsCast, closure::Closure};
use js_sys::Reflect;

use charming::{Chart, WasmRenderer};
use charming::component::{Axis, Grid, Legend, Title};
use charming::element::{AxisType, Trigger, Tooltip};
use charming::series::Line;

use crate::chat_tag_manager::{TagCategory, load_tag_categories_yew};
use crate::platforms::{PlatformType, get_url_with_timestamp};
use crate::ChatLog;

#[derive(Clone, PartialEq)]
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
}

#[derive(Clone, Debug)]
pub struct TimelineBucket {
    pub timestamp: DateTime<Utc>,
    pub counts_by_category: HashMap<String, usize>,
    pub total_count: usize,
    pub first_message_offset: Option<f64>,
}

#[derive(Clone, Debug)]
pub struct TimelineData {
    pub buckets: Vec<TimelineBucket>,
    pub categories: Vec<TagCategory>,
}

pub fn process_timeline_data(
    chat_logs: &[ChatLog],
    interval: TimeInterval,
    categories: &[TagCategory],
) -> TimelineData {
    let mut buckets_map: HashMap<i64, TimelineBucket> = HashMap::new();
    let interval_minutes = interval.to_minutes();

    for log in chat_logs {
        // Parse timestamp using JavaScript Date API (handles locale format like "5/24/2025, 10:40:29 AM")
        let js_date = js_sys::Date::new(&JsValue::from_str(&log.timestamp));
        
        if !js_date.get_time().is_nan() {
            // Convert JS timestamp (milliseconds) to chrono DateTime
            let timestamp_ms = js_date.get_time() as i64;
            let timestamp_secs = timestamp_ms / 1000;
            let timestamp_nanos = ((timestamp_ms % 1000) * 1_000_000) as u32;
            
            if let Some(timestamp) = DateTime::from_timestamp(timestamp_secs, timestamp_nanos) {
                let timestamp = timestamp.with_timezone(&Utc);
                
                // Round down to interval bucket
                let bucket_timestamp = round_to_interval(timestamp, interval_minutes);
                let bucket_key = bucket_timestamp.timestamp();

                // Get or create bucket
                let bucket = buckets_map.entry(bucket_key).or_insert_with(|| TimelineBucket {
                    timestamp: bucket_timestamp,
                    counts_by_category: HashMap::new(),
                    total_count: 0,
                    first_message_offset: None,
                });

                // Check which categories match this message
                let mut message_matched = false;
                for category in categories {
                    for tag in &category.tags() {
                        if log.message.to_lowercase().contains(&tag.to_lowercase()) {
                            *bucket.counts_by_category.entry(category.name()).or_insert(0) += 1;
                            message_matched = true;
                            break; // Only count once per category
                        }
                    }
                }

                // If no categories match, count as "All Messages"
                if !message_matched || categories.is_empty() {
                    *bucket.counts_by_category.entry("All Messages".to_string()).or_insert(0) += 1;
                }

                bucket.total_count += 1;

                // Store first message offset for click navigation
                if bucket.first_message_offset.is_none() {
                    bucket.first_message_offset = Some(log.offset_seconds);
                }
            }
        }
    }

    // Convert to sorted vector
    let mut buckets: Vec<_> = buckets_map.into_values().collect();
    buckets.sort_by_key(|b| b.timestamp);

    TimelineData {
        buckets,
        categories: categories.to_vec(),
    }
}

fn round_to_interval(timestamp: DateTime<Utc>, interval_minutes: i64) -> DateTime<Utc> {
    let minutes = timestamp.minute() as i64;
    let rounded_minutes = (minutes / interval_minutes) * interval_minutes;
    
    timestamp
        .with_minute(rounded_minutes as u32).unwrap_or(timestamp)
        .with_second(0).unwrap_or(timestamp)
        .with_nanosecond(0).unwrap_or(timestamp)
}

pub fn create_timeline_chart(
    timeline_data: &TimelineData, 
    canvas_id: &str, 
    platform_info: &Option<(PlatformType, String)>
) -> Result<(), String> {
    if timeline_data.buckets.is_empty() {
        return Err("No data to display".to_string());
    }

    // Prepare data for charming
    let x_axis_data: Vec<String> = timeline_data.buckets
        .iter()
        .map(|bucket| bucket.timestamp.format("%H:%M").to_string())
        .collect();

    let mut chart = Chart::new()
        .title(Title::new().text("Chat Messages Over Time"))
        .tooltip(Tooltip::new().trigger(Trigger::Axis))
        .legend(Legend::new().top("30"))
        .grid(Grid::new().left("3%").right("4%").bottom("3%").contain_label(true))
        .animation(false) // Disable animations to prevent glitchy transitions
        .x_axis(
            Axis::new()
                .type_(AxisType::Category)
                .boundary_gap(false)
                .data(x_axis_data)
        )
        .y_axis(
            Axis::new()
                .type_(AxisType::Value)
                .name("Message Count")
        );

    // If we have categories, create separate lines for each
    if !timeline_data.categories.is_empty() {
        for category in &timeline_data.categories {
            let data: Vec<i32> = timeline_data.buckets
                .iter()
                .map(|bucket| bucket.counts_by_category.get(&category.name()).copied().unwrap_or(0) as i32)
                .collect();

            let line_series = Line::new()
                .name(&category.name())
                .data(data)
                .item_style(
                    charming::element::ItemStyle::new()
                        .color(category.color())
                )
                .line_style(
                    charming::element::LineStyle::new()
                        .color(category.color())
                        .width(2)
                );

            chart = chart.series(line_series);
        }
    } else {
        // Show total message count if no categories
        let data: Vec<i32> = timeline_data.buckets
            .iter()
            .map(|bucket| bucket.total_count as i32)
            .collect();

        let line_series = Line::new()
            .name("All Messages")
            .data(data)
            .item_style(
                charming::element::ItemStyle::new()
                    .color("#007bff")
            )
            .line_style(
                charming::element::LineStyle::new()
                    .color("#007bff")
                    .width(2)
            );

        chart = chart.series(line_series);
    }

    // Use charming's WASM renderer
    let renderer = WasmRenderer::new(800, 400);
    let chart_instance = renderer.render(canvas_id, &chart).map_err(|e| format!("Render error: {:?}", e))?;

    // Add click event handler if platform info is available
    if let Some((platform_type, platform_ref)) = platform_info {
        add_chart_click_handler(&chart_instance, timeline_data, platform_type, platform_ref)?;
    }

    Ok(())
}

fn add_chart_click_handler(
    chart_instance: &JsValue,
    timeline_data: &TimelineData,
    platform_type: &PlatformType,
    platform_ref: &str,
) -> Result<(), String> {
    // First, remove any existing click handlers to prevent duplicates
    let off = Reflect::get(chart_instance, &"off".into())
        .map_err(|_| "Chart object should have 'off' method")?
        .dyn_into::<js_sys::Function>()
        .map_err(|_| "'off' should be a function")?;
    
    // Remove all existing click handlers
    let _ = off.call1(chart_instance, &"click".into());
    
    // Clone data for the closure
    let timeline_buckets = timeline_data.buckets.clone();
    let platform_type_clone = platform_type.clone();
    let platform_ref_clone = platform_ref.to_string();
    
    // Create the click handler closure
    let closure = Closure::wrap(Box::new(move |params: JsValue| {
        // Extract dataIndex from the click event parameters
        if let Ok(data_index_val) = Reflect::get(&params, &"dataIndex".into()) {
            if let Some(data_index) = data_index_val.as_f64() {
                let index = data_index as usize;
                
                if let Some(bucket) = timeline_buckets.get(index) {
                    if let Some(offset) = bucket.first_message_offset {
                        let url = get_url_with_timestamp(&platform_type_clone, &platform_ref_clone, offset);
                        
                        // Open the URL in a new tab
                        if let Some(window) = web_sys::window() {
                            let _ = window.open_with_url_and_target(&url, "_blank");
                        }
                    }
                }
            }
        }
    }) as Box<dyn FnMut(JsValue)>);
    
    let js_function: &js_sys::Function = closure.as_ref().unchecked_ref();
    
    // Get the 'on' method from the chart instance
    let on = Reflect::get(chart_instance, &"on".into())
        .map_err(|_| "Chart object should have 'on' method")?
        .dyn_into::<js_sys::Function>()
        .map_err(|_| "'on' should be a function")?;
    
    // Call the 'on' method to add click listener
    on.call2(chart_instance, &"click".into(), js_function)
        .map_err(|e| format!("Failed to call 'on' method: {:?}", e))?;
    
    // Prevent the closure from being dropped
    closure.forget();
    
    Ok(())
}

#[derive(Properties, PartialEq)]
pub struct ChatTimelineChartProps {
    pub chat_logs: Vec<ChatLog>,
    pub platform_info: PlatformType, 
    pub platform_ref: String,
}

#[function_component(ChatTimelineChart)]
pub fn chat_timeline_chart(props: &ChatTimelineChartProps) -> Html {
    let categories = use_state(|| Vec::<TagCategory>::new());
    let error_message = use_state(|| None::<String>);
    let selected_interval = use_state(|| TimeInterval::Minutes5);

    // Load categories on mount and listen for storage changes
    {
        let categories = categories.clone();
        use_effect_with((), move |_| {
            let loaded_categories = load_tag_categories_yew();
            categories.set(loaded_categories);
            
            // Listen for custom events when tag categories are updated
            let categories_for_listener = categories.clone();
            let custom_listener = gloo::events::EventListener::new(
                &web_sys::window().unwrap(),
                "tagCategoriesChanged",
                move |_event| {
                    let updated_categories = load_tag_categories_yew();
                    categories_for_listener.set(updated_categories);
                }
            );
            
            // Store listener to prevent it from being dropped
            std::mem::forget(custom_listener);
        });
    }

    // Update chart when data changes
    {
        let chat_logs = props.chat_logs.clone();
        let categories = categories.clone();
        let error_message = error_message.clone();
        let selected_interval = selected_interval.clone();
        let platform_type = props.platform_info.clone();
        let platform_ref = props.platform_ref.clone();

        let logs_len = chat_logs.len();
        let interval_minutes = selected_interval.to_minutes();
        let cats_len = categories.len();
        
        // Create a simple hash of category data to detect changes
        let cats_hash: u64 = {
            let mut hasher = std::collections::hash_map::DefaultHasher::new();
            for cat in &*categories {
                cat.name().hash(&mut hasher);
                cat.color().hash(&mut hasher);
                for tag in &cat.tags() {
                    tag.hash(&mut hasher);
                }
            }
            hasher.finish()
        };

        use_effect_with((logs_len, interval_minutes, cats_len, cats_hash), move |(_, _, _, _)| {
            if !chat_logs.is_empty() {
                let timeline_data = process_timeline_data(&chat_logs, (*selected_interval).clone(), &*categories);
                let platform_info = Some((platform_type, platform_ref));
                
                // Small delay to ensure DOM is ready
                let error_msg = error_message.clone();
                gloo::timers::callback::Timeout::new(100, move || {
                    match create_timeline_chart(&timeline_data, "chatTimelineChart", &platform_info) {
                        Ok(_) => error_msg.set(None),
                        Err(e) => error_msg.set(Some(e)),
                    }
                }).forget();
            }
        });
    }

    let on_interval_change = {
        let selected_interval = selected_interval.clone();
        Callback::from(move |e: Event| {
            let select: web_sys::HtmlSelectElement = e.target_unchecked_into();
            let interval = match select.value().as_str() {
                "1" => TimeInterval::Minutes1,
                "5" => TimeInterval::Minutes5,
                "10" => TimeInterval::Minutes10,
                "30" => TimeInterval::Minutes30,
                _ => TimeInterval::Minutes5,
            };
            selected_interval.set(interval);
        })
    };

    html! {
        <div class="chat-timeline-chart">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5>{"Chat Timeline"}</h5>
                <div class="d-flex align-items-center">
                    <label class="form-label me-2 mb-0">{"Interval:"}</label>
                    <select 
                        class="form-select form-select-sm" 
                        style="width: auto;"
                        onchange={on_interval_change}
                        value={selected_interval.to_minutes().to_string()}
                    >
                        <option value="1">{"1 minute"}</option>
                        <option value="5" selected={true}>{"5 minutes"}</option>
                        <option value="10">{"10 minutes"}</option>
                        <option value="30">{"30 minutes"}</option>
                    </select>
                </div>
            </div>
            
            if let Some(error) = (*error_message).as_ref() {
                <div class="alert alert-warning">
                    {format!("Chart error: {}", error)}
                </div>
            }
            
            if props.chat_logs.is_empty() {
                <div class="text-center text-muted py-5">
                    {"No chat data available for timeline visualization"}
                </div>
            } else {
                <div class="chart-container" style="position: relative; height: 400px; width: 100%;">
                    <div 
                        id="chatTimelineChart" 
                        style="width: 100%; height: 100%; border: 1px solid #dee2e6; border-radius: 0.375rem;">
                    </div>
                </div>
            }
        </div>
    }
}