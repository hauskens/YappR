use yew::prelude::*;
use wasm_bindgen::prelude::*;
use gloo_net::http::Request;
use web_sys::Event;
use yew::html::TargetCast;
use serde::{Deserialize};

mod utils;
mod platforms;

mod broadcaster_add;
mod broadcaster_edit;
mod chat_tag_manager;
mod chat_timeline_chart;
mod chatlog_search;
mod generic_table;
mod transcription_table;

#[derive(Deserialize, Clone, PartialEq)]
struct ChatLog {
    id: i32,
    username: String,
    message: String,
    timestamp: String,
    offset_seconds: f64,
}

#[derive(Deserialize, Clone)]
struct ChatLogsResponse {
    video_platform_ref: String,
    video_platform_type: String,
    chat_logs: Vec<ChatLog>,
}

#[derive(Clone, PartialEq)]
enum SortField {
    Timestamp,
    Username,
    Message,
}

#[derive(Clone, PartialEq)]
enum SortOrder {
    Asc,
    Desc,
}

#[function_component(ChatLogsTable)]
pub fn chat_logs_table(props: &ChatLogsProps) -> Html {
    let video_id = props.video_id;
    let chat_logs = use_state(|| Vec::<ChatLog>::new());
    let platform_info = use_state(|| None::<(platforms::PlatformType, String)>);
    let search_term = use_state(|| String::new());
    let username_filter = use_state(|| String::new());
    let loading = use_state(|| true);
    let current_page = use_state(|| 1usize);
    let page_size = use_state(|| 50usize);
    let sort_field = use_state(|| SortField::Timestamp);
    let sort_order = use_state(|| SortOrder::Asc);

    {
        let chat_logs = chat_logs.clone();
        let platform_info = platform_info.clone();
        let loading = loading.clone();
        use_effect_with(video_id, move |&video_id| {
            wasm_bindgen_futures::spawn_local(async move {
                match Request::get(&format!("/video/{}/chatlogs", video_id))
                    .send()
                    .await
                {
                    Ok(response) => {
                        if let Ok(mut data) = response.json::<ChatLogsResponse>().await {
                            // Convert timestamps to local time
                            for log in &mut data.chat_logs {
                                log.timestamp = utils::to_local_time(&log.timestamp);
                            }
                            chat_logs.set(data.chat_logs);
                            
                            // Store platform information
                            if let Some(platform_type) = platforms::PlatformType::from_string(&data.video_platform_type) {
                                platform_info.set(Some((platform_type, data.video_platform_ref.clone())));
                            }
                        }
                    }
                    Err(_) => {}
                }
                loading.set(false);
            });
        });
    }

    let filtered_and_sorted_logs = {
        let search = (*search_term).clone();
        let username_filter = (*username_filter).clone();
        let sort_field = (*sort_field).clone();
        let sort_order = (*sort_order).clone();
        
        let mut filtered: Vec<ChatLog> = (*chat_logs).iter()
            .filter(|log| {
                let search_match = if search.is_empty() {
                    true
                } else {
                    log.message.to_lowercase().contains(&search.to_lowercase()) ||
                    log.username.to_lowercase().contains(&search.to_lowercase())
                };
                
                let username_match = if username_filter.is_empty() {
                    true
                } else {
                    log.username == username_filter
                };
                
                search_match && username_match
            })
            .cloned()
            .collect();

        filtered.sort_by(|a, b| {
            let comparison = match sort_field {
                SortField::Timestamp => a.offset_seconds.partial_cmp(&b.offset_seconds).unwrap_or(std::cmp::Ordering::Equal),
                SortField::Username => a.username.cmp(&b.username),
                SortField::Message => a.message.cmp(&b.message),
            };
            
            match sort_order {
                SortOrder::Asc => comparison,
                SortOrder::Desc => comparison.reverse(),
            }
        });
        
        filtered
    };

    let unique_usernames = {
        let mut usernames: Vec<String> = (*chat_logs).iter()
            .map(|log| log.username.clone())
            .collect::<std::collections::HashSet<_>>()
            .into_iter()
            .collect();
        usernames.sort();
        usernames
    };

    let total_filtered = filtered_and_sorted_logs.len();
    let total_pages = (total_filtered + *page_size - 1) / *page_size;
    let start_idx = (*current_page - 1) * *page_size;
    let end_idx = std::cmp::min(start_idx + *page_size, total_filtered);
    
    let paginated_logs = if start_idx < total_filtered {
        filtered_and_sorted_logs[start_idx..end_idx].to_vec()
    } else {
        Vec::new()
    };

    let on_search_input = {
        let search_term = search_term.clone();
        let current_page = current_page.clone();
        Callback::from(move |e: InputEvent| {
            let input: web_sys::HtmlInputElement = e.target_unchecked_into();
            search_term.set(input.value());
            current_page.set(1);
        })
    };

    let on_username_filter_change = {
        let username_filter = username_filter.clone();
        let current_page = current_page.clone();
        Callback::from(move |e: Event| {
            let select: web_sys::HtmlSelectElement = e.target_unchecked_into();
            username_filter.set(select.value());
            current_page.set(1);
        })
    };

    let on_sort_header_click = {
        let sort_field = sort_field.clone();
        let sort_order = sort_order.clone();
        Callback::from(move |field: SortField| {
            if *sort_field == field {
                sort_order.set(match *sort_order {
                    SortOrder::Asc => SortOrder::Desc,
                    SortOrder::Desc => SortOrder::Asc,
                });
            } else {
                sort_field.set(field);
                sort_order.set(SortOrder::Asc);
            }
        })
    };

    let on_page_size_change = {
        let page_size = page_size.clone();
        let current_page = current_page.clone();
        Callback::from(move |e: Event| {
            let select: web_sys::HtmlSelectElement = e.target_unchecked_into();
            if let Ok(new_size) = select.value().parse::<usize>() {
                page_size.set(new_size);
                current_page.set(1);
            }
        })
    };

    let on_page_change = {
        let current_page = current_page.clone();
        Callback::from(move |page: usize| {
            current_page.set(page);
        })
    };

    let on_clear_filters = {
        let search_term = search_term.clone();
        let username_filter = username_filter.clone();
        let current_page = current_page.clone();
        Callback::from(move |_| {
            search_term.set(String::new());
            username_filter.set(String::new());
            current_page.set(1);
        })
    };

    if *loading {
        return html! {
            <div class="text-center">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">{"Loading..."}</span>
                </div>
            </div>
        };
    }

    let sort_icon = |field: SortField| -> Html {
        if *sort_field == field {
            match *sort_order {
                SortOrder::Asc => html! { <i class="fas fa-sort-up ms-1"></i> },
                SortOrder::Desc => html! { <i class="fas fa-sort-down ms-1"></i> },
            }
        } else {
            html! { <i class="fas fa-sort ms-1 text-muted"></i> }
        }
    };

    let has_active_filters = !search_term.is_empty() || !username_filter.is_empty();

    // Generate pagination buttons
    let pagination_buttons = if total_pages > 1 {
        let current = *current_page;
        let max_visible = 7; // Show 7 page numbers max
        let half_visible = max_visible / 2;
        
        let start_page = if current <= half_visible {
            1
        } else if current + half_visible >= total_pages {
            std::cmp::max(1, total_pages - max_visible + 1)
        } else {
            current - half_visible
        };
        
        let end_page = std::cmp::min(total_pages, start_page + max_visible - 1);
        
        let mut pages = Vec::new();
        
        // First page + ellipsis if needed
        if start_page > 1 {
            pages.push(html! {
                <li key={1} class="page-item">
                    <button class="page-link" onclick={
                        let callback = on_page_change.clone();
                        Callback::from(move |_| callback.emit(1))
                    }>
                        {"1"}
                    </button>
                </li>
            });
            
            if start_page > 2 {
                pages.push(html! {
                    <li key={"ellipsis-start"} class="page-item disabled">
                        <span class="page-link">{"..."}</span>
                    </li>
                });
            }
        }
        
        // Main page range
        for page in start_page..=end_page {
            let is_current = page == current;
            pages.push(html! {
                <li key={page} class={classes!("page-item", is_current.then_some("active"))}>
                    <button class="page-link" onclick={
                        let callback = on_page_change.clone();
                        Callback::from(move |_| callback.emit(page))
                    }>
                        {page}
                    </button>
                </li>
            });
        }
        
        // Last page + ellipsis if needed
        if end_page < total_pages {
            if end_page < total_pages - 1 {
                pages.push(html! {
                    <li key={"ellipsis-end"} class="page-item disabled">
                        <span class="page-link">{"..."}</span>
                    </li>
                });
            }
            
            pages.push(html! {
                <li key={total_pages} class="page-item">
                    <button class="page-link" onclick={
                        let callback = on_page_change.clone();
                        Callback::from(move |_| callback.emit(total_pages))
                    }>
                        {total_pages}
                    </button>
                </li>
            });
        }
        
        pages
    } else {
        Vec::new()
    };

    html! {
        <div class="chat-logs-table">
            // Timeline Chart Section
            <div class="mb-4">
                {
                    if let Some((platform_type, platform_ref)) = (*platform_info).as_ref() {
                        html! {
                            <chat_timeline_chart::ChatTimelineChart 
                                chat_logs={(*chat_logs).clone()}
                                platform_info={platform_type.clone()}
                                platform_ref={platform_ref.clone()}
                            />
                        }
                    } else {
                        html! {
                            <chat_timeline_chart::ChatTimelineChart 
                                chat_logs={(*chat_logs).clone()}
                                platform_info={platforms::PlatformType::YouTube}
                                platform_ref={"".to_string()}
                            />
                        }
                    }
                }
            </div>
            
            <div class="row mb-3">
                <div class="col-md-4">
                    <div class="input-group">
                        <input
                            type="text"
                            class="form-control"
                            placeholder="Search messages or usernames..."
                            value={(*search_term).clone()}
                            oninput={on_search_input}
                        />
                        if has_active_filters {
                            <button 
                                class="btn btn-outline-secondary" 
                                type="button"
                                onclick={on_clear_filters}
                                title="Clear all filters"
                            >
                                <i class="fas fa-times"></i>
                            </button>
                        }
                    </div>
                </div>
                <div class="col-md-3">
                    <select class="form-select" onchange={on_username_filter_change} value={(*username_filter).clone()}>
                        <option value="" selected={username_filter.is_empty()}>{"All users"}</option>
                        {for unique_usernames.iter().map(|username| {
                            html! {
                                <option key={username.clone()} value={username.clone()}>
                                    {username}
                                </option>
                            }
                        })}
                    </select>
                </div>
                <div class="col-md-2">
                    <select class="form-select" onchange={on_page_size_change} value={page_size.to_string()}>
                        <option value="25">{"25 per page"}</option>
                        <option value="50" selected={*page_size == 50}>{"50 per page"}</option>
                        <option value="100">{"100 per page"}</option>
                        <option value="200">{"200 per page"}</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <div class="text-muted small mt-2">
                        {format!("Showing {} - {} of {} messages", 
                            if total_filtered > 0 { start_idx + 1 } else { 0 },
                            end_idx,
                            total_filtered
                        )}
                        if has_active_filters {
                            <span class="badge bg-primary ms-2">{"Filtered"}</span>
                        }
                    </div>
                </div>
            </div>
            
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th style="cursor: pointer;" onclick={
                                let callback = on_sort_header_click.clone();
                                Callback::from(move |_| callback.emit(SortField::Timestamp))
                            }>
                                {"Timestamp"} {sort_icon(SortField::Timestamp)}
                            </th>
                            <th style="cursor: pointer;" onclick={
                                let callback = on_sort_header_click.clone();
                                Callback::from(move |_| callback.emit(SortField::Username))
                            }>
                                {"Username"} {sort_icon(SortField::Username)}
                            </th>
                            <th style="cursor: pointer;" onclick={
                                let callback = on_sort_header_click.clone();
                                Callback::from(move |_| callback.emit(SortField::Message))
                            }>
                                {"Message"} {sort_icon(SortField::Message)}
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {for paginated_logs.iter().map(|log| {
                            let timestamp_cell = if let Some((platform_type, platform_ref)) = (*platform_info).as_ref() {
                                let timestamp_url = platforms::get_url_with_timestamp(platform_type, platform_ref, log.offset_seconds);
                                html! {
                                    <a href={timestamp_url} target="_blank" class="text-decoration-none">
                                        {&log.timestamp}
                                    </a>
                                }
                            } else {
                                html! { {&log.timestamp} }
                            };

                            html! {
                                <tr key={log.id}>
                                    <td>{timestamp_cell}</td>
                                    <td>{&log.username}</td>
                                    <td>{&log.message}</td>
                                </tr>
                            }
                        })}
                    </tbody>
                </table>
            </div>
            
            if total_pages > 1 {
                <nav>
                    <ul class="pagination justify-content-center">
                        <li class={classes!("page-item", (*current_page == 1).then_some("disabled"))}>
                            <button class="page-link" onclick={
                                let callback = on_page_change.clone();
                                let current_page = current_page.clone();
                                Callback::from(move |_| {
                                    if *current_page > 1 {
                                        callback.emit(*current_page - 1);
                                    }
                                })
                            }>
                                {"Previous"}
                            </button>
                        </li>
                        
                        {for pagination_buttons}
                        
                        <li class={classes!("page-item", (*current_page == total_pages).then_some("disabled"))}>
                            <button class="page-link" onclick={
                                let callback = on_page_change.clone();
                                let current_page = current_page.clone();
                                Callback::from(move |_| {
                                    if *current_page < total_pages {
                                        callback.emit(*current_page + 1);
                                    }
                                })
                            }>
                                {"Next"}
                            </button>
                        </li>
                    </ul>
                </nav>
            }
        </div>
    }
}

