use wasm_bindgen::prelude::*;
use web_sys::{HtmlElement, HtmlInputElement, HtmlSelectElement, HtmlFormElement, HtmlButtonElement, Event, Element, FormData, File};
use wasm_bindgen::JsCast;
use gloo_net::http::Request;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Clone, Debug)]
struct TwitchLookupResponse {
    success: bool,
    user_id: Option<String>,
    display_name: Option<String>,
    error: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct ChannelInfo {
    id: i32,
    name: String,
    platform_name: String,
}

#[derive(Clone, Debug)]
pub struct BroadcasterEditManager {
    twitch_platform_id: Option<String>,
    csrf_token: Option<String>,
}

impl BroadcasterEditManager {
    pub fn new() -> Self {
        Self {
            twitch_platform_id: None,
            csrf_token: Self::get_csrf_token(),
        }
    }

    fn get_csrf_token() -> Option<String> {
        let document = web_sys::window()?.document()?;
        let token_input = document.query_selector("input[name=\"csrf_token\"]").ok()??;
        let input = token_input.dyn_into::<HtmlInputElement>().ok()?;
        Some(input.value())
    }

    fn get_element_by_id<T: JsCast>(id: &str) -> Option<T> {
        let document = web_sys::window()?.document()?;
        let element = document.get_element_by_id(id)?;
        element.dyn_into::<T>().ok()
    }


    fn show_status_icon(&self, element_id: &str, icon_class: &str, success: bool) {
        if let Some(element) = Self::get_element_by_id::<HtmlElement>(element_id) {
            let color = if success { "text-success" } else { "text-danger" };
            element.set_inner_html(&format!(
                r#"<i class="{} {}" style="font-size: 1.5rem;"></i>"#,
                icon_class, color
            ));
            let _ = element.style().set_property("display", "inline-block");
        }
    }

    pub fn initialize(&mut self) {
        self.find_twitch_platform_id();
        self.setup_event_listeners();
        self.toggle_twitch_lookup();
        self.auto_fade_success_messages();
    }

    fn find_twitch_platform_id(&mut self) {
        if let Some(platform_select) = Self::get_element_by_id::<HtmlSelectElement>("platform_id") {
            for i in 0..platform_select.length() {
                if let Some(option) = platform_select.item(i) {
                    if let Ok(option_element) = option.dyn_into::<web_sys::HtmlOptionElement>() {
                        if let Some(text) = option_element.text_content() {
                            if text.to_lowercase() == "twitch" {
                                self.twitch_platform_id = Some(option_element.value());
                                break;
                            }
                        }
                    }
                }
            }
        }
    }

    fn setup_event_listeners(&self) {
        self.setup_twitch_lookup_listener();
        self.setup_platform_change_listener();
        self.setup_htmx_listeners();
        self.setup_chat_log_listeners();
        self.setup_channel_linking_listeners();
        self.setup_parameter_validation();
    }

    fn setup_twitch_lookup_listener(&self) {
        if let Some(lookup_button) = Self::get_element_by_id::<HtmlButtonElement>("lookup-twitch-id") {
            let manager = self.clone();
            let closure = Closure::wrap(Box::new(move |_: Event| {
                let manager_clone = manager.clone();
                wasm_bindgen_futures::spawn_local(async move {
                    manager_clone.lookup_twitch_id().await;
                });
            }) as Box<dyn FnMut(_)>);
            
            lookup_button.set_onclick(Some(closure.as_ref().unchecked_ref()));
            closure.forget();
        }
    }

    fn setup_platform_change_listener(&self) {
        if let Some(platform_select) = Self::get_element_by_id::<HtmlSelectElement>("platform_id") {
            let manager = self.clone();
            let closure = Closure::wrap(Box::new(move |_: Event| {
                manager.toggle_twitch_lookup();
            }) as Box<dyn FnMut(_)>);
            
            platform_select.set_onchange(Some(closure.as_ref().unchecked_ref()));
            closure.forget();
        }
    }

    fn setup_htmx_listeners(&self) {
        let document = web_sys::window().unwrap().document().unwrap();
        let body = document.body().unwrap();

        // Before request listener
        let before_closure = Closure::wrap(Box::new(move |_: Event| {
            if let Some(spinner) = Self::get_element_by_id::<HtmlElement>("settings-spinner") {
                let _ = spinner.style().set_property("display", "block");
            }
        }) as Box<dyn FnMut(_)>);
        
        let _ = body.add_event_listener_with_callback("htmx:beforeRequest", before_closure.as_ref().unchecked_ref());
        before_closure.forget();

        // After request listener
        let after_closure = Closure::wrap(Box::new(move |_: Event| {
            if let Some(spinner) = Self::get_element_by_id::<HtmlElement>("settings-spinner") {
                let _ = spinner.style().set_property("display", "none");
            }
        }) as Box<dyn FnMut(_)>);
        
        let _ = body.add_event_listener_with_callback("htmx:afterRequest", after_closure.as_ref().unchecked_ref());
        after_closure.forget();
    }

    fn setup_chat_log_listeners(&self) {
        self.setup_file_input_listener();
        self.setup_channel_select_listener();
        self.setup_upload_button_listener();
    }

