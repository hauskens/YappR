use wasm_bindgen::prelude::*;
use wasm_bindgen::JsValue;
use serde::{Deserialize, Serialize};
use regex::Regex;
use std::collections::HashMap;

#[wasm_bindgen]
extern "C" {
    fn alert(s: &str);
    
    #[wasm_bindgen(js_namespace = console)]
    fn log(s: &str);
}

macro_rules! console_log {
    ($($t:tt)*) => (log(&format_args!($($t)*).to_string()))
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[wasm_bindgen]
pub struct TagCategory {
    id: String,
    name: String,
    color: String,
    tags: Vec<String>,
}

#[wasm_bindgen]
impl TagCategory {
    #[wasm_bindgen(constructor)]
    pub fn new(id: String, name: String, color: String, tags: Vec<String>) -> TagCategory {
        TagCategory { id, name, color, tags }
    }
    
    #[wasm_bindgen(getter)]
    pub fn id(&self) -> String {
        self.id.clone()
    }
    
    #[wasm_bindgen(getter)]
    pub fn name(&self) -> String {
        self.name.clone()
    }
    
    #[wasm_bindgen(getter)]
    pub fn color(&self) -> String {
        self.color.clone()
    }
    
    #[wasm_bindgen(getter)]
    pub fn tags(&self) -> Vec<String> {
        self.tags.clone()
    }
    
    #[wasm_bindgen(setter)]
    pub fn set_name(&mut self, name: String) {
        self.name = name;
    }
    
    #[wasm_bindgen(setter)]
    pub fn set_color(&mut self, color: String) {
        self.color = color;
    }
    
    #[wasm_bindgen(setter)]
    pub fn set_tags(&mut self, tags: Vec<String>) {
        self.tags = tags;
    }
}

#[wasm_bindgen]
pub fn greet(name: &str) {
    alert(&format!("Hello, {}!", name));
}

#[wasm_bindgen]
pub fn add(a: i32, b: i32) -> i32 {
    console_log!("Adding {} + {}", a, b);
    a + b
}

#[wasm_bindgen]
pub fn fibonacci(n: u32) -> u32 {
    match n {
        0 => 0,
        1 => 1,
        _ => fibonacci(n - 1) + fibonacci(n - 2)
    }
}

#[wasm_bindgen]
pub fn hewwo(user: &str) -> String {
    format!("Hello, {}!", user)
}

#[wasm_bindgen]
pub fn highlight_text(text: &str, search_term: &str) -> String {
    if search_term.is_empty() || text.is_empty() {
        return text.to_string();
    }
    
    // Escape special regex characters
    let escaped_term = regex::escape(search_term);
    
    match Regex::new(&format!("({})", escaped_term)) {
        Ok(re) => re.replace_all(text, "<mark>$1").to_string(),
        Err(_) => text.to_string(), // Return original text if regex fails
    }
}

#[wasm_bindgen]
pub fn get_contrast_yiq(hex_color: &str) -> String {
    let color = if hex_color.starts_with('#') {
        &hex_color[1..]
    } else {
        hex_color
    };
    
    if color.len() != 6 {
        return "#000000".to_string(); // Default to black for invalid colors
    }
    
    // Parse RGB values
    let r = u8::from_str_radix(&color[0..2], 16).unwrap_or(0) as f64;
    let g = u8::from_str_radix(&color[2..4], 16).unwrap_or(0) as f64;
    let b = u8::from_str_radix(&color[4..6], 16).unwrap_or(0) as f64;
    
    // Calculate brightness using YIQ formula
    let yiq = (r * 299.0 + g * 587.0 + b * 114.0) / 1000.0;
    
    // Return black or white depending on brightness
    if yiq >= 128.0 {
        "#000000".to_string()
    } else {
        "#ffffff".to_string()
    }
}

#[wasm_bindgen]
pub fn parse_tag_categories_json(json_string: &str) -> Result<Vec<TagCategory>, String> {
    match serde_json::from_str::<Vec<TagCategory>>(json_string) {
        Ok(categories) => Ok(categories),
        Err(e) => Err(format!("Failed to parse JSON: {}", e))
    }
}

#[wasm_bindgen]
pub fn serialize_tag_categories(categories: Vec<TagCategory>) -> String {
    match serde_json::to_string_pretty(&categories) {
        Ok(json) => json,
        Err(_) => "[]".to_string()
    }
}

#[wasm_bindgen]
pub fn validate_tag_category_data(json_string: &str) -> bool {
    match serde_json::from_str::<Vec<TagCategory>>(json_string) {
        Ok(categories) => {
            // Additional validation logic
            categories.iter().all(|cat| {
                !cat.id.is_empty() && !cat.name.is_empty() && !cat.color.is_empty()
            })
        }
        Err(_) => false
    }
}

#[wasm_bindgen]
pub fn process_tag_string(tags_text: &str) -> Vec<String> {
    tags_text
        .split(',')
        .map(|tag| tag.trim().replace(' ', ""))
        .filter(|tag| !tag.is_empty())
        .collect()
}

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

// Tag Category Management Functions
#[wasm_bindgen]
pub fn load_tag_categories() -> Vec<TagCategory> {
    let window = web_sys::window().unwrap();
    let storage = window.local_storage().unwrap().unwrap();
    
    match storage.get_item("tagCategories") {
        Ok(Some(stored)) => {
            match serde_json::from_str::<Vec<TagCategory>>(&stored) {
                Ok(categories) => categories,
                Err(_) => {
                    console_log!("Failed to parse tag categories from localStorage");
                    Vec::new()
                }
            }
        }
        _ => Vec::new()
    }
}

#[wasm_bindgen]
pub fn save_tag_categories(categories: Vec<TagCategory>) {
    let window = web_sys::window().unwrap();
    let storage = window.local_storage().unwrap().unwrap();
    
    let json = serialize_tag_categories(categories.clone());
    let _ = storage.set_item("tagCategories", &json);
    
    render_tag_categories(categories);
}

#[wasm_bindgen]
pub fn render_tag_categories(categories: Vec<TagCategory>) {
    let document = web_sys::window().unwrap().document().unwrap();
    let container = document.get_element_by_id("tagCategoriesContainer").unwrap();
    let no_tags_msg = document.get_element_by_id("noCategoriesMsg");
    
    // Clear current categories (except for the noTagsMsg)
    let children: Vec<web_sys::Element> = (0..container.children().length())
        .filter_map(|i| container.children().item(i))
        .filter(|child| child.id() != "noCategoriesMsg")
        .collect();
    
    for child in children {
        container.remove_child(&child).ok();
    }
    
    if categories.is_empty() {
        if let Some(msg) = no_tags_msg {
            msg.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("display", "block").ok();
        }
        return;
    }
    
    if let Some(msg) = no_tags_msg {
        msg.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("display", "none").ok();
    }
    
    // Create badges for each category
    for category in categories {
        let badge = document.create_element("div").unwrap();
        badge.set_class_name("badge rounded-pill d-inline-flex align-items-center me-2 mb-2");
        
        let style = badge.dyn_ref::<web_sys::HtmlElement>().unwrap().style();
        style.set_property("background-color", &category.color).ok();
        style.set_property("color", &get_contrast_yiq(&category.color)).ok();
        style.set_property("font-size", "0.9rem").ok();
        style.set_property("padding", "0.5em 0.8em").ok();
        
        // Name span
        let name_span = document.create_element("span").unwrap();
        name_span.set_text_content(Some(&category.name));
        name_span.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("margin-right", "5px").ok();
        badge.append_child(&name_span).ok();
        
        // Tags count
        let tags_count = document.create_element("span").unwrap();
        tags_count.set_text_content(Some(&format!("({} tags)", category.tags.len())));
        tags_count.set_class_name("small opacity-75");
        badge.append_child(&tags_count).ok();
        
        // Edit button
        let edit_btn = document.create_element("button").unwrap();
        edit_btn.set_class_name("btn btn-sm ms-2 p-0");
        edit_btn.set_inner_html("<i class=\"bi bi-pencil-fill\" style=\"font-size: 0.8rem;\"></i>");
        edit_btn.set_attribute("onclick", &format!("editCategory('{}')", category.id)).ok();
        edit_btn.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("line-height", "1").ok();
        edit_btn.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("color", &get_contrast_yiq(&category.color)).ok();
        badge.append_child(&edit_btn).ok();
        
        // Delete button
        let delete_btn = document.create_element("button").unwrap();
        delete_btn.set_class_name("btn btn-sm ms-1 p-0");
        delete_btn.set_inner_html("<i class=\"bi bi-x-lg\" style=\"font-size: 0.8rem;\"></i>");
        delete_btn.set_attribute("onclick", &format!("deleteCategory('{}')", category.id)).ok();
        delete_btn.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("line-height", "1").ok();
        delete_btn.dyn_ref::<web_sys::HtmlElement>().unwrap().style().set_property("color", &get_contrast_yiq(&category.color)).ok();
        badge.append_child(&delete_btn).ok();
        
        container.append_child(&badge).ok();
    }
}

#[wasm_bindgen]
pub fn open_add_category_modal() {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Reset form
    if let Some(name_input) = document.get_element_by_id("categoryName") {
        name_input.dyn_ref::<web_sys::HtmlInputElement>().unwrap().set_value("");
    }
    if let Some(color_input) = document.get_element_by_id("categoryColor") {
        color_input.dyn_ref::<web_sys::HtmlInputElement>().unwrap().set_value("#007bff");
    }
    if let Some(tags_input) = document.get_element_by_id("categoryTags") {
        tags_input.dyn_ref::<web_sys::HtmlTextAreaElement>().unwrap().set_value("");
    }
    if let Some(id_input) = document.get_element_by_id("editCategoryId") {
        id_input.dyn_ref::<web_sys::HtmlInputElement>().unwrap().set_value("");
    }
    
    // Update modal title
    if let Some(modal_title) = document.get_element_by_id("tagCategoryModalLabel") {
        modal_title.set_text_content(Some("Add Tag Category"));
    }
    
    // Show modal using Bootstrap
    let js_code = "new bootstrap.Modal(document.getElementById('tagCategoryModal')).show()";
    js_sys::eval(js_code).ok();
}

#[wasm_bindgen]
pub fn edit_category_modal(category_id: &str) {
    let document = web_sys::window().unwrap().document().unwrap();
    let categories = load_tag_categories();
    
    let category = categories.iter().find(|c| c.id == category_id);
    if let Some(cat) = category {
        // Fill form
        if let Some(name_input) = document.get_element_by_id("categoryName") {
            name_input.dyn_ref::<web_sys::HtmlInputElement>().unwrap().set_value(&cat.name);
        }
        if let Some(color_input) = document.get_element_by_id("categoryColor") {
            color_input.dyn_ref::<web_sys::HtmlInputElement>().unwrap().set_value(&cat.color);
        }
        if let Some(tags_input) = document.get_element_by_id("categoryTags") {
            tags_input.dyn_ref::<web_sys::HtmlTextAreaElement>().unwrap().set_value(&cat.tags.join(", "));
        }
        if let Some(id_input) = document.get_element_by_id("editCategoryId") {
            id_input.dyn_ref::<web_sys::HtmlInputElement>().unwrap().set_value(&cat.id);
        }
        
        // Update modal title
        if let Some(modal_title) = document.get_element_by_id("tagCategoryModalLabel") {
            modal_title.set_text_content(Some("Edit Tag Category"));
        }
        
        // Show modal
        let js_code = "new bootstrap.Modal(document.getElementById('tagCategoryModal')).show()";
        js_sys::eval(js_code).ok();
    }
}

#[wasm_bindgen]
pub fn save_category_wasm() -> bool {
    let document = web_sys::window().unwrap().document().unwrap();
    
    let name = document.get_element_by_id("categoryName")
        .and_then(|e| Some(e.dyn_ref::<web_sys::HtmlInputElement>()?.value()))
        .unwrap_or_default().trim().to_string();
        
    let color = document.get_element_by_id("categoryColor")
        .and_then(|e| Some(e.dyn_ref::<web_sys::HtmlInputElement>()?.value()))
        .unwrap_or_default();
        
    let tags_text = document.get_element_by_id("categoryTags")
        .and_then(|e| Some(e.dyn_ref::<web_sys::HtmlTextAreaElement>()?.value()))
        .unwrap_or_default();
        
    let id = document.get_element_by_id("editCategoryId")
        .and_then(|e| Some(e.dyn_ref::<web_sys::HtmlInputElement>()?.value()))
        .unwrap_or_default();
    
    if name.is_empty() {
        js_sys::eval("alert('Please enter a category name')").ok();
        return false;
    }
    
    let tags = process_tag_string(&tags_text);
    if tags.is_empty() {
        js_sys::eval("alert('Please enter at least one tag')").ok();
        return false;
    }
    
    let mut categories = load_tag_categories();
    
    if id.is_empty() {
        // Add new
        let new_id = js_sys::Date::now().to_string();
        categories.push(TagCategory {
            id: new_id,
            name,
            color,
            tags,
        });
    } else {
        // Edit existing
        if let Some(category) = categories.iter_mut().find(|c| c.id == id) {
            category.name = name;
            category.color = color;
            category.tags = tags;
        }
    }
    
    save_tag_categories(categories);
    
    // Hide modal
    js_sys::eval("bootstrap.Modal.getInstance(document.getElementById('tagCategoryModal')).hide()").ok();
    
    true
}

#[wasm_bindgen]
pub fn delete_category_wasm(category_id: &str) {
    let confirm_result = js_sys::eval("confirm('Are you sure you want to delete this category?')")
        .unwrap()
        .as_bool()
        .unwrap_or(false);
        
    if confirm_result {
        let mut categories = load_tag_categories();
        categories.retain(|c| c.id != category_id);
        save_tag_categories(categories);
    }
}

#[wasm_bindgen]
pub fn export_tag_categories_wasm() {
    let categories = load_tag_categories();
    
    if categories.is_empty() {
        js_sys::eval("alert('No tag categories to export')").ok();
        return;
    }
    
    let json = serialize_tag_categories(categories);
    let date = js_sys::Date::new_0().to_iso_string();
    let date_string = date.as_string().unwrap();
    let date_str = date_string.split('T').next().unwrap();
    let filename = format!("vodmeta-tag-categories-{}.json", date_str);
    
    // Create and trigger download using JavaScript
    let js_code = format!(
        r#"
        const blob = new Blob([`{}`], {{ type: 'application/json' }});
        const downloadLink = document.createElement('a');
        downloadLink.href = URL.createObjectURL(blob);
        downloadLink.download = '{}';
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
        "#,
        json.replace('`', "\\`"), filename
    );
    
    js_sys::eval(&js_code).ok();
}

#[wasm_bindgen]
pub fn import_tag_categories_wasm() {
    let js_code = r#"
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'application/json';
        fileInput.onchange = (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const content = e.target.result;
                    if (validateTagCategoryData(content)) {
                        const imported = JSON.parse(content);
                        const current = loadTagCategories();
                        
                        if (current.length > 0 && !confirm(`This will replace your ${current.length} existing categories. Continue?`)) {
                            return;
                        }
                        
                        saveTagCategories(imported);
                        alert(`Successfully imported ${imported.length} tag categories`);
                    } else {
                        alert('Invalid format: File does not contain valid tag category data');
                    }
                } catch (error) {
                    alert(`Error importing categories: ${error}`);
                }
            };
            reader.readAsText(file);
        };
        fileInput.click();
    "#;
    
    js_sys::eval(js_code).ok();
}