#[derive(Properties, PartialEq)]
pub struct ChatLogsProps {
    pub video_id: i32,
}

#[wasm_bindgen]
pub fn render_chat_logs(video_id: i32, element_id: &str) -> Result<(), String> {
    let document = web_sys::window().unwrap().document().unwrap();
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    yew::Renderer::<ChatLogsTable>::with_root_and_props(
        element, 
        ChatLogsProps { video_id }
    ).render();
    Ok(())
}

#[wasm_bindgen]
pub fn render_component_by_name(component_name: &str, element_id: &str) -> Result<(), String> {
    let window = web_sys::window()
        .ok_or("Failed to get window")?;
    let document = window.document()
        .ok_or("Failed to get document")?;
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    match component_name {
        "tag-categories" => {
            yew::Renderer::<chat_tag_manager::TagCategoryManager>::with_root(element).render();
            Ok(())
        },
        _ => Err(format!("Unknown component: '{}'", component_name))
    }
}

#[wasm_bindgen]
pub fn render_chat_timeline_chart(
    element_id: &str,
    platform_type: &str,
    platform_ref: &str
) -> Result<(), String> {
    let document = web_sys::window().unwrap().document().unwrap();
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    // Parse platform type
    let platform_type_enum = platforms::PlatformType::from_string(platform_type)
        .unwrap_or(platforms::PlatformType::YouTube);
    
    // For now, render with empty data - in real usage, you'd pass the chat logs
    yew::Renderer::<chat_timeline_chart::ChatTimelineChart>::with_root_and_props(
        element,
        chat_timeline_chart::ChatTimelineChartProps {
            chat_logs: Vec::new(),
            platform_info: platform_type_enum,
            platform_ref: platform_ref.to_string(),
        }
    ).render();
    
    Ok(())
}

