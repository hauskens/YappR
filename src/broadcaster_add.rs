use wasm_bindgen::prelude::*;
use web_sys::{HtmlInputElement, HtmlSelectElement, HtmlButtonElement, Event};
use wasm_bindgen::JsCast;

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
                // For admin input, we assume they're entering a channel name/username
                // The channel ID and name will be the same initially
                name_input.set_value(&channel_value);
                channel_id_input.set_value(&channel_value);
                channel_name_input.set_value(&channel_value);
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
        } else if let Ok(channel_input) = channel_element.dyn_into::<HtmlInputElement>() {
            // Admin case: check if input has value
            !channel_input.value().trim().is_empty()
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
        let closure = Closure::wrap(Box::new(move |_event: Event| {
            broadcaster_update_name();
        }) as Box<dyn FnMut(_)>);
        
        if let Ok(channel_select) = channel_element.clone().dyn_into::<HtmlSelectElement>() {
            channel_select.set_onchange(Some(closure.as_ref().unchecked_ref()));
        } else if let Ok(channel_input) = channel_element.dyn_into::<HtmlInputElement>() {
            channel_input.set_oninput(Some(closure.as_ref().unchecked_ref()));
        }
        
        closure.forget();
    }
    
    if let Some(willbehave_element) = document.get_element_by_id("willbehave") {
        let willbehave_input = willbehave_element.dyn_into::<HtmlInputElement>().unwrap();
        let closure = Closure::wrap(Box::new(move |_event: Event| {
            broadcaster_check_validity();
        }) as Box<dyn FnMut(_)>);
        
        willbehave_input.set_onchange(Some(closure.as_ref().unchecked_ref()));
        closure.forget();
    }
}