use yew::prelude::*;
use web_sys::{Event, HtmlInputElement, HtmlSelectElement, RequestInit};
use yew::html::TargetCast;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Local, TimeZone};
use wasm_bindgen::JsValue;
use crate::chat_image_generator::{generate_chat_image, save_image_settings, load_image_settings, download_canvas_as_image, copy_canvas_to_clipboard};

#[derive(Deserialize, Clone, PartialEq)]
pub struct ChatLogSearchResult {
    pub id: i32,
    pub username: String,
    pub message: String,
    pub timestamp: String,
    pub channel_id: i32,
    pub channel_name: String,
    pub vod: Option<VodInfo>,
    pub user_color: Option<String>,
}

#[derive(Deserialize, Clone, PartialEq)]
pub struct VodInfo {
    pub video_id: i32,
    pub video_title: String,
    pub platform_ref: String,
    pub timestamp_seconds: i32,
    pub timestamp_formatted: String,
    pub video_url: String,
}

#[derive(Deserialize, Clone)]
pub struct ChatLogSearchResponse {
    pub results: Vec<ChatLogSearchResult>,
    pub total: usize,
    pub query: String,
    pub filters: SearchFilters,
}

#[derive(Deserialize, Clone)]
pub struct SearchFilters {
    pub channel: Option<String>,
    pub username: Option<String>,
    pub date_from: Option<String>,
    pub date_to: Option<String>,
}

#[derive(Serialize)]
struct SearchRequest {
    query: String,
    channel_id: Option<i32>,
    username: Option<String>,
    date_from: Option<String>,
    date_to: Option<String>,
    limit: usize,
}

#[derive(Clone, PartialEq)]
pub struct SearchFormData {
    pub query: String,
    pub channel_id: Option<i32>,
    pub username: String,
    pub date_from: String,
    pub date_to: String,
    pub limit: usize,
}

#[derive(Clone, PartialEq)]
pub struct ImageGeneratorData {
    pub username: String,
    pub message: String,
    pub user_color: String,
    pub message_color: String,
    pub background_color: String,
    pub font_size: u32,
    pub max_width: u32,
    pub show_modal: bool,
}

impl Default for ImageGeneratorData {
    fn default() -> Self {
        Self {
            username: String::new(),
            message: String::new(),
            user_color: "#ff6b6b".to_string(),
            message_color: "#efeff1".to_string(),
            background_color: "#0e0e10".to_string(),
            font_size: 16,
            max_width: 600,
            show_modal: false,
        }
    }
}

impl Default for SearchFormData {
    fn default() -> Self {
        Self {
            query: String::new(),
            channel_id: None,
            username: String::new(),
            date_from: String::new(),
            date_to: String::new(),
            limit: 100,
        }
    }
}

#[derive(Properties, PartialEq)]
pub struct ChatLogSearchProps {
    pub channels: Vec<Channel>,
}

#[derive(Deserialize, Clone, PartialEq)]
pub struct Channel {
    pub id: i32,
    pub name: String,
}