// Interactive Chart functionality using HTML5 Canvas
#[derive(Clone, Debug)]
pub struct TimelineDataPoint {
    pub timestamp: f64,
    pub count: u32,
    pub label: String,
    pub url: Option<String>,
}

#[wasm_bindgen]
pub fn create_tooltip() -> web_sys::HtmlElement {
    let document = web_sys::window().unwrap().document().unwrap();
    let tooltip = document.create_element("div").unwrap().dyn_into::<web_sys::HtmlElement>().unwrap();
    tooltip.set_id("chartTooltip");
    tooltip.style().set_property("position", "absolute").ok();
    tooltip.style().set_property("background", "rgba(0, 0, 0, 0.8)").ok();
    tooltip.style().set_property("color", "white").ok();
    tooltip.style().set_property("padding", "8px 12px").ok();
    tooltip.style().set_property("border-radius", "4px").ok();
    tooltip.style().set_property("font-size", "12px").ok();
    tooltip.style().set_property("pointer-events", "none").ok();
    tooltip.style().set_property("display", "none").ok();
    tooltip.style().set_property("z-index", "1000").ok();
    
    document.body().unwrap().append_child(&tooltip).ok();
    tooltip
}

#[wasm_bindgen]
pub fn initialize_chat_timeline_chart() {
    let document = web_sys::window().unwrap().document().unwrap();
    let canvas_element = document.get_element_by_id("chatTimelineChart");
    
    if canvas_element.is_none() {
        console_log!("Chat timeline canvas not found");
        return;
    }
    
    let canvas = canvas_element.unwrap().dyn_into::<web_sys::HtmlCanvasElement>().unwrap();
    
    // Set canvas size
    canvas.set_width(800);
    canvas.set_height(200);
    
    // Get chat messages and process them
    let chat_messages = document.query_selector_all(".chat-message").unwrap();
    if chat_messages.length() == 0 {
        console_log!("No chat messages found");
        return;
    }
    
    // Get selected interval
    let interval_select = document.get_element_by_id("timelineInterval");
    let interval_minutes = if let Some(select) = interval_select {
        let select_element = select.dyn_ref::<web_sys::HtmlSelectElement>().unwrap();
        select_element.value().parse::<u32>().unwrap_or(30)
    } else {
        30
    };
    
    let chart_data = process_chat_timeline_data(&chat_messages, interval_minutes);
    
    if let Err(e) = draw_interactive_timeline_chart(&canvas, &chart_data) {
        console_log!("Error drawing chart: {}", e);
    }
    
    // Add interactivity with tooltip
    let tooltip = create_tooltip();
    setup_chart_interactivity(&canvas, &chart_data, tooltip);
}