#[wasm_bindgen]
pub fn render_tag_category_manager(element_id: &str) -> Result<(), String> {
    let document = web_sys::window().unwrap().document().unwrap();
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    yew::Renderer::<chat_tag_manager::TagCategoryManager>::with_root(element).render();
    Ok(())
}

#[wasm_bindgen]
pub fn render_transcription_table(video_id: i32, element_id: &str) -> Result<(), String> {
    transcription_table::render_transcription_table(video_id, element_id)
}

#[wasm_bindgen]
pub fn init_broadcaster_add_form() {
    broadcaster_add::broadcaster_init_form();
}

#[wasm_bindgen] 
pub fn update_broadcaster_name() {
    broadcaster_add::broadcaster_update_name();
}

#[wasm_bindgen]
pub fn check_broadcaster_form_validity() {
    broadcaster_add::broadcaster_check_validity();
}

#[wasm_bindgen]
pub fn render_chatlog_search(channels_json: &str, element_id: &str) -> Result<(), String> {
    chatlog_search::render_chatlog_search(channels_json, element_id)
}

// Broadcaster edit functionality
#[wasm_bindgen]
pub fn init_broadcaster_edit() {
    broadcaster_edit::init_broadcaster_edit();
}

#[wasm_bindgen]
pub fn toggle_twitch_lookup() {
    broadcaster_edit::toggle_twitch_lookup();
}

#[wasm_bindgen]
pub fn lookup_twitch_id() {
    broadcaster_edit::lookup_twitch_id();
}

#[wasm_bindgen]
pub fn show_channel_link_modal(channel_id: i32, channel_name: String, current_source_channel_id: Option<i32>, current_source_channel_name: String) {
    broadcaster_edit::show_channel_link_modal(channel_id, channel_name, current_source_channel_id, current_source_channel_name);
}

#[wasm_bindgen]
pub fn show_enhanced_linking_modal(channel_id: i32, channel_name: String, source_channel_name: String) {
    broadcaster_edit::show_enhanced_linking_modal(channel_id, channel_name, source_channel_name);
}