#[function_component(ChatLogSearch)]
pub fn chatlog_search(props: &ChatLogSearchProps) -> Html {
    let search_form = use_state(SearchFormData::default);
    let search_results = use_state(|| None::<ChatLogSearchResponse>);
    let loading = use_state(|| false);
    let error_message = use_state(|| None::<String>);
    let image_generator = use_state(|| {
        // Try to load settings from localStorage
        if let Some(settings_json) = load_image_settings() {
            if let Ok(settings) = serde_json::from_str::<serde_json::Value>(&settings_json) {
                ImageGeneratorData {
                    user_color: settings["user_color"].as_str().unwrap_or("#ff6b6b").to_string(),
                    message_color: settings["message_color"].as_str().unwrap_or("#efeff1").to_string(),
                    background_color: settings["background_color"].as_str().unwrap_or("#0e0e10").to_string(),
                    font_size: settings["font_size"].as_u64().unwrap_or(16) as u32,
                    max_width: settings["max_width"].as_u64().unwrap_or(600) as u32,
                    ..ImageGeneratorData::default()
                }
            } else {
                ImageGeneratorData::default()
            }
        } else {
            ImageGeneratorData::default()
        }
    });
    
    // Auto-update preview when settings change
    {
        let image_generator = image_generator.clone();
        use_effect_with(image_generator.clone(), move |data| {
            if data.show_modal && !data.username.is_empty() && !data.message.is_empty() {
                // Save settings
                save_image_settings(&data.user_color, &data.message_color, &data.background_color, data.font_size, data.max_width);
                
                // Update preview
                if let Ok(canvas) = generate_chat_image(
                    &data.username,
                    &data.user_color,
                    &data.message,
                    &data.message_color,
                    &data.background_color,
                    data.font_size,
                    data.max_width,
                ) {
                    if let Some(document) = web_sys::window().and_then(|w| w.document()) {
                        if let Some(preview_container) = document.get_element_by_id("image-preview") {
                            preview_container.set_inner_html("");
                            let _ = preview_container.append_child(&canvas);
                        }
                    }
                }
            }
            || ()
        });
    }

    let on_form_submit = {
        let search_form = search_form.clone();
        let search_results = search_results.clone();
        let loading = loading.clone();
        let error_message = error_message.clone();
        
        Callback::from(move |e: SubmitEvent| {
            e.prevent_default();
            
            let form_data = (*search_form).clone();
            let search_results = search_results.clone();
            let loading = loading.clone();
            let error_message = error_message.clone();
            
            if form_data.query.trim().is_empty() && form_data.username.trim().is_empty() {
                error_message.set(Some("Please enter either a search query or username".to_string()));
                return;
            }
            
            loading.set(true);
            error_message.set(None);
            
            wasm_bindgen_futures::spawn_local(async move {
                let request_data = SearchRequest {
                    query: form_data.query.clone(),
                    channel_id: form_data.channel_id,
                    username: if form_data.username.is_empty() { None } else { Some(form_data.username.clone()) },
                    date_from: if form_data.date_from.is_empty() { None } else { Some(form_data.date_from.clone()) },
                    date_to: if form_data.date_to.is_empty() { None } else { Some(form_data.date_to.clone()) },
                    limit: form_data.limit,
                };
                
                // Get CSRF token from window.csrfToken
                let csrf_token = web_sys::window()
                    .and_then(|w| js_sys::Reflect::get(&w, &"csrfToken".into()).ok())
                    .and_then(|token| token.as_string());
                
                // Prepare headers
                let headers = web_sys::Headers::new().unwrap();
                headers.set("Content-Type", "application/json").unwrap();
                if let Some(token) = csrf_token {
                    headers.set("X-CSRFToken", &token).unwrap();
                }
                
                // Create request with custom headers
                let opts = RequestInit::new();
                opts.set_method("POST");
                opts.set_headers(&headers);
                opts.set_body(&JsValue::from_str(&serde_json::to_string(&request_data).unwrap()));
                
                let request = web_sys::Request::new_with_str_and_init("/utils/chatlog_search", &opts).unwrap();
                
                match gloo_net::http::Request::from(request).send().await
                {
                    Ok(response) => {
                        if response.ok() {
                            match response.json::<ChatLogSearchResponse>().await {
                                Ok(data) => {
                                    search_results.set(Some(data));
                                }
                                Err(_) => {
                                    error_message.set(Some("Failed to parse search results".to_string()));
                                }
                            }
                        } else {
                            error_message.set(Some(format!("Search failed: {}", response.status())));
                        }
                    }
                    Err(_) => {
                        error_message.set(Some("Network error during search".to_string()));
                    }
                }
                loading.set(false);
            });
        })
    };

    let on_query_input = {
        let search_form = search_form.clone();
        Callback::from(move |e: InputEvent| {
            let input: HtmlInputElement = e.target_unchecked_into();
            let mut form_data = (*search_form).clone();
            form_data.query = input.value();
            search_form.set(form_data);
        })
    };

    let on_channel_change = {
        let search_form = search_form.clone();
        Callback::from(move |e: Event| {
            let select: HtmlSelectElement = e.target_unchecked_into();
            let mut form_data = (*search_form).clone();
            form_data.channel_id = if select.value().is_empty() {
                None
            } else {
                select.value().parse().ok()
            };
            search_form.set(form_data);
        })
    };

    let on_username_input = {
        let search_form = search_form.clone();
        Callback::from(move |e: InputEvent| {
            let input: HtmlInputElement = e.target_unchecked_into();
            let mut form_data = (*search_form).clone();
            form_data.username = input.value();
            search_form.set(form_data);
        })
    };

    let on_date_from_input = {
        let search_form = search_form.clone();
        Callback::from(move |e: InputEvent| {
            let input: HtmlInputElement = e.target_unchecked_into();
            let mut form_data = (*search_form).clone();
            form_data.date_from = input.value();
            search_form.set(form_data);
        })
    };

    let on_date_to_input = {
        let search_form = search_form.clone();
        Callback::from(move |e: InputEvent| {
            let input: HtmlInputElement = e.target_unchecked_into();
            let mut form_data = (*search_form).clone();
            form_data.date_to = input.value();
            search_form.set(form_data);
        })
    };

    let on_limit_change = {
        let search_form = search_form.clone();
        Callback::from(move |e: Event| {
            let select: HtmlSelectElement = e.target_unchecked_into();
            let mut form_data = (*search_form).clone();
            if let Ok(limit) = select.value().parse::<usize>() {
                form_data.limit = limit;
                search_form.set(form_data);
            }
        })
    };

    // Image generator callbacks
    let on_open_image_modal = {
        let image_generator = image_generator.clone();
        Callback::from(move |(username, message, user_color): (String, String, Option<String>)| {
            let mut data = (*image_generator).clone();
            data.username = username;
            data.message = message;
            if let Some(color) = user_color {
                data.user_color = color;
            }
            data.show_modal = true;
            image_generator.set(data);
        })
    };

    let on_close_image_modal = {
        let image_generator = image_generator.clone();
        Callback::from(move |_| {
            let mut data = (*image_generator).clone();
            data.show_modal = false;
            image_generator.set(data);
        })
    };

    let on_color_change = {
        let image_generator = image_generator.clone();
        Callback::from(move |(field, value): (String, String)| {
            let mut data = (*image_generator).clone();
            match field.as_str() {
                "user_color" => data.user_color = value,
                "message_color" => data.message_color = value,
                "background_color" => data.background_color = value,
                _ => {}
            }
            image_generator.set(data);
        })
    };

    let on_font_size_change = {
        let image_generator = image_generator.clone();
        Callback::from(move |size: u32| {
            let mut data = (*image_generator).clone();
            data.font_size = size;
            image_generator.set(data);
        })
    };

    let on_max_width_change = {
        let image_generator = image_generator.clone();
        Callback::from(move |width: u32| {
            let mut data = (*image_generator).clone();
            data.max_width = width;
            image_generator.set(data);
        })
    };

    let render_search_results = |results: &ChatLogSearchResponse| -> Html {
        if results.results.is_empty() {
            return html! {
                <div class="alert alert-info">
                    <i class="bi bi-info-circle me-2"></i>
                    {"No chat messages found matching your search criteria."}
                </div>
            };
        }

        let active_filters = {
            let mut filters = Vec::new();
            if let Some(channel) = &results.filters.channel {
                filters.push(format!("Channel: {}", channel));
            }
            if let Some(username) = &results.filters.username {
                filters.push(format!("Username: {}", username));
            }
            if results.filters.date_from.is_some() || results.filters.date_to.is_some() {
                let date_range = match (&results.filters.date_from, &results.filters.date_to) {
                    (Some(from), Some(to)) => format!("{} to {}", from, to),
                    (Some(from), None) => format!("from {}", from),
                    (None, Some(to)) => format!("to {}", to),
                    _ => String::new(),
                };
                if !date_range.is_empty() {
                    filters.push(format!("Date: {}", date_range));
                }
            }
            filters
        };

        html! {
            <div>
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h6 class="mb-0">{"Search Results"}</h6>
                    <span class="badge bg-success">{format!("{} of {} results", results.results.len(), results.total)}</span>
                </div>
                
                if !active_filters.is_empty() {
                    <div class="alert alert-light small mb-3">
                        <strong>{"Active filters: "}</strong>
                        {active_filters.join(", ")}
                    </div>
                }
                
                <div class="table-responsive">
                    <table class="table table-striped table-hover">
                        <thead class="table">
                            <tr>
                                <th style="width: 140px; min-width: 140px;">{"Time"}</th>
                                <th style="width: 120px; min-width: 120px;">{"Channel"}</th>
                                <th style="width: 120px; min-width: 120px;">{"Username"}</th>
                                <th style="width: auto; max-width: 300px;">{"Message"}</th>
                                <th style="width: 140px; min-width: 140px;">{"VOD Link"}</th>
                                <th style="width: 100px; min-width: 100px;">{"Actions"}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {for results.results.iter().map(|result| {
                                let highlighted_message = highlight_search_terms(&result.message, &results.query);
                                let timestamp = format_timestamp(&result.timestamp);
                                let username = result.username.clone();
                                let message = result.message.clone();
                                let user_color = result.user_color.clone();
                                let on_generate_click = {
                                    let on_open_image_modal = on_open_image_modal.clone();
                                    let username = username.clone();
                                    let message = message.clone();
                                    let user_color = user_color.clone();
                                    Callback::from(move |_: MouseEvent| {
                                        on_open_image_modal.emit((username.clone(), message.clone(), user_color.clone()));
                                    })
                                };
                                
                                html! {
                                    <tr key={result.id}>
                                        <td class="text-muted small text-nowrap">{timestamp}</td>
                                        <td>
                                            <span class="badge bg-secondary text-truncate d-inline-block" style="max-width: 100px;">{&result.channel_name}</span>
                                        </td>
                                        <td class="fw-bold text-truncate" style="max-width: 120px;" title={result.username.clone()}>{&result.username}</td>
                                        <td style="word-wrap: break-word; word-break: break-word; max-width: 300px;">{Html::from_html_unchecked(highlighted_message.into())}</td>
                                        <td class="text-nowrap">
                                            {
                                                if let Some(vod) = &result.vod {
                                                    html! {
                                                        <a href={vod.video_url.clone()} 
                                                           class="btn btn-sm btn-outline-primary text-nowrap" 
                                                           target="_blank"
                                                           title={format!("Watch at {} in: {}", vod.timestamp_formatted, vod.video_title)}>
                                                            <i class="bi bi-play-circle me-1"></i>
                                                            {&vod.timestamp_formatted}
                                                        </a>
                                                    }
                                                } else {
                                                    html! {
                                                        <span class="text-muted small">{"No VOD"}</span>
                                                    }
                                                }
                                            }
                                        </td>
                                        <td>
                                            <button 
                                                class="btn btn-sm btn-outline-success"
                                                onclick={on_generate_click}
                                                title="Generate chat image"
                                            >
                                                <i class="bi bi-image"></i>
                                            </button>
                                        </td>
                                    </tr>
                                }
                            })}
                        </tbody>
                    </table>
                </div>
                
                if results.results.len() < results.total {
                    <div class="alert alert-info mt-3">
                        <i class="bi bi-info-circle me-2"></i>
                        {format!("Showing first {} of {} results. Try refining your search or increasing the result limit.", results.results.len(), results.total)}
                    </div>
                }
            </div>
        }
    };

    // Render image generator modal
    let render_image_modal = || -> Html {
        if !image_generator.show_modal {
            return html! {};
        }

        let on_user_color_change = {
            let on_color_change = on_color_change.clone();
            Callback::from(move |e: Event| {
                let input: HtmlInputElement = e.target_unchecked_into();
                on_color_change.emit(("user_color".to_string(), input.value()));
            })
        };

        let on_message_color_change = {
            let on_color_change = on_color_change.clone();
            Callback::from(move |e: Event| {
                let input: HtmlInputElement = e.target_unchecked_into();
                on_color_change.emit(("message_color".to_string(), input.value()));
            })
        };

        let on_background_color_change = {
            let on_color_change = on_color_change.clone();
            Callback::from(move |e: Event| {
                let input: HtmlInputElement = e.target_unchecked_into();
                on_color_change.emit(("background_color".to_string(), input.value()));
            })
        };

        let on_font_size_input = {
            let on_font_size_change = on_font_size_change.clone();
            Callback::from(move |e: InputEvent| {
                let input: HtmlInputElement = e.target_unchecked_into();
                if let Ok(size) = input.value().parse::<u32>() {
                    on_font_size_change.emit(size);
                }
            })
        };

        let on_max_width_input = {
            let on_max_width_change = on_max_width_change.clone();
            Callback::from(move |e: InputEvent| {
                let input: HtmlInputElement = e.target_unchecked_into();
                if let Ok(width) = input.value().parse::<u32>() {
                    on_max_width_change.emit(width);
                }
            })
        };

        let on_download_image = {
            let image_generator = image_generator.clone();
            Callback::from(move |_: MouseEvent| {
                let data = (*image_generator).clone();
                if let Ok(canvas) = generate_chat_image(
                    &data.username,
                    &data.user_color,
                    &data.message,
                    &data.message_color,
                    &data.background_color,
                    data.font_size,
                    data.max_width,
                ) {
                    let filename = format!("{}_chat.png", data.username.replace(" ", "_"));
                    let _ = download_canvas_as_image(&canvas, &filename);
                }
            })
        };

        let on_copy_image = {
            let image_generator = image_generator.clone();
            Callback::from(move |_: MouseEvent| {
                let data = (*image_generator).clone();
                if let Ok(canvas) = generate_chat_image(
                    &data.username,
                    &data.user_color,
                    &data.message,
                    &data.message_color,
                    &data.background_color,
                    data.font_size,
                    data.max_width,
                ) {
                    wasm_bindgen_futures::spawn_local(async move {
                        if let Err(_) = copy_canvas_to_clipboard(&canvas).await {
                            web_sys::window().unwrap().alert_with_message("Failed to copy to clipboard").unwrap();
                        }
                    });
                }
            })
        };

        html! {
            <div class="modal fade show" style="display: block; background-color: rgba(0,0,0,0.5);">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">{"Generate Chat Image"}</h5>
                            <button type="button" class="btn-close" onclick={on_close_image_modal.clone()}></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <h6>{"Color Settings"}</h6>
                                    <div class="mb-3">
                                        <label class="form-label">{"Username Color"}</label>
                                        <input 
                                            type="color" 
                                            class="form-control form-control-color" 
                                            value={image_generator.user_color.clone()}
                                            onchange={on_user_color_change}
                                        />
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">{"Message Color"}</label>
                                        <input 
                                            type="color" 
                                            class="form-control form-control-color" 
                                            value={image_generator.message_color.clone()}
                                            onchange={on_message_color_change}
                                        />
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">{"Background Color"}</label>
                                        <input 
                                            type="color" 
                                            class="form-control form-control-color" 
                                            value={image_generator.background_color.clone()}
                                            onchange={on_background_color_change}
                                        />
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">{"Font Size"}</label>
                                        <input 
                                            type="range" 
                                            class="form-range" 
                                            min="12" 
                                            max="32" 
                                            value={image_generator.font_size.to_string()}
                                            oninput={on_font_size_input}
                                        />
                                        <small class="text-muted">{format!("{}px", image_generator.font_size)}</small>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">{"Max Width"}</label>
                                        <input 
                                            type="range" 
                                            class="form-range" 
                                            min="300" 
                                            max="1200" 
                                            step="50" 
                                            value={image_generator.max_width.to_string()}
                                            oninput={on_max_width_input}
                                        />
                                        <small class="text-muted">{format!("{}px", image_generator.max_width)}</small>
                                    </div>
                                    <div class="mb-3">
                                        <h6>{"Presets"}</h6>
                                        <div class="btn-group" role="group">
                                            <button type="button" class="btn btn-outline-primary btn-sm" 
                                                onclick={
                                                    let image_generator = image_generator.clone();
                                                    Callback::from(move |_| {
                                                        let mut data = (*image_generator).clone();
                                                        data.user_color = "#9146ff".to_string();
                                                        data.message_color = "#efeff1".to_string();
                                                        data.background_color = "#0e0e10".to_string();
                                                        image_generator.set(data);
                                                    })
                                                }>
                                                {"Twitch"}
                                            </button>
                                            <button type="button" class="btn btn-outline-primary btn-sm"
                                                onclick={
                                                    let image_generator = image_generator.clone();
                                                    Callback::from(move |_| {
                                                        let mut data = (*image_generator).clone();
                                                        data.user_color = "#7289da".to_string();
                                                        data.message_color = "#dcddde".to_string();
                                                        data.background_color = "#36393f".to_string();
                                                        image_generator.set(data);
                                                    })
                                                }>
                                                {"Discord"}
                                            </button>
                                            <button type="button" class="btn btn-outline-primary btn-sm"
                                                onclick={
                                                    let image_generator = image_generator.clone();
                                                    Callback::from(move |_| {
                                                        let mut data = (*image_generator).clone();
                                                        data.user_color = "#00ff00".to_string();
                                                        data.message_color = "#ffffff".to_string();
                                                        data.background_color = "#000000".to_string();
                                                        image_generator.set(data);
                                                    })
                                                }>
                                                {"Classic"}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <h6>{"Preview"}</h6>
                                    <div class="border rounded p-1 mb-1 d-flex justify-content-center align-items-center" style="min-height: 100px; max-height: 200px; overflow: auto;">
                                        <div id="image-preview"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" onclick={on_close_image_modal.clone()}>
                                {"Close"}
                            </button>
                            <button type="button" class="btn btn-outline-primary" onclick={on_copy_image}>
                                <i class="bi bi-clipboard me-2"></i>
                                {"Copy to Clipboard"}
                            </button>
                            <button type="button" class="btn btn-primary" onclick={on_download_image}>
                                <i class="bi bi-download me-2"></i>
                                {"Download Image"}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        }
    };

    html! {
        <div class="chatlog-search">
            {render_image_modal()}
            
            if props.channels.is_empty() {
                <div class="alert alert-warning mb-4">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    <strong>{"No searchable channels available"}</strong>
                    <p class="mb-0">{"Enable chatlog collection under broadcaster channel settings to search chat messages."}</p>
                </div>
            }
            
            <form onsubmit={on_form_submit} class="mb-4">
                <div class="row">
                    <div class="col-md-6 mb-3">
                        <label for="search-query" class="form-label">{"Search Query"}</label>
                        <input 
                            type="text" 
                            class="form-control" 
                            id="search-query" 
                            placeholder="Enter search terms..."
                            value={search_form.query.clone()}
                            oninput={on_query_input}
                            disabled={props.channels.is_empty()}
                        />
                        <div class="form-text">{"Search for specific words or phrases in chat messages. Use quotes (\"exact phrase\") for strict matching. Leave empty to search by username only."}</div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <label for="channel-filter" class="form-label">{"Channel (Optional)"}</label>
                        <select class="form-select" id="channel-filter" onchange={on_channel_change} disabled={props.channels.is_empty()}>
                            <option value="" selected=true>{"All Channels"}</option>
                            {for props.channels.iter().map(|channel| {
                                html! {
                                    <option key={channel.id} value={channel.id.to_string()}>
                                        {&channel.name}
                                    </option>
                                }
                            })}
                        </select>
                    </div>
                    <div class="col-md-3 mb-3">
                        <label for="username-filter" class="form-label">{"Username"}</label>
                        <input 
                            type="text" 
                            class="form-control" 
                            id="username-filter" 
                            placeholder="Filter by username..."
                            value={search_form.username.clone()}
                            oninput={on_username_input}
                            disabled={props.channels.is_empty()}
                        />
                        <div class="form-text small">{"Can be used alone to find all messages from a user"}</div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-md-3 mb-3">
                        <label for="date-from" class="form-label">{"From Date"}</label>
                        <input 
                            type="date" 
                            class="form-control" 
                            id="date-from" 
                            value={search_form.date_from.clone()}
                            oninput={on_date_from_input}
                            disabled={props.channels.is_empty()}
                        />
                    </div>
                    <div class="col-md-3 mb-3">
                        <label for="date-to" class="form-label">{"To Date"}</label>
                        <input 
                            type="date" 
                            class="form-control" 
                            id="date-to" 
                            value={search_form.date_to.clone()}
                            oninput={on_date_to_input}
                            disabled={props.channels.is_empty()}
                        />
                    </div>
                    <div class="col-md-3 mb-3">
                        <label for="limit" class="form-label">{"Max Results"}</label>
                        <select class="form-select" id="limit" onchange={on_limit_change} disabled={props.channels.is_empty()}>
                            <option value="50" selected={search_form.limit == 50}>{"50"}</option>
                            <option value="100" selected={search_form.limit == 100}>{"100"}</option>
                            <option value="250" selected={search_form.limit == 250}>{"250"}</option>
                            <option value="500" selected={search_form.limit == 500}>{"500"}</option>
                        </select>
                    </div>
                    <div class="col-md-3 mb-3 d-flex align-items-end">
                        <button 
                            type="submit" 
                            class="btn btn-success w-100"
                            disabled={*loading || props.channels.is_empty()}
                        >
                            if *loading {
                                <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                            }
                            <i class="bi bi-search me-2"></i>
                            {"Search"}
                        </button>
                    </div>
                </div>
            </form>
            
            <div id="search-results">
                if let Some(error) = (*error_message).as_ref() {
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        {format!("Error: {}", error)}
                    </div>
                } else if *loading {
                    <div class="text-center py-4">
                        <div class="spinner-border text-success" role="status">
                            <span class="visually-hidden">{"Searching..."}</span>
                        </div>
                        <p class="mt-2">{"Searching chat logs..."}</p>
                    </div>
                } else if let Some(results) = (*search_results).as_ref() {
                    {render_search_results(results)}
                } else {
                    <div class="text-center text-muted py-4">
                        <i class="bi bi-chat-dots fs-1 mb-2"></i>
                        <p>{"Enter a search query and/or username above to find chat messages"}</p>
                    </div>
                }
            </div>
        </div>
    }
}