fn process_chat_timeline_data(chat_messages: &web_sys::NodeList, interval_minutes: u32) -> Vec<TimelineDataPoint> {
    let mut message_timestamps: Vec<(f64, web_sys::Element)> = Vec::new();
    
    // Extract timestamps from messages
    for i in 0..chat_messages.length() {
        if let Some(message) = chat_messages.get(i) {
            let message_element = message.dyn_ref::<web_sys::Element>().unwrap();
            if let Ok(Some(timestamp_element)) = message_element.query_selector(".chat-timestamp[data-utc]") {
                if let Some(utc_time) = timestamp_element.get_attribute("data-utc") {
                    let date = js_sys::Date::new(&wasm_bindgen::JsValue::from_str(&utc_time));
                    if !date.get_time().is_nan() {
                        message_timestamps.push((date.get_time(), message_element.clone()));
                    }
                }
            }
        }
    }
    
    if message_timestamps.is_empty() {
        return Vec::new();
    }
    
    // Sort by timestamp
    message_timestamps.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    
    // Group into intervals
    let mut buckets: HashMap<i64, (u32, Option<String>)> = HashMap::new();
    let interval_ms = (interval_minutes as f64) * 60.0 * 1000.0;
    
    for (timestamp, element) in message_timestamps {
        let bucket_key = (timestamp / interval_ms).floor() as i64;
        
        let entry = buckets.entry(bucket_key).or_insert((0, None));
        entry.0 += 1;
        
        // Store URL from first message in bucket
        if entry.1.is_none() {
            if let Ok(Some(timestamp_link)) = element.query_selector("a[href*=\"t=\"]") {
                let link = timestamp_link.dyn_ref::<web_sys::HtmlAnchorElement>().unwrap();
                entry.1 = Some(link.href());
            }
        }
    }
    
    // Convert to data points
    let mut data_points: Vec<TimelineDataPoint> = buckets
        .into_iter()
        .map(|(bucket_key, (count, url))| {
            let timestamp = (bucket_key as f64) * interval_ms;
            let date = js_sys::Date::new(&wasm_bindgen::JsValue::from(timestamp));
            let label = format!("{}:{:02}", date.get_hours(), date.get_minutes());
            
            TimelineDataPoint {
                timestamp,
                count,
                label,
                url,
            }
        })
        .collect();
    
    // Sort by timestamp
    data_points.sort_by(|a, b| a.timestamp.partial_cmp(&b.timestamp).unwrap());
    
    data_points
}

