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