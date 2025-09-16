use wasm_bindgen::prelude::*;
use web_sys::{HtmlInputElement, HtmlSelectElement, HtmlButtonElement, Event, HtmlElement};
use wasm_bindgen::JsCast;
use serde::Deserialize;
use gloo_net::http::Request as GlooRequest;

#[derive(Deserialize)]
struct TwitchApiResponse {
    success: bool,
    user_id: Option<String>,
    display_name: Option<String>,
    error: Option<String>,
}

#[wasm_bindgen]
pub fn broadcaster_update_name() {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Try to get elements - handle both admin (input) and non-admin (select) cases
    let channel_input = document.get_element_by_id("twitch_channel");
    let name_input = document.get_element_by_id("name")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    let channel_id_input = document.get_element_by_id("channel_id")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    let channel_name_input = document.get_element_by_id("channel_name")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    
    if let (Some(channel_element), Some(name_input), Some(channel_id_input), Some(channel_name_input)) 
        = (channel_input, name_input, channel_id_input, channel_name_input) {
        
        // Check if it's a select element (non-admin) or input element (admin)
        if let Ok(channel_select) = channel_element.clone().dyn_into::<HtmlSelectElement>() {
            // Non-admin case: dropdown selection
            if !channel_select.value().is_empty() {
                let channel_value = channel_select.value();
                if let Some((channel_id, channel_name)) = parse_channel_value(&channel_value) {
                    name_input.set_value(&channel_name);
                    channel_id_input.set_value(&channel_id);
                    channel_name_input.set_value(&channel_name);
                }
            }
        } else if let Ok(channel_input) = channel_element.dyn_into::<HtmlInputElement>() {
            // Admin case: text input
            let channel_value = channel_input.value();
            if !channel_value.is_empty() {
                // For admin input, suggest the channel name as broadcaster name
                // but don't auto-populate the hidden fields until validated
                name_input.set_value(&channel_value);
            }
        }
    }
    
    broadcaster_check_validity();
}

fn parse_channel_value(value: &str) -> Option<(String, String)> {
    let parts: Vec<&str> = value.split('|').collect();
    if parts.len() == 2 {
        Some((parts[0].to_string(), parts[1].to_string()))
    } else {
        None
    }
}

#[wasm_bindgen]
pub fn broadcaster_check_validity() {
    let document = web_sys::window().unwrap().document().unwrap();
    
    let save_button = document.get_element_by_id("saveButton")
        .and_then(|e| e.dyn_into::<HtmlButtonElement>().ok());
    let willbehave_checkbox = document.get_element_by_id("willbehave")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    let channel_element = document.get_element_by_id("twitch_channel");
    
    if let (Some(save_button), Some(willbehave_checkbox), Some(channel_element)) 
        = (save_button, willbehave_checkbox, channel_element) {
        
        let has_valid_channel = if let Ok(channel_select) = channel_element.clone().dyn_into::<HtmlSelectElement>() {
            // Non-admin case: check if valid option is selected
            let selected_index = channel_select.selected_index();
            selected_index > 0 && !channel_select.value().is_empty()
        } else if let Ok(_channel_input) = channel_element.dyn_into::<HtmlInputElement>() {
            // Admin case: check if channel has been validated (hidden fields populated)
            let channel_id_input = document.get_element_by_id("channel_id")
                .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
            let channel_name_input = document.get_element_by_id("channel_name")
                .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
            
            if let (Some(channel_id), Some(channel_name)) = (channel_id_input, channel_name_input) {
                !channel_id.value().trim().is_empty() && !channel_name.value().trim().is_empty()
            } else {
                false
            }
        } else {
            false
        };
        
        // Enable save button only if willbehave is checked and valid channel is provided
        save_button.set_disabled(!(willbehave_checkbox.checked() && has_valid_channel));
    }
}

#[wasm_bindgen]
pub fn broadcaster_init_form() {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Initial form validation check
    broadcaster_check_validity();
    
    // Set up event listeners
    if let Some(channel_element) = document.get_element_by_id("twitch_channel") {
        // Handle both admin (input) and non-admin (select) cases
        if let Ok(channel_select) = channel_element.clone().dyn_into::<HtmlSelectElement>() {
            // Non-admin case: dropdown selection
            let closure = Closure::wrap(Box::new(move |_event: Event| {
                broadcaster_update_name();
            }) as Box<dyn FnMut(_)>);
            channel_select.set_onchange(Some(closure.as_ref().unchecked_ref()));
            closure.forget();
        } else if let Ok(channel_input) = channel_element.dyn_into::<HtmlInputElement>() {
            // Admin case: text input - set up combined listener
            let closure = Closure::wrap(Box::new(move |_event: Event| {
                broadcaster_update_name();
                clear_channel_validation();
            }) as Box<dyn FnMut(_)>);
            channel_input.set_oninput(Some(closure.as_ref().unchecked_ref()));
            closure.forget();
        }
    }
    
    if let Some(willbehave_element) = document.get_element_by_id("willbehave") {
        let willbehave_input = willbehave_element.dyn_into::<HtmlInputElement>().unwrap();
        let closure = Closure::wrap(Box::new(move |_event: Event| {
            broadcaster_check_validity();
        }) as Box<dyn FnMut(_)>);
        
        willbehave_input.set_onchange(Some(closure.as_ref().unchecked_ref()));
        closure.forget();
    }
    
    // Set up validate button listener
    if let Some(validate_btn) = document.get_element_by_id("validateChannelBtn") {
        let validate_btn = validate_btn.dyn_into::<HtmlButtonElement>().unwrap();
        let closure = Closure::wrap(Box::new(move |_event: Event| {
            wasm_bindgen_futures::spawn_local(async {
                if let Err(e) = validate_twitch_channel().await {
                    web_sys::console::error_1(&e);
                }
            });
        }) as Box<dyn FnMut(_)>);
        
        validate_btn.set_onclick(Some(closure.as_ref().unchecked_ref()));
        closure.forget();
    }
}