fn draw_interactive_timeline_chart(canvas: &web_sys::HtmlCanvasElement, data: &[TimelineDataPoint]) -> Result<(), String> {
    let context = canvas
        .get_context("2d")
        .map_err(|_| "Failed to get 2D context")?
        .ok_or("Failed to get 2D context")?
        .dyn_into::<web_sys::CanvasRenderingContext2d>()
        .map_err(|_| "Failed to cast to CanvasRenderingContext2d")?;

    let width = canvas.width() as f64;
    let height = canvas.height() as f64;
    let margin = 50.0;
    let chart_width = width - 2.0 * margin;
    let chart_height = height - 2.0 * margin;

    // Clear canvas (transparent background)
    context.clear_rect(0.0, 0.0, width, height);
    
    if data.is_empty() {
        let _ = js_sys::Reflect::set(&context, &"fillStyle".into(), &"#333333".into());
        context.set_font("16px Arial");
        context.set_text_align("center");
        let _ = context.fill_text("No chat data available", width / 2.0, height / 2.0);
        return Ok(());
    }

    let max_count = data.iter().map(|d| d.count).max().unwrap_or(1) as f64;
    let min_timestamp = data.first().unwrap().timestamp;
    let max_timestamp = data.last().unwrap().timestamp;
    let time_range = max_timestamp - min_timestamp;

    // Draw axes
    let _ = js_sys::Reflect::set(&context, &"strokeStyle".into(), &"#666666".into());
    context.set_line_width(1.0);
    context.begin_path();
    // Y axis
    context.move_to(margin, margin);
    context.line_to(margin, height - margin);
    // X axis
    context.line_to(width - margin, height - margin);
    context.stroke();

    // Draw grid lines
    let _ = js_sys::Reflect::set(&context, &"strokeStyle".into(), &"#eeeeee".into());
    context.set_line_width(0.5);
    
    // Horizontal grid lines
    for i in 0..5 {
        let y = margin + (i as f64 * chart_height / 4.0);
        context.begin_path();
        context.move_to(margin, y);
        context.line_to(width - margin, y);
        context.stroke();
    }
    
    // Vertical grid lines
    for i in 0..6 {
        let x = margin + (i as f64 * chart_width / 5.0);
        context.begin_path();
        context.move_to(x, margin);
        context.line_to(x, height - margin);
        context.stroke();
    }

    // Draw area chart
    if data.len() > 1 {
        let _ = js_sys::Reflect::set(&context, &"fillStyle".into(), &"rgba(0, 123, 255, 0.3)".into());
        context.begin_path();
        
        let first_x = margin + ((data[0].timestamp - min_timestamp) / time_range) * chart_width;
        context.move_to(first_x, height - margin);
        
        for point in data {
            let x = margin + ((point.timestamp - min_timestamp) / time_range) * chart_width;
            let y = height - margin - ((point.count as f64 / max_count) * chart_height);
            context.line_to(x, y);
        }
        
        let last_x = margin + ((data.last().unwrap().timestamp - min_timestamp) / time_range) * chart_width;
        context.line_to(last_x, height - margin);
        context.close_path();
        context.fill();
    }

    // Draw line
    let _ = js_sys::Reflect::set(&context, &"strokeStyle".into(), &"#007bff".into());
    context.set_line_width(2.0);
    context.begin_path();
    
    for (i, point) in data.iter().enumerate() {
        let x = margin + ((point.timestamp - min_timestamp) / time_range) * chart_width;
        let y = height - margin - ((point.count as f64 / max_count) * chart_height);
        
        if i == 0 {
            context.move_to(x, y);
        } else {
            context.line_to(x, y);
        }
    }
    context.stroke();

    // Draw points
    let _ = js_sys::Reflect::set(&context, &"fillStyle".into(), &"#007bff".into());
    for point in data {
        let x = margin + ((point.timestamp - min_timestamp) / time_range) * chart_width;
        let y = height - margin - ((point.count as f64 / max_count) * chart_height);
        
        context.begin_path();
        context.arc(x, y, 4.0, 0.0, 2.0 * std::f64::consts::PI).ok();
        context.fill();
    }

    // Draw labels
    let _ = js_sys::Reflect::set(&context, &"fillStyle".into(), &"#333333".into());
    context.set_font("12px Arial");
    context.set_text_align("center");
    
    // X-axis labels (time)
    for i in 0..6 {
        let timestamp = min_timestamp + (i as f64 * time_range / 5.0);
        let x = margin + (i as f64 * chart_width / 5.0);
        let date = js_sys::Date::new(&wasm_bindgen::JsValue::from(timestamp));
        let label = format!("{}:{:02}", date.get_hours(), date.get_minutes());
        let _ = context.fill_text(&label, x, height - margin + 20.0);
    }
    
    // Y-axis labels (count)
    context.set_text_align("right");
    for i in 0..5 {
        let count = (max_count * (4 - i) as f64 / 4.0) as u32;
        let y = margin + (i as f64 * chart_height / 4.0) + 4.0;
        let _ = context.fill_text(&count.to_string(), margin - 10.0, y);
    }

    // Title
    let _ = js_sys::Reflect::set(&context, &"fillStyle".into(), &"#333333".into());
    context.set_font("16px Arial");
    context.set_text_align("center");
    let _ = context.fill_text("Chat Messages Timeline (Interactive)", width / 2.0, 25.0);

    Ok(())
}

