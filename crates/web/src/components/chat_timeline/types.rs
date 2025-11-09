use serde::{Deserialize, Serialize};

/// Represents a tag category for classifying chat messages
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TagCategory {
    pub id: String,
    pub name: String,
    pub color: String,         // Hex color code (e.g., "#ff0000")
    pub keywords: Vec<String>, // Keywords to match in messages
}

#[allow(dead_code)]
impl TagCategory {
    pub fn new(name: String, color: String, keywords: Vec<String>) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            name,
            color,
            keywords,
        }
    }
}

/// LocalStorage keys
#[allow(dead_code)]
pub const STORAGE_KEY_TAG_CATEGORIES: &str = "yappr_chat_timeline_tag_categories";

/// Load tag categories from localStorage
#[cfg(feature = "hydrate")]
pub fn load_tag_categories() -> Vec<TagCategory> {
    use wasm_bindgen::JsValue;

    if let Some(window) = web_sys::window()
        && let Ok(Some(storage)) = window.local_storage()
        && let Ok(Some(json)) = storage.get_item(STORAGE_KEY_TAG_CATEGORIES)
    {
        serde_json::from_str(&json).unwrap_or_default()
    } else {
        Vec::new()
    }
}

/// Load tag categories from localStorage (server-side no-op)
#[cfg(not(feature = "hydrate"))]
pub fn load_tag_categories() -> Vec<TagCategory> {
    Vec::new()
}

/// Save tag categories to localStorage
#[cfg(feature = "hydrate")]
pub fn save_tag_categories(categories: &[TagCategory]) {
    if let Some(window) = web_sys::window()
        && let Ok(Some(storage)) = window.local_storage()
    {
        if let Ok(json) = serde_json::to_string(categories) {
            let _ = storage.set_item(STORAGE_KEY_TAG_CATEGORIES, &json);

            // Dispatch custom event to notify other components
            if let Ok(event) = web_sys::CustomEvent::new("tagCategoriesChanged") {
                let _ = window.dispatch_event(&event);
            }
        }
    }
}

/// Save tag categories to localStorage (server-side no-op)
#[cfg(not(feature = "hydrate"))]
#[allow(dead_code)]
pub fn save_tag_categories(_categories: &[TagCategory]) {
    // No-op on server
}

/// Calculate contrast color (black or white) for a given background hex color
#[allow(dead_code)]
pub fn get_contrast_color(hex_color: &str) -> &'static str {
    let hex = hex_color.trim_start_matches('#');

    if hex.len() != 6 {
        return "#000000";
    }

    let r = u8::from_str_radix(&hex[0..2], 16).unwrap_or(0);
    let g = u8::from_str_radix(&hex[2..4], 16).unwrap_or(0);
    let b = u8::from_str_radix(&hex[4..6], 16).unwrap_or(0);

    // YIQ formula for perceived brightness
    let yiq = ((r as f32 * 299.0) + (g as f32 * 587.0) + (b as f32 * 114.0)) / 1000.0;

    if yiq >= 128.0 { "#000000" } else { "#ffffff" }
}