#[wasm_bindgen]
pub async fn validate_twitch_channel() -> Result<(), JsValue> {
    let document = web_sys::window().unwrap().document().unwrap();
    
    let channel_input = document.get_element_by_id("twitch_channel")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    let validate_btn = document.get_element_by_id("validateChannelBtn")
        .and_then(|e| e.dyn_into::<HtmlButtonElement>().ok());
    let result_div = document.get_element_by_id("channelValidationResult")
        .and_then(|e| e.dyn_into::<HtmlElement>().ok());
    let channel_id_input = document.get_element_by_id("channel_id")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    let channel_name_input = document.get_element_by_id("channel_name")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok());
    
    if let (Some(channel_input), Some(validate_btn), Some(result_div), Some(channel_id_input), Some(channel_name_input)) = 
        (channel_input, validate_btn, result_div, channel_id_input, channel_name_input) {
        
        let username_value = channel_input.value();
        let username = username_value.trim();
        if username.is_empty() {
            show_validation_result(&result_div, "Please enter a channel username", "warning")?;
            return Ok(());
        }
        
        // Update button state
        validate_btn.set_disabled(true);
        validate_btn.set_inner_html("<i class=\"bi bi-hourglass-split\"></i> Validating...");
        
        // Clear previous results
        result_div.set_inner_html("");
        
        // Make API request using gloo_net
        let url = format!("/api/lookup_twitch_id?username={}", username);
        
        match GlooRequest::get(&url).send().await {
            Ok(response) => {
                if response.ok() {
                    match response.json::<TwitchApiResponse>().await {
                        Ok(api_response) => {
                            if api_response.success {
                                if let (Some(user_id), Some(display_name)) = (api_response.user_id, api_response.display_name) {
                                    // Populate hidden fields
                                    channel_id_input.set_value(&user_id);
                                    channel_name_input.set_value(&display_name);
                                    
                                    show_validation_result(
                                        &result_div,
                                        &format!("✅ Channel validated: <strong>{}</strong> (ID: {})", display_name, user_id),
                                        "success"
                                    )?;
                                    
                                    // Recheck form validity
                                    broadcaster_check_validity();
                                } else {
                                    show_validation_result(&result_div, "❌ Invalid response from server", "danger")?;
                                    clear_hidden_fields(&channel_id_input, &channel_name_input);
                                }
                            } else {
                                let error_msg = api_response.error.unwrap_or_else(|| "Unknown error".to_string());
                                show_validation_result(&result_div, &format!("❌ {}", error_msg), "danger")?;
                                clear_hidden_fields(&channel_id_input, &channel_name_input);
                            }
                        }
                        Err(_) => {
                            show_validation_result(&result_div, "❌ Failed to parse server response", "danger")?;
                            clear_hidden_fields(&channel_id_input, &channel_name_input);
                        }
                    }
                } else {
                    show_validation_result(&result_div, &format!("❌ Server error: {}", response.status()), "danger")?;
                    clear_hidden_fields(&channel_id_input, &channel_name_input);
                }
            }
            Err(_) => {
                show_validation_result(&result_div, "❌ Network error during validation", "danger")?;
                clear_hidden_fields(&channel_id_input, &channel_name_input);
            }
        }
        
        // Restore button state
        validate_btn.set_disabled(false);
        validate_btn.set_inner_html("<i class=\"bi bi-search\"></i> Validate");
    }
    
    Ok(())
}

fn show_validation_result(result_div: &HtmlElement, message: &str, alert_type: &str) -> Result<(), JsValue> {
    let html = format!("<div class=\"alert alert-{}\" role=\"alert\">{}</div>", alert_type, message);
    result_div.set_inner_html(&html);
    Ok(())
}

fn clear_hidden_fields(channel_id_input: &HtmlInputElement, channel_name_input: &HtmlInputElement) {
    channel_id_input.set_value("");
    channel_name_input.set_value("");
}

#[wasm_bindgen]
pub fn clear_channel_validation() {
    let document = web_sys::window().unwrap().document().unwrap();
    
    if let Some(result_div) = document.get_element_by_id("channelValidationResult")
        .and_then(|e| e.dyn_into::<HtmlElement>().ok()) {
        result_div.set_inner_html("");
    }
    
    if let Some(channel_id_input) = document.get_element_by_id("channel_id")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok()) {
        channel_id_input.set_value("");
    }
    
    if let Some(channel_name_input) = document.get_element_by_id("channel_name")
        .and_then(|e| e.dyn_into::<HtmlInputElement>().ok()) {
        channel_name_input.set_value("");
    }
    
    broadcaster_check_validity();
}