fn setup_chart_interactivity(canvas: &web_sys::HtmlCanvasElement, data: &[TimelineDataPoint], tooltip: web_sys::HtmlElement) {
    use wasm_bindgen::closure::Closure;
    use wasm_bindgen::JsCast;
    
    let data_clone = data.to_vec();
    let canvas_clone = canvas.clone();
    let tooltip_clone = tooltip.clone();
    
    // Mouse move handler for hover effects
    let mousemove_handler = Closure::wrap(Box::new(move |event: web_sys::MouseEvent| {
        let rect = canvas_clone.get_bounding_client_rect();
        let x = event.client_x() as f64 - rect.x();
        let y = event.client_y() as f64 - rect.y();
        
        // Check if hovering over a data point
        let width = canvas_clone.width() as f64;
        let height = canvas_clone.height() as f64;
        let margin = 50.0;
        let chart_width = width - 2.0 * margin;
        let chart_height = height - 2.0 * margin;
        
        if !data_clone.is_empty() {
            let min_timestamp = data_clone.first().unwrap().timestamp;
            let max_timestamp = data_clone.last().unwrap().timestamp;
            let time_range = max_timestamp - min_timestamp;
            let max_count = data_clone.iter().map(|d| d.count).max().unwrap_or(1) as f64;
            
            let mut hovered_point: Option<&TimelineDataPoint> = None;
            
            for point in &data_clone {
                let point_x = margin + ((point.timestamp - min_timestamp) / time_range) * chart_width;
                let point_y = height - margin - ((point.count as f64 / max_count) * chart_height);
                
                // Check if mouse is near this point (within 10px radius)
                let distance = ((x - point_x).powi(2) + (y - point_y).powi(2)).sqrt();
                if distance <= 10.0 {
                    hovered_point = Some(point);
                    break;
                }
            }
            
            // Update cursor style and tooltip
            if let Some(point) = hovered_point {
                canvas_clone.style().set_property("cursor", "pointer").ok();
                
                // Show tooltip with point information
                let tooltip_text = format!(
                    "Time: {}\nMessages: {}\nClick to go to timestamp",
                    point.label, point.count
                );
                tooltip_clone.set_inner_text(&tooltip_text);
                
                // Position tooltip near mouse
                let page_x = event.page_x() as f64;
                let page_y = event.page_y() as f64;
                tooltip_clone.style().set_property("left", &format!("{}px", page_x + 10.0)).ok();
                tooltip_clone.style().set_property("top", &format!("{}px", page_y - 10.0)).ok();
                tooltip_clone.style().set_property("display", "block").ok();
            } else {
                canvas_clone.style().set_property("cursor", "default").ok();
                tooltip_clone.style().set_property("display", "none").ok();
            }
        }
    }) as Box<dyn FnMut(web_sys::MouseEvent)>);
    
    canvas.add_event_listener_with_callback("mousemove", mousemove_handler.as_ref().unchecked_ref()).ok();
    mousemove_handler.forget();
    
    // Mouse leave handler to hide tooltip
    let tooltip_leave = tooltip.clone();
    let mouseleave_handler = Closure::wrap(Box::new(move |_: web_sys::MouseEvent| {
        tooltip_leave.style().set_property("display", "none").ok();
    }) as Box<dyn FnMut(web_sys::MouseEvent)>);
    
    canvas.add_event_listener_with_callback("mouseleave", mouseleave_handler.as_ref().unchecked_ref()).ok();
    mouseleave_handler.forget();
    
    // Click handler for navigation
    let data_clone_click = data.to_vec();
    let canvas_clone_click = canvas.clone();
    
    let click_handler = Closure::wrap(Box::new(move |event: web_sys::MouseEvent| {
        let rect = canvas_clone_click.get_bounding_client_rect();
        let x = event.client_x() as f64 - rect.x();
        let y = event.client_y() as f64 - rect.y();
        
        let width = canvas_clone_click.width() as f64;
        let height = canvas_clone_click.height() as f64;
        let margin = 50.0;
        let chart_width = width - 2.0 * margin;
        let chart_height = height - 2.0 * margin;
        
        if !data_clone_click.is_empty() {
            let min_timestamp = data_clone_click.first().unwrap().timestamp;
            let max_timestamp = data_clone_click.last().unwrap().timestamp;
            let time_range = max_timestamp - min_timestamp;
            let max_count = data_clone_click.iter().map(|d| d.count).max().unwrap_or(1) as f64;
            
            for point in &data_clone_click {
                let point_x = margin + ((point.timestamp - min_timestamp) / time_range) * chart_width;
                let point_y = height - margin - ((point.count as f64 / max_count) * chart_height);
                
                let distance = ((x - point_x).powi(2) + (y - point_y).powi(2)).sqrt();
                if distance <= 10.0 {
                    if let Some(ref url) = point.url {
                        // Navigate to the timestamp URL
                        let window = web_sys::window().unwrap();
                        let location = window.location();
                        location.set_href(url).ok();
                    }
                    break;
                }
            }
        }
    }) as Box<dyn FnMut(web_sys::MouseEvent)>);
    
    canvas.add_event_listener_with_callback("click", click_handler.as_ref().unchecked_ref()).ok();
    click_handler.forget();
}

#[wasm_bindgen]
pub fn update_chat_timeline_interval() {
    initialize_chat_timeline_chart();
}

#[wasm_bindgen]
pub struct Counter {
    value: i32,
}

#[wasm_bindgen]
impl Counter {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Counter {
        Counter { value: 0 }
    }

    #[wasm_bindgen(getter)]
    pub fn value(&self) -> i32 {
        self.value
    }

    #[wasm_bindgen]
    pub fn increment(&mut self) {
        self.value += 1;
    }

    #[wasm_bindgen]
    pub fn reset(&mut self) {
        self.value = 0;
    }
}