use wasm_bindgen::prelude::*;


#[wasm_bindgen]
pub fn convert_timestamps() {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Get all elements with class 'chat-timestamp' and attribute 'data-utc'
    let elements = document.query_selector_all(".chat-timestamp[data-utc]").unwrap();
    
    for i in 0..elements.length() {
        if let Some(element) = elements.get(i) {
            let html_element = element.dyn_into::<web_sys::HtmlElement>().unwrap();
            
            if let Some(utc_time) = html_element.get_attribute("data-utc") {
                // Parse the UTC time string and convert to local time
                if let Ok(timestamp) = utc_time.parse::<f64>() {
                    let date = js_sys::Date::new(&JsValue::from(timestamp));
                    let local_time = date.to_locale_string("en-US", &JsValue::undefined());
                    
                    if let Some(local_string) = local_time.as_string() {
                        html_element.set_text_content(Some(&local_string));
                    }
                } else {
                    // Try parsing as ISO string
                    let date = js_sys::Date::new(&JsValue::from_str(&utc_time));
                    if !date.get_time().is_nan() {
                        let local_time = date.to_locale_string("en-US", &JsValue::undefined());
                        if let Some(local_string) = local_time.as_string() {
                            html_element.set_text_content(Some(&local_string));
                        }
                    }
                }
            }
        }
    }
}

#[wasm_bindgen]
pub fn to_local_time(timestamp: &str) -> String {
    let date = js_sys::Date::new(&JsValue::from_str(timestamp));
    let local_time = date.to_locale_string("en-US", &JsValue::undefined());
    local_time.as_string().unwrap()
}

#[wasm_bindgen]
pub fn show_timezone_modal(import_id: u32, current_timezone: &str) {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Set the form values
    if let Some(import_id_input) = document.get_element_by_id("import-id") {
        let input = import_id_input.dyn_into::<web_sys::HtmlInputElement>().unwrap();
        input.set_value(&import_id.to_string());
    }
    
    if let Some(current_tz_input) = document.get_element_by_id("current-timezone") {
        let input = current_tz_input.dyn_into::<web_sys::HtmlInputElement>().unwrap();
        input.set_value(current_timezone);
    }
    
    if let Some(new_tz_select) = document.get_element_by_id("new-timezone") {
        let select = new_tz_select.dyn_into::<web_sys::HtmlSelectElement>().unwrap();
        select.set_value("");
    }
    
    // Show the modal using Bootstrap
    let window = web_sys::window().unwrap();
    let bootstrap = js_sys::Reflect::get(&window, &JsValue::from_str("bootstrap")).unwrap();
    let modal_class = js_sys::Reflect::get(&bootstrap, &JsValue::from_str("Modal")).unwrap();
    
    if let Some(modal_element) = document.get_element_by_id("timezoneModal") {
        let modal_constructor = modal_class.dyn_into::<js_sys::Function>().unwrap();
        let args = js_sys::Array::new();
        args.push(&modal_element);
        let modal_instance = js_sys::Reflect::construct(&modal_constructor, &args).unwrap();
        
        let show_method = js_sys::Reflect::get(&modal_instance, &JsValue::from_str("show")).unwrap();
        let show_fn = show_method.dyn_into::<js_sys::Function>().unwrap();
        let _ = show_fn.call0(&modal_instance);
    }
}

#[wasm_bindgen]
pub async fn adjust_timezone() -> Result<(), JsValue> {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Get form values
    let import_id = if let Some(element) = document.get_element_by_id("import-id") {
        let input = element.dyn_into::<web_sys::HtmlInputElement>().unwrap();
        input.value()
    } else {
        return Err(JsValue::from_str("Import ID not found"));
    };
    
    let new_timezone = if let Some(element) = document.get_element_by_id("new-timezone") {
        let select = element.dyn_into::<web_sys::HtmlSelectElement>().unwrap();
        select.value()
    } else {
        return Err(JsValue::from_str("New timezone not found"));
    };
    
    if new_timezone.is_empty() {
        let window = web_sys::window().unwrap();
        window.alert_with_message("Please select a new timezone")?;
        return Ok(());
    }
    
    // Get CSRF token
    let csrf_token = if let Some(element) = document.query_selector("input[name=\"csrf_token\"]").unwrap() {
        let input = element.dyn_into::<web_sys::HtmlInputElement>().unwrap();
        input.value()
    } else {
        return Err(JsValue::from_str("CSRF token not found"));
    };
    
    // Prepare request
    let window = web_sys::window().unwrap();
    let request_init = web_sys::RequestInit::new();
    request_init.set_method("POST");
    
    let headers = web_sys::Headers::new()?;
    headers.set("Content-Type", "application/json")?;
    headers.set("X-CSRFToken", &csrf_token)?;
    request_init.set_headers(&headers);
    
    let obj = js_sys::Object::new();
    js_sys::Reflect::set(&obj, &JsValue::from_str("new_timezone"), &JsValue::from_str(&new_timezone))?;
    let body = js_sys::JSON::stringify(&obj)?;
    request_init.set_body(&body);
    
    let url = format!("/utils/chatlog_imports/{}/adjust_timezone", import_id);
    let request = web_sys::Request::new_with_str_and_init(&url, &request_init)?;
    
    let response_value = wasm_bindgen_futures::JsFuture::from(window.fetch_with_request(&request)).await?;
    let response: web_sys::Response = response_value.dyn_into().unwrap();
    
    let json = wasm_bindgen_futures::JsFuture::from(response.json()?).await?;
    
    if let Ok(success) = js_sys::Reflect::get(&json, &JsValue::from_str("success")) {
        if success.as_bool().unwrap_or(false) {
            // Hide the modal
            let bootstrap = js_sys::Reflect::get(&window, &JsValue::from_str("bootstrap")).unwrap();
            let modal_class = js_sys::Reflect::get(&bootstrap, &JsValue::from_str("Modal")).unwrap();
            
            if let Some(modal_element) = document.get_element_by_id("timezoneModal") {
                let get_instance_method = js_sys::Reflect::get(&modal_class, &JsValue::from_str("getInstance")).unwrap();
                let get_instance_fn = get_instance_method.dyn_into::<js_sys::Function>().unwrap();
                let modal_instance = get_instance_fn.call1(&modal_class, &modal_element)?;
                
                let hide_method = js_sys::Reflect::get(&modal_instance, &JsValue::from_str("hide")).unwrap();
                let hide_fn = hide_method.dyn_into::<js_sys::Function>().unwrap();
                let _ = hide_fn.call0(&modal_instance);
            }
            
            // Reload chatlog imports
            load_chatlog_imports().await?;
            
            window.alert_with_message("Timezone adjusted successfully")?;
        } else {
            let error = js_sys::Reflect::get(&json, &JsValue::from_str("error")).unwrap();
            let error_msg = format!("Error: {}", error.as_string().unwrap_or("Unknown error".to_string()));
            window.alert_with_message(&error_msg)?;
        }
    }
    
    Ok(())
}

#[wasm_bindgen]
pub async fn load_chatlog_imports() -> Result<(), JsValue> {
    let window = web_sys::window().unwrap();
    let document = window.document().unwrap();
    
    let response_value = wasm_bindgen_futures::JsFuture::from(
        window.fetch_with_str("/utils/chatlog_imports")
    ).await?;
    let response: web_sys::Response = response_value.dyn_into().unwrap();
    
    let text = wasm_bindgen_futures::JsFuture::from(response.text()?).await?;
    let html = text.as_string().unwrap();
    
    if let Some(container) = document.get_element_by_id("chatlog-imports-container") {
        container.set_inner_html(&html);
    }
    
    Ok(())
}