    fn setup_file_input_listener(&self) {
        if let Some(file_input) = Self::get_element_by_id::<HtmlInputElement>("chatlog-files") {
            let manager = self.clone();
            let closure = Closure::wrap(Box::new(move |_: Event| {
                manager.handle_file_selection();
            }) as Box<dyn FnMut(_)>);
            
            let _ = file_input.add_event_listener_with_callback("change", closure.as_ref().unchecked_ref());
            closure.forget();
        }
    }

    fn setup_channel_select_listener(&self) {
        if let Some(channel_select) = Self::get_element_by_id::<HtmlSelectElement>("channel-select") {
            let manager = self.clone();
            let closure = Closure::wrap(Box::new(move |_: Event| {
                manager.update_upload_button_state();
            }) as Box<dyn FnMut(_)>);
            
            let _ = channel_select.add_event_listener_with_callback("change", closure.as_ref().unchecked_ref());
            closure.forget();
        }
    }

    fn setup_upload_button_listener(&self) {
        if let Some(upload_button) = Self::get_element_by_id::<HtmlButtonElement>("upload-chatlogs") {
            let manager = self.clone();
            let closure = Closure::wrap(Box::new(move |_: Event| {
                let manager_clone = manager.clone();
                wasm_bindgen_futures::spawn_local(async move {
                    manager_clone.upload_chat_logs().await;
                });
            }) as Box<dyn FnMut(_)>);
            
            upload_button.set_onclick(Some(closure.as_ref().unchecked_ref()));
            closure.forget();
        }
    }