fn highlight_search_terms(message: &str, query: &str) -> String {
    if query.trim().is_empty() {
        return html_escape(message);
    }
    
    let escaped_message = html_escape(message);
    let trimmed_query = query.trim();
    
    // Check if query is enclosed in quotes for strict mode
    if (trimmed_query.starts_with('"') && trimmed_query.ends_with('"') && trimmed_query.len() > 1) ||
       (trimmed_query.starts_with('\'') && trimmed_query.ends_with('\'') && trimmed_query.len() > 1) {
        // Strict mode: search for exact phrase (case insensitive)
        let phrase = &trimmed_query[1..trimmed_query.len()-1]; // Remove quotes
        if !phrase.is_empty() {
            let regex = regex::Regex::new(&format!("(?i){}", regex::escape(phrase))).unwrap();
            return regex.replace_all(&escaped_message, |caps: &regex::Captures| {
                format!("<mark class=\"bg-warning\">{}</mark>", &caps[0])
            }).to_string();
        }
        return escaped_message;
    } else {
        // Normal mode: search for individual terms (case insensitive)
        let terms: Vec<&str> = query.split_whitespace().filter(|t| !t.is_empty()).collect();
        
        let mut result = escaped_message;
        for term in terms {
            let regex = regex::Regex::new(&format!("(?i){}", regex::escape(term))).unwrap();
            result = regex.replace_all(&result, |caps: &regex::Captures| {
                format!("<mark class=\"bg-warning\">{}</mark>", &caps[0])
            }).to_string();
        }
        
        result
    }
}

fn html_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

fn format_timestamp(timestamp: &str) -> String {
    // Try to parse the timestamp and format it nicely
    if let Ok(dt) = DateTime::parse_from_rfc3339(timestamp) {
        let local_dt: DateTime<Local> = dt.into();
        local_dt.format("%m-%d %H:%M:%S").to_string()
    } else {
        // If RFC3339 parsing fails, try parsing without timezone info
        if let Ok(naive_dt) = chrono::NaiveDateTime::parse_from_str(timestamp, "%Y-%m-%dT%H:%M:%S%.f") {
            let local_dt = Local.from_local_datetime(&naive_dt).single().unwrap_or_else(|| Local::now());
            local_dt.format("%m-%d %H:%M:%S").to_string()
        } else {
            // Last resort: just truncate the microseconds and show date/time
            if timestamp.len() >= 19 {
                let truncated = &timestamp[0..16]; // "2025-08-26T16:29"
                if let Ok(naive_dt) = chrono::NaiveDateTime::parse_from_str(&format!("{}:00", truncated), "%Y-%m-%dT%H:%M:%S") {
                    let local_dt = Local.from_local_datetime(&naive_dt).single().unwrap_or_else(|| Local::now());
                    local_dt.format("%m-%d %H:%M:%S").to_string()
                } else {
                    timestamp.to_string()
                }
            } else {
                timestamp.to_string()
            }
        }
    }
}

pub fn render_chatlog_search(channels_json: &str, element_id: &str) -> Result<(), String> {
    let channels: Vec<Channel> = serde_json::from_str(channels_json)
        .map_err(|e| format!("Failed to parse channels JSON: {}", e))?;
    
    let document = web_sys::window().unwrap().document().unwrap();
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    yew::Renderer::<ChatLogSearch>::with_root_and_props(
        element, 
        ChatLogSearchProps { channels }
    ).render();
    Ok(())
}