    fn setup_channel_linking_listeners(&self) {
        let document = web_sys::window().unwrap().document().unwrap();
        
        // Channel link forms
        let link_forms = document.query_selector_all(r#"form[action*="/channel/"][action$="/link"]:not([action*="/link_videos"])"#).unwrap();
        for i in 0..link_forms.length() {
            if let Some(form_element) = link_forms.get(i) {
                if let Ok(form) = form_element.dyn_into::<HtmlFormElement>() {
                    let manager = self.clone();
                    let closure = Closure::wrap(Box::new(move |event: Event| {
                        event.prevent_default();
                        let manager_clone = manager.clone();
                        let form_clone = event.target().unwrap().dyn_into::<HtmlFormElement>().unwrap();
                        wasm_bindgen_futures::spawn_local(async move {
                            manager_clone.handle_channel_linking_submit(form_clone).await;
                        });
                    }) as Box<dyn FnMut(_)>);
                    
                    let _ = form.add_event_listener_with_callback("submit", closure.as_ref().unchecked_ref());
                    closure.forget();
                }
            }
        }

        // Video linking forms
        let video_forms = document.query_selector_all(r#"form[action*="/link_videos"]"#).unwrap();
        for i in 0..video_forms.length() {
            if let Some(form_element) = video_forms.get(i) {
                if let Ok(form) = form_element.dyn_into::<HtmlFormElement>() {
                    let manager = self.clone();
                    let closure = Closure::wrap(Box::new(move |event: Event| {
                        event.prevent_default();
                        let manager_clone = manager.clone();
                        let form_clone = event.target().unwrap().dyn_into::<HtmlFormElement>().unwrap();
                        wasm_bindgen_futures::spawn_local(async move {
                            manager_clone.handle_video_linking_submit(form_clone).await;
                        });
                    }) as Box<dyn FnMut(_)>);
                    
                    let _ = form.add_event_listener_with_callback("submit", closure.as_ref().unchecked_ref());
                    closure.forget();
                }
            }
        }
    }

    fn setup_parameter_validation(&self) {
        let document = web_sys::window().unwrap().document().unwrap();
        let inputs = document.query_selector_all(r#"input[name="margin_sec"], input[name="min_duration"], input[name="date_margin_hours"]"#).unwrap();
        
        for i in 0..inputs.length() {
            if let Some(input_element) = inputs.get(i) {
                if let Ok(input) = input_element.dyn_into::<HtmlInputElement>() {
                    let manager = self.clone();
                    let input_clone = input.clone();
                    
                    let closure = Closure::wrap(Box::new(move |_: Event| {
                        manager.validate_parameter(&input_clone);
                    }) as Box<dyn FnMut(_)>);
                    
                    let _ = input.add_event_listener_with_callback("input", closure.as_ref().unchecked_ref());
                    let _ = input.add_event_listener_with_callback("change", closure.as_ref().unchecked_ref());
                    closure.forget();
                }
            }
        }
    }

    fn toggle_twitch_lookup(&self) {
        if let (Some(platform_select), Some(lookup_container)) = (
            Self::get_element_by_id::<HtmlSelectElement>("platform_id"),
            Self::get_element_by_id::<HtmlElement>("twitch-lookup-container")
        ) {
            let display = if Some(platform_select.value()) == self.twitch_platform_id {
                "block"
            } else {
                "none"
            };
            let _ = lookup_container.style().set_property("display", display);
        }
    }

    async fn lookup_twitch_id(&self) {
        let username_input = Self::get_element_by_id::<HtmlInputElement>("twitch_username");
        let status_element = Self::get_element_by_id::<HtmlElement>("twitch-lookup-status");
        let platform_ref_input = Self::get_element_by_id::<HtmlInputElement>("platform_ref");
        let channel_id_input = Self::get_element_by_id::<HtmlInputElement>("channel_id");

        if let (Some(username_input), Some(status_element), Some(platform_ref_input), Some(channel_id_input)) =
            (username_input, status_element, platform_ref_input, channel_id_input) {
            
            let username = username_input.value().trim().to_string();
            if username.is_empty() {
                let _ = web_sys::window().unwrap().alert_with_message("Please enter a Twitch username");
                return;
            }

            // Show loading indicator
            status_element.set_inner_html(r#"<div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>"#);
            let _ = status_element.style().set_property("display", "inline-block");

            match self.fetch_twitch_id(&username).await {
                Ok(response) if response.success => {
                    if let Some(user_id) = response.user_id {
                        self.show_status_icon("twitch-lookup-status", "bi bi-check-circle-fill", true);
                        platform_ref_input.set_value(&user_id);
                        channel_id_input.set_value(&user_id);

                        // Auto-fill name if empty
                        if let Some(name_input) = Self::get_element_by_id::<HtmlInputElement>("name") {
                            if name_input.value().trim().is_empty() {
                                if let Some(display_name) = response.display_name {
                                    name_input.set_value(&display_name);
                                }
                            }
                        }
                    }
                }
                _ => {
                    self.show_status_icon("twitch-lookup-status", "bi bi-x-circle-fill", false);
                    web_sys::console::error_1(&JsValue::from_str("Error looking up Twitch ID"));
                }
            }
        }
    }

    async fn fetch_twitch_id(&self, username: &str) -> Result<TwitchLookupResponse, Box<dyn std::error::Error>> {
        let url = format!("/api/lookup_twitch_id?username={}", js_sys::encode_uri_component(username));
        let response = Request::get(&url).send().await?;
        let data: TwitchLookupResponse = response.json().await?;
        Ok(data)
    }

    fn auto_fade_success_messages(&self) {
        let document = web_sys::window().unwrap().document().unwrap();
        
        let closure = Closure::wrap(Box::new(move || {
            let alerts = document.query_selector_all("#settings-feedback .alert-success").unwrap();
            for i in 0..alerts.length() {
                if let Some(alert) = alerts.get(i) {
                    if let Ok(alert_element) = alert.dyn_into::<HtmlElement>() {
                        let _ = alert_element.style().set_property("opacity", "0");
                        
                        let alert_clone = alert_element.clone();
                        let timeout_closure = Closure::wrap(Box::new(move || {
                            alert_clone.remove();
                        }) as Box<dyn FnMut()>);
                        
                        let _ = web_sys::window().unwrap().set_timeout_with_callback_and_timeout_and_arguments_0(
                            timeout_closure.as_ref().unchecked_ref(),
                            300
                        );
                        timeout_closure.forget();
                    }
                }
            }
        }) as Box<dyn FnMut()>);
        
        let _ = web_sys::window().unwrap().set_timeout_with_callback_and_timeout_and_arguments_0(
            closure.as_ref().unchecked_ref(),
            3000
        );
        closure.forget();
    }

    fn handle_file_selection(&self) {
        if let (Some(file_input), Some(file_list), Some(selected_files_list)) = (
            Self::get_element_by_id::<HtmlInputElement>("chatlog-files"),
            Self::get_element_by_id::<HtmlElement>("file-list"),
            Self::get_element_by_id::<HtmlElement>("selected-files")
        ) {
            if let Some(files) = file_input.files() {
                if files.length() > 0 {
                    selected_files_list.set_inner_html("");
                    
                    for i in 0..files.length() {
                        if let Some(file) = files.get(i) {
                            let file_size_kb = (file.size() as f64 / 1024.0).round() as i32;
                            let li_html = format!(
                                r#"<li class="list-group-item d-flex justify-content-between align-items-center">
                                    <span><i class="bi bi-file-text me-2"></i>{}</span>
                                    <span class="badge bg-secondary">{} KB</span>
                                </li>"#,
                                file.name(), file_size_kb
                            );
                            selected_files_list.insert_adjacent_html("beforeend", &li_html).unwrap();
                        }
                    }
                    let _ = file_list.style().set_property("display", "block");
                } else {
                    let _ = file_list.style().set_property("display", "none");
                }
            }
            
            self.update_upload_button_state();
        }
    }

    fn update_upload_button_state(&self) {
        if let (Some(file_input), Some(channel_select), Some(upload_button)) = (
            Self::get_element_by_id::<HtmlInputElement>("chatlog-files"),
            Self::get_element_by_id::<HtmlSelectElement>("channel-select"),
            Self::get_element_by_id::<HtmlButtonElement>("upload-chatlogs")
        ) {
            let has_files = file_input.files().map(|f| f.length() > 0).unwrap_or(false);
            let has_channel = !channel_select.value().is_empty();
            upload_button.set_disabled(!(has_files && has_channel));
        }
    }

    async fn upload_chat_logs(&self) {
        if let (Some(file_input), Some(channel_select)) = (
            Self::get_element_by_id::<HtmlInputElement>("chatlog-files"),
            Self::get_element_by_id::<HtmlSelectElement>("channel-select")
        ) {
            if let Some(files) = file_input.files() {
                let channel_id = channel_select.value();
                
                self.show_upload_progress();
                
                let mut success_count = 0;
                let mut error_count = 0;
                let mut results = Vec::new();

                for i in 0..files.length() {
                    if let Some(file) = files.get(i) {
                        let progress = ((i + 1) as f64 / files.length() as f64 * 100.0).round() as i32;
                        self.update_upload_progress(progress, &file.name(), i + 1, files.length());

                        match self.upload_single_file(&file, &channel_id).await {
                            Ok(message) => {
                                success_count += 1;
                                results.push(format!(r#"<div class="alert alert-success">✓ {}: {}</div>"#, file.name(), message));
                            }
                            Err(error) => {
                                error_count += 1;
                                results.push(format!(r#"<div class="alert alert-danger">✗ {}: {}</div>"#, file.name(), error));
                            }
                        }
                    }
                }

                self.finalize_upload(success_count, error_count, results);
            }
        }
    }

    fn show_upload_progress(&self) {
        if let (Some(progress_div), Some(upload_button), Some(results_div)) = (
            Self::get_element_by_id::<HtmlElement>("upload-progress"),
            Self::get_element_by_id::<HtmlButtonElement>("upload-chatlogs"),
            Self::get_element_by_id::<HtmlElement>("upload-results")
        ) {
            let _ = progress_div.style().set_property("display", "block");
            upload_button.set_disabled(true);
            results_div.set_inner_html("");
        }
    }

    fn update_upload_progress(&self, progress: i32, filename: &str, current: u32, total: u32) {
        if let (Some(progress_bar), Some(status_div)) = (
            Self::get_element_by_id::<HtmlElement>("upload-progress-bar"),
            Self::get_element_by_id::<HtmlElement>("upload-status")
        ) {
            let _ = progress_bar.style().set_property("width", &format!("{}%", progress));
            progress_bar.set_text_content(Some(&format!("{}%", progress)));
            status_div.set_text_content(Some(&format!("Processing {}... ({}/{})", filename, current, total)));
        }
    }

    async fn upload_single_file(&self, file: &File, channel_id: &str) -> Result<String, String> {
        let form_data = FormData::new().map_err(|_| "Failed to create FormData")?;
        let _ = form_data.append_with_blob("chatlog_file", file);
        let _ = form_data.append_with_str("channel_id", channel_id);
        
        if let Some(csrf_token) = &self.csrf_token {
            let _ = form_data.append_with_str("csrf_token", csrf_token);
        }

        let request = Request::post("/api/upload_chatlog")
            .header("X-Requested-With", "fetch")
            .body(form_data).map_err(|e| format!("Request error: {:?}", e))?;

        match request.send().await {
            Ok(response) => {
                if response.ok() {
                    let result: serde_json::Value = response.json().await.map_err(|_| "Failed to parse response")?;
                    if result["success"].as_bool().unwrap_or(false) {
                        Ok(result["message"].as_str().unwrap_or("Success").to_string())
                    } else {
                        Err(result["error"].as_str().unwrap_or("Unknown error").to_string())
                    }
                } else {
                    Err(format!("HTTP error: {}", response.status()))
                }
            }
            Err(_) => Err("Network error".to_string())
        }
    }

    fn finalize_upload(&self, success_count: i32, error_count: i32, results: Vec<String>) {
        if let (Some(status_div), Some(results_div), Some(upload_button)) = (
            Self::get_element_by_id::<HtmlElement>("upload-status"),
            Self::get_element_by_id::<HtmlElement>("upload-results"),
            Self::get_element_by_id::<HtmlButtonElement>("upload-chatlogs")
        ) {
            status_div.set_inner_html(&format!(
                r#"<strong>Upload Complete:</strong> 
                <span class="text-success">{} successful</span>, 
                <span class="text-danger">{} failed</span>"#,
                success_count, error_count
            ));

            results_div.set_inner_html(&results.join(""));
            upload_button.set_disabled(false);

            if success_count > 0 {
                if let Some(file_input) = Self::get_element_by_id::<HtmlInputElement>("chatlog-files") {
                    file_input.set_value("");
                    if let Some(file_list) = Self::get_element_by_id::<HtmlElement>("file-list") {
                        let _ = file_list.style().set_property("display", "none");
                    }
                    self.update_upload_button_state();
                }
            }
        }
    }

    async fn handle_channel_linking_submit(&self, form: HtmlFormElement) {
        if let Some(submit_button) = form.query_selector("button[type=\"submit\"]").unwrap() {
            if let Ok(button) = submit_button.dyn_into::<HtmlButtonElement>() {
                let original_text = button.inner_html();
                button.set_disabled(true);
                button.set_inner_html(r#"<div class="spinner-border spinner-border-sm me-2" role="status"></div>Updating..."#);

                let result = self.submit_form(&form).await;
                
                button.set_disabled(false);
                button.set_inner_html(&original_text);

                match result {
                    Ok(_) => {
                        let _ = web_sys::window().unwrap().alert_with_message("Channel link updated successfully");
                        web_sys::window().unwrap().location().reload().unwrap();
                    }
                    Err(error) => {
                        let _ = web_sys::window().unwrap().alert_with_message(&format!("Error updating channel link: {}", error));
                    }
                }
            }
        }
    }

    async fn handle_video_linking_submit(&self, form: HtmlFormElement) {
        if let Some(submit_button) = form.query_selector("button[type=\"submit\"]").unwrap() {
            if let Ok(button) = submit_button.dyn_into::<HtmlButtonElement>() {
                let original_text = button.inner_html();
                let channel_name = self.get_channel_name_from_form(&form);
                
                button.set_disabled(true);
                button.set_inner_html(r#"<div class="spinner-border spinner-border-sm me-2" role="status"></div>Running..."#);

                let result = self.submit_form(&form).await;
                
                button.set_disabled(false);
                button.set_inner_html(&original_text);

                match result {
                    Ok(_) => {
                        self.show_linking_feedback("success", &format!("Video linking completed for {}. Check the logs for details.", channel_name));
                    }
                    Err(error) => {
                        self.show_linking_feedback("danger", &format!("Error running video linking: {}", error));
                    }
                }
            }
        }
    }

    fn get_channel_name_from_form(&self, form: &HtmlFormElement) -> String {
        if let Ok(Some(channel_card)) = form.closest(".card") {
            if let Some(title) = channel_card.query_selector(".card-title").unwrap() {
                return title.text_content().unwrap_or_else(|| "this channel".to_string());
            }
        }
        "this channel".to_string()
    }

    async fn submit_form(&self, form: &HtmlFormElement) -> Result<(), String> {
        let form_data = FormData::new_with_form(form).map_err(|_| "Failed to create form data")?;
        
        if let Some(csrf_token) = &self.csrf_token {
            let _ = form_data.append_with_str("csrf_token", csrf_token);
        }

        let request = Request::post(&form.action())
            .header("X-Requested-With", "fetch")
            .body(form_data).map_err(|e| format!("Request error: {:?}", e))?;

        match request.send().await {
            Ok(response) => {
                if response.ok() {
                    Ok(())
                } else {
                    Err(format!("HTTP error: {}", response.status()))
                }
            }
            Err(_) => Err("Network error".to_string())
        }
    }

    fn show_linking_feedback(&self, feedback_type: &str, message: &str) {
        let document = web_sys::window().unwrap().document().unwrap();
        
        let feedback_container = if let Some(container) = document.get_element_by_id("linking-feedback") {
            container
        } else {
            let container = document.create_element("div").unwrap();
            container.set_id("linking-feedback");
            container.set_class_name("mt-3");
            
            // Try to insert after first linking form
            if let Some(first_form) = document.query_selector(r#"form[action*="/link_videos"]"#).unwrap() {
                if let Some(parent) = first_form.parent_node() {
                    let _ = parent.insert_before(&container, first_form.next_sibling().as_ref());
                }
            } else if let Some(settings_feedback) = document.get_element_by_id("settings-feedback") {
                let _ = settings_feedback.append_child(&container);
            }
            
            container
        };

        let alert_html = format!(
            r#"<div class="alert alert-{} alert-dismissible fade show">
                {}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>"#,
            feedback_type, message
        );

        feedback_container.set_inner_html(&alert_html);

        // Auto-dismiss success messages
        if feedback_type == "success" {
            let container_clone = feedback_container.clone();
            let closure = Closure::wrap(Box::new(move || {
                if let Some(alert) = container_clone.query_selector(".alert").unwrap() {
                    if let Ok(alert_element) = alert.dyn_into::<HtmlElement>() {
                        alert_element.class_list().remove_1("show").unwrap();
                        
                        let alert_clone = alert_element.clone();
                        let remove_closure = Closure::wrap(Box::new(move || {
                            alert_clone.remove();
                        }) as Box<dyn FnMut()>);
                        
                        let _ = web_sys::window().unwrap().set_timeout_with_callback_and_timeout_and_arguments_0(
                            remove_closure.as_ref().unchecked_ref(),
                            150
                        );
                        remove_closure.forget();
                    }
                }
            }) as Box<dyn FnMut()>);
            
            let _ = web_sys::window().unwrap().set_timeout_with_callback_and_timeout_and_arguments_0(
                closure.as_ref().unchecked_ref(),
                5000
            );
            closure.forget();
        }
    }

    fn validate_parameter(&self, input: &HtmlInputElement) {
        let value = input.value().parse::<i32>().unwrap_or(0);
        let name = input.name();
        
        // Remove existing validation classes
        if let Some(element) = input.dyn_ref::<Element>() {
            let _ = element.class_list().remove_2("is-invalid", "is-valid");
        }
        
        let (is_valid, message) = match name.as_str() {
            "margin_sec" => {
                if value < 0 || value > 20 {
                    (false, "Duration margin should be between 0-20 seconds")
                } else if value > 5 {
                    (true, "High values may create false matches")
                } else {
                    (true, "")
                }
            }
            "min_duration" => {
                if value < 60 {
                    (false, "Minimum duration should be at least 60 seconds")
                } else if value < 300 {
                    (true, "Low values may include short clips")
                } else {
                    (true, "")
                }
            }
            "date_margin_hours" => {
                if value < 1 || value > 168 {
                    (false, "Date margin should be between 1-168 hours (1 week)")
                } else if value > 72 {
                    (true, "Long time windows may create false matches")
                } else {
                    (true, "")
                }
            }
            _ => (true, "")
        };

        if let Some(element) = input.dyn_ref::<Element>() {
            if !is_valid {
                let _ = element.class_list().add_1("is-invalid");
            } else {
                let _ = element.class_list().add_1("is-valid");
            }
        }

        // Handle feedback message
        if let Some(parent) = input.parent_element() {
            let feedback = if let Some(existing) = parent.query_selector(".invalid-feedback").unwrap() {
                existing
            } else {
                let feedback = web_sys::window().unwrap().document().unwrap().create_element("div").unwrap();
                feedback.set_class_name("invalid-feedback");
                let _ = parent.append_child(&feedback);
                feedback
            };

            if !message.is_empty() {
                feedback.set_text_content(Some(message));
                if let Some(html_feedback) = feedback.dyn_ref::<HtmlElement>() {
                    let _ = html_feedback.style().set_property("display", "block");
                }
                
                if is_valid && !message.is_empty() {
                    feedback.set_class_name("form-text text-warning");
                }
            } else {
                if let Some(html_feedback) = feedback.dyn_ref::<HtmlElement>() {
                    let _ = html_feedback.style().set_property("display", "none");
                }
            }
        }
    }
}

// Global functions for modal operations
pub fn show_channel_link_modal(channel_id: i32, channel_name: String, current_source_channel_id: Option<i32>, current_source_channel_name: String) {
    let modal_manager = ModalManager::new();
    modal_manager.show_channel_link_modal(channel_id, &channel_name, current_source_channel_id, &current_source_channel_name);
}

pub fn show_enhanced_linking_modal(channel_id: i32, channel_name: String, source_channel_name: String) {
    let modal_manager = ModalManager::new();
    modal_manager.show_enhanced_linking_modal(channel_id, &channel_name, &source_channel_name);
}

struct ModalManager;

impl ModalManager {
    fn new() -> Self {
        Self
    }

    fn show_channel_link_modal(&self, channel_id: i32, channel_name: &str, current_source_channel_id: Option<i32>, current_source_channel_name: &str) {
        let document = web_sys::window().unwrap().document().unwrap();
        
        if let (Some(_modal), Some(form), Some(save_btn), Some(modal_title), Some(dropdown)) = (
            document.get_element_by_id("channelLinkModal"),
            document.get_element_by_id("channelLinkForm").and_then(|e| e.dyn_into::<HtmlFormElement>().ok()),
            document.get_element_by_id("saveChannelLinkBtn").and_then(|e| e.dyn_into::<HtmlButtonElement>().ok()),
            document.get_element_by_id("channelLinkModalLabel").and_then(|e| e.dyn_into::<HtmlElement>().ok()),
            document.get_element_by_id("modal_link_channel_id").and_then(|e| e.dyn_into::<HtmlSelectElement>().ok())
        ) {
            // Update modal title and form action
            modal_title.set_text_content(Some(&format!("Manage Channel Link - {}", channel_name)));
            form.set_action(&format!("/channel/{}/link", channel_id));
            
            // Populate dropdown
            self.populate_channel_dropdown(&dropdown, channel_id, current_source_channel_id);
            
            // Update preview
            self.update_channel_link_preview(&dropdown, Some(current_source_channel_name));
            
            // Setup change listener
            let dropdown_clone = dropdown.clone();
            let preview_closure = Closure::wrap(Box::new(move |_: Event| {
                ModalManager::new().update_channel_link_preview(&dropdown_clone, None);
            }) as Box<dyn FnMut(_)>);
            dropdown.set_onchange(Some(preview_closure.as_ref().unchecked_ref()));
            preview_closure.forget();
            
            // Setup save button
            self.setup_channel_link_save_button(&save_btn, channel_id, channel_name);
            
            // Show modal
            self.show_bootstrap_modal("channelLinkModal");
        }
    }

    fn populate_channel_dropdown(&self, dropdown: &HtmlSelectElement, current_channel_id: i32, current_source_channel_id: Option<i32>) {
        dropdown.set_inner_html(r#"<option value="None">None (No source channel)</option>"#);
        
        let document = web_sys::window().unwrap().document().unwrap();
        let channel_rows = document.query_selector_all("tbody tr").unwrap();
        
        for i in 0..channel_rows.length() {
            if let Some(row) = channel_rows.get(i) {
                if let Ok(element) = row.dyn_into::<Element>() {
                    if let (Some(id_cell), Some(name_cell)) = (
                        element.query_selector("td:first-child").unwrap(),
                        element.query_selector("td:nth-child(3)").unwrap()
                    ) {
                    let row_channel_id: i32 = id_cell.text_content().unwrap_or_default().parse().unwrap_or(0);
                    let row_channel_name = name_cell.text_content().unwrap_or_default();
                    
                    if row_channel_id != 0 && row_channel_id != current_channel_id && !row_channel_name.is_empty() {
                        let option = document.create_element("option").unwrap();
                        option.set_attribute("value", &row_channel_id.to_string()).unwrap();
                        option.set_text_content(Some(&row_channel_name));
                        
                        if current_source_channel_id == Some(row_channel_id) {
                            option.set_attribute("selected", "selected").unwrap();
                        }
                        
                            let _ = dropdown.append_child(&option);
                        }
                    }
                }
            }
        }
    }

    fn update_channel_link_preview(&self, dropdown: &HtmlSelectElement, current_source_name: Option<&str>) {
        if let Some(preview) = web_sys::window().unwrap().document().unwrap().get_element_by_id("channel-link-preview") {
            let selected_value = dropdown.value();
            let selected_text = dropdown.item(dropdown.selected_index() as u32)
                .and_then(|opt| opt.text_content()).unwrap_or_else(|| "None".to_string());

            let preview_html = if selected_value == "None" {
                r#"<div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    <strong>No source channel:</strong> Enhanced video linking will not be available.
                </div>"#
            } else {
                let is_current = current_source_name.map(|name| selected_text.contains(name)).unwrap_or(false);
                let alert_class = if is_current { "alert-info" } else { "alert-success" };
                let status_text = if is_current { "Current selection" } else { "New selection" };
                
                &format!(r#"<div class="{}">
                    <i class="bi bi-link-45deg me-2"></i>
                    <strong>{}:</strong> Videos will be matched from "{}".
                </div>"#, alert_class, status_text, selected_text)
            };
            
            preview.set_inner_html(preview_html);
        }
    }

    fn setup_channel_link_save_button(&self, save_btn: &HtmlButtonElement, channel_id: i32, channel_name: &str) {
        let channel_id_clone = channel_id;
        let channel_name_clone = channel_name.to_string();
        
        let closure = Closure::wrap(Box::new(move |_: Event| {
            let manager = BroadcasterEditManager::new();
            let channel_name_clone2 = channel_name_clone.clone();
            wasm_bindgen_futures::spawn_local(async move {
                manager.handle_channel_link_submit(channel_id_clone, &channel_name_clone2).await;
            });
        }) as Box<dyn FnMut(_)>);
        
        save_btn.set_onclick(Some(closure.as_ref().unchecked_ref()));
        closure.forget();
    }

    fn show_enhanced_linking_modal(&self, channel_id: i32, channel_name: &str, source_channel_name: &str) {
        let document = web_sys::window().unwrap().document().unwrap();
        
        if let (Some(form), Some(run_btn), Some(modal_title)) = (
            document.get_element_by_id("enhancedLinkingForm").and_then(|e| e.dyn_into::<HtmlFormElement>().ok()),
            document.get_element_by_id("runLinkingBtn").and_then(|e| e.dyn_into::<HtmlButtonElement>().ok()),
            document.get_element_by_id("enhancedLinkingModalLabel").and_then(|e| e.dyn_into::<HtmlElement>().ok())
        ) {
            // Update modal title and form action
            modal_title.set_text_content(Some(&format!("Enhanced Video Linking - {}", channel_name)));
            form.set_action(&format!("/channel/{}/link_videos", channel_id));
            
            // Update description
            if let Some(modal_content) = document.get_element_by_id("linking-modal-content") {
                if let Some(description) = modal_content.query_selector("p").unwrap() {
                    description.set_text_content(Some(&format!(
                        r#"Link videos from "{}" to "{}" using duration matching and title date parsing."#,
                        source_channel_name, channel_name
                    )));
                }
            }
            
            // Setup run button
            self.setup_enhanced_linking_run_button(&run_btn, channel_id, channel_name);
            
            // Show modal
            self.show_bootstrap_modal("enhancedLinkingModal");
        }
    }

    fn setup_enhanced_linking_run_button(&self, run_btn: &HtmlButtonElement, channel_id: i32, channel_name: &str) {
        let channel_id_clone = channel_id;
        let channel_name_clone = channel_name.to_string();
        
        let closure = Closure::wrap(Box::new(move |_: Event| {
            let manager = BroadcasterEditManager::new();
            let channel_name_clone2 = channel_name_clone.clone();
            wasm_bindgen_futures::spawn_local(async move {
                manager.handle_modal_linking_submit(channel_id_clone, &channel_name_clone2).await;
            });
        }) as Box<dyn FnMut(_)>);
        
        run_btn.set_onclick(Some(closure.as_ref().unchecked_ref()));
        closure.forget();
    }

    fn show_bootstrap_modal(&self, modal_id: &str) {
        if let Some(modal_element) = web_sys::window().unwrap().document().unwrap().get_element_by_id(modal_id) {
            let window = web_sys::window().unwrap();
            let bootstrap = js_sys::Reflect::get(&window, &JsValue::from_str("bootstrap")).unwrap();
            let modal_class = js_sys::Reflect::get(&bootstrap, &JsValue::from_str("Modal")).unwrap();
            let modal_constructor = modal_class.dyn_into::<js_sys::Function>().unwrap();
            
            let args = js_sys::Array::new();
            args.push(&modal_element);
            let modal_instance = js_sys::Reflect::construct(&modal_constructor, &args).unwrap();
            
            let show_method = js_sys::Reflect::get(&modal_instance, &JsValue::from_str("show")).unwrap();
            let show_fn = show_method.dyn_into::<js_sys::Function>().unwrap();
            let _ = show_fn.call0(&modal_instance);
        }
    }
}

impl BroadcasterEditManager {
    async fn handle_channel_link_submit(&self, _channel_id: i32, channel_name: &str) {
        if let (Some(form), Some(save_btn), Some(_modal), Some(dropdown)) = (
            Self::get_element_by_id::<HtmlFormElement>("channelLinkForm"),
            Self::get_element_by_id::<HtmlButtonElement>("saveChannelLinkBtn"),
            web_sys::window().unwrap().document().unwrap().get_element_by_id("channelLinkModal"),
            Self::get_element_by_id::<HtmlSelectElement>("modal_link_channel_id")
        ) {
            let selected_value = dropdown.value();
            let selected_text = dropdown.item(dropdown.selected_index() as u32)
                .and_then(|opt| opt.text_content()).unwrap_or_else(|| "None".to_string());
            let original_text = save_btn.inner_html();
            
            // Show loading state
            save_btn.set_disabled(true);
            save_btn.set_inner_html(r#"<div class="spinner-border spinner-border-sm me-2" role="status"></div>Saving..."#);
            
            let result = self.submit_form(&form).await;
            
            // Reset button state
            save_btn.set_disabled(false);
            save_btn.set_inner_html(&original_text);
            
            match result {
                Ok(_) => {
                    // Close modal
                    self.hide_bootstrap_modal("channelLinkModal");
                    
                    let message = if selected_value == "None" {
                        format!("{} unlinked successfully", channel_name)
                    } else {
                        format!(r#"{} linked to "{}" successfully"#, channel_name, selected_text)
                    };
                    
                    let _ = web_sys::window().unwrap().alert_with_message(&message);
                    web_sys::window().unwrap().location().reload().unwrap();
                }
                Err(error) => {
                    let _ = web_sys::window().unwrap().alert_with_message(&format!("Error updating channel link: {}", error));
                }
            }
        }
    }

    async fn handle_modal_linking_submit(&self, _channel_id: i32, channel_name: &str) {
        // Confirm action
        let confirm_message = format!(
            r#"Run enhanced video linking for "{}"?

This will analyze all videos and create links where matches are found."#,
            channel_name
        );
        
        if !web_sys::window().unwrap().confirm_with_message(&confirm_message).unwrap_or(false) {
            return;
        }

        if let (Some(form), Some(run_btn), Some(_modal)) = (
            Self::get_element_by_id::<HtmlFormElement>("enhancedLinkingForm"),
            Self::get_element_by_id::<HtmlButtonElement>("runLinkingBtn"),
            web_sys::window().unwrap().document().unwrap().get_element_by_id("enhancedLinkingModal")
        ) {
            let original_text = run_btn.inner_html();
            
            // Show loading state
            run_btn.set_disabled(true);
            run_btn.set_inner_html(r#"<div class="spinner-border spinner-border-sm me-2" role="status"></div>Running..."#);
            
            let result = self.submit_form(&form).await;
            
            // Reset button state
            run_btn.set_disabled(false);
            run_btn.set_inner_html(&original_text);
            
            match result {
                Ok(_) => {
                    // Close modal
                    self.hide_bootstrap_modal("enhancedLinkingModal");
                    let _ = web_sys::window().unwrap().alert_with_message(&format!("Video linking completed for {}. Check the logs for details.", channel_name));
                }
                Err(error) => {
                    let _ = web_sys::window().unwrap().alert_with_message(&format!("Error running video linking: {}", error));
                }
            }
        }
    }

    fn hide_bootstrap_modal(&self, modal_id: &str) {
        if let Some(modal_element) = web_sys::window().unwrap().document().unwrap().get_element_by_id(modal_id) {
            let window = web_sys::window().unwrap();
            let bootstrap = js_sys::Reflect::get(&window, &JsValue::from_str("bootstrap")).unwrap();
            let modal_class = js_sys::Reflect::get(&bootstrap, &JsValue::from_str("Modal")).unwrap();
            
            let get_instance_method = js_sys::Reflect::get(&modal_class, &JsValue::from_str("getInstance")).unwrap();
            let get_instance_fn = get_instance_method.dyn_into::<js_sys::Function>().unwrap();
            
            if let Ok(modal_instance) = get_instance_fn.call1(&modal_class, &modal_element) {
                let hide_method = js_sys::Reflect::get(&modal_instance, &JsValue::from_str("hide")).unwrap();
                let hide_fn = hide_method.dyn_into::<js_sys::Function>().unwrap();
                let _ = hide_fn.call0(&modal_instance);
            }
        }
    }
}

// Main initialization function
pub fn init_broadcaster_edit() {
    let mut manager = BroadcasterEditManager::new();
    manager.initialize();
}

// Legacy compatibility functions
pub fn toggle_twitch_lookup() {
    let manager = BroadcasterEditManager::new();
    manager.toggle_twitch_lookup();
}

pub fn lookup_twitch_id() {
    let manager = BroadcasterEditManager::new();
    wasm_bindgen_futures::spawn_local(async move {
        manager.lookup_twitch_id().await;
    });
}