use wasm_bindgen::prelude::*;


fn wrap_text(text: &str, max_chars_per_line: usize) -> Vec<String> {
    if max_chars_per_line == 0 {
        return vec![text.to_string()];
    }
    
    let mut lines = Vec::new();
    let words: Vec<&str> = text.split_whitespace().collect();
    let mut current_line = String::new();
    
    for word in words {
        let test_line = if current_line.is_empty() {
            word.to_string()
        } else {
            format!("{} {}", current_line, word)
        };
        
        if test_line.len() <= max_chars_per_line {
            current_line = test_line;
        } else {
            if !current_line.is_empty() {
                lines.push(current_line);
                current_line = word.to_string();
            } else {
                // Word is longer than max line length, break it
                let mut remaining = word;
                while remaining.len() > max_chars_per_line {
                    lines.push(remaining[..max_chars_per_line].to_string());
                    remaining = &remaining[max_chars_per_line..];
                }
                if !remaining.is_empty() {
                    current_line = remaining.to_string();
                }
            }
        }
    }
    
    if !current_line.is_empty() {
        lines.push(current_line);
    }
    
    if lines.is_empty() {
        lines.push(String::new());
    }
    
    lines
}


#[wasm_bindgen]
pub fn generate_chat_image(
    username: &str,
    user_color: &str,
    message: &str,
    message_color: &str,
    background_color: &str,
    font_size: u32,
    max_width: u32,
) -> Result<web_sys::HtmlCanvasElement, JsValue> {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Create canvas element
    let canvas = document
        .create_element("canvas")?
        .dyn_into::<web_sys::HtmlCanvasElement>()?;
    
    let ctx = canvas
        .get_context("2d")?
        .unwrap()
        .dyn_into::<web_sys::CanvasRenderingContext2d>()?;
    
    // Set font first to get accurate measurements
    let font_string = format!("{}px 'Arial', 'Inter', 'Helvetica Neue', sans-serif", font_size);
    ctx.set_font(&font_string);
    ctx.set_text_baseline("top");
    
    // Calculate text dimensions
    let padding = 15.0;
    let line_height = font_size as f64 * 1.4;
    let username_with_colon = format!("{}:", username);
    let spacing = 8.0; // Space between username and message
    
    // Approximate character width
    let char_width = font_size as f64 * 0.6;
    let username_width = username_with_colon.len() as f64 * char_width;
    
    // Calculate available width for message after username
    let available_message_width = max_width as f64 - padding * 2.0 - username_width - spacing;
    let chars_per_line = (available_message_width / char_width).floor() as usize;
    
    // Wrap message text
    let wrapped_lines = wrap_text(message, chars_per_line);
    let num_lines = wrapped_lines.len().max(1);
    
    // Calculate canvas dimensions
    let canvas_width = max_width;
    let canvas_height = (num_lines as f64 * line_height + padding * 2.0) as u32;
    
    canvas.set_width(canvas_width);
    canvas.set_height(canvas_height);
    
    // Make canvas fit in container
    canvas.style().set_property("max-width", "100%")?;
    canvas.style().set_property("height", "auto")?;
    
    // Fill background
    ctx.set_fill_style_str(background_color);
    ctx.fill_rect(0.0, 0.0, canvas_width as f64, canvas_height as f64);
    
    // Reset font after canvas resize
    ctx.set_font(&font_string);
    ctx.set_text_baseline("top");
    
    // Draw username with colon in bold on first line
    let bold_font_string = format!("bold {}px 'Arial', 'Inter', 'Helvetica Neue', sans-serif", font_size);
    ctx.set_font(&bold_font_string);
    ctx.set_fill_style_str(user_color);
    ctx.fill_text(&username_with_colon, padding, padding)?;
    
    // Draw wrapped message lines
    ctx.set_font(&font_string);
    ctx.set_fill_style_str(message_color);
    
    for (line_index, line) in wrapped_lines.iter().enumerate() {
        let y_position = padding + line_index as f64 * line_height;
        let x_position = if line_index == 0 {
            padding + username_width + spacing // First line after username
        } else {
            padding // Subsequent lines start from left margin
        };
        ctx.fill_text(line, x_position, y_position)?;
    }
    
    Ok(canvas)
}

#[wasm_bindgen]
pub fn generate_multi_line_chat_image(
    chat_lines: &str,
    background_color: &str,
    username_color: &str,
    message_color: &str,
    font_size: u32,
    max_width: u32,
) -> Result<web_sys::HtmlCanvasElement, JsValue> {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Create canvas element
    let canvas = document
        .create_element("canvas")?
        .dyn_into::<web_sys::HtmlCanvasElement>()?;
    
    let ctx = canvas
        .get_context("2d")?
        .unwrap()
        .dyn_into::<web_sys::CanvasRenderingContext2d>()?;
    
    // Parse chat lines
    let lines: Vec<&str> = chat_lines
        .trim()
        .split('\n')
        .filter(|line| !line.trim().is_empty())
        .collect();
    
    if lines.is_empty() {
        return Err(JsValue::from_str("No chat lines provided"));
    }
    
    // Set font first to get accurate measurements
    let font_string = format!("{}px 'Arial', 'Inter', 'Helvetica Neue', sans-serif", font_size);
    ctx.set_font(&font_string);
    ctx.set_text_baseline("top");
    
    // Calculate maximum width needed
    let padding = 15.0;
    let line_height = font_size as f64 * 1.4;
    let mut max_content_width: f64 = 0.0;
    let char_width = font_size as f64 * 0.6; // Approximate character width
    
    let spacing = 8.0; // Space between username and message
    for line in &lines {
        let line_width = if let Some(colon_index) = line.find(": ") {
            let username = &line[..colon_index];
            let message = &line[colon_index + 2..];
            let username_with_colon = format!("{}:", username);
            let username_width = username_with_colon.len() as f64 * char_width;
            let message_width = message.len() as f64 * char_width;
            username_width + spacing + message_width
        } else {
            line.len() as f64 * char_width
        };
        max_content_width = max_content_width.max(line_width);
    }
    
    // Set up dimensions - respect max_width
    let canvas_width = ((max_content_width + padding * 2.0).min(max_width as f64)) as u32;
    let canvas_height = (lines.len() as f64 * line_height + padding * 2.0) as u32;
    
    canvas.set_width(canvas_width);
    canvas.set_height(canvas_height);
    
    // Make canvas fit in container
    canvas.style().set_property("max-width", "100%")?;
    canvas.style().set_property("height", "auto")?;
    
    // Fill background
    ctx.set_fill_style_str(background_color);
    ctx.fill_rect(0.0, 0.0, canvas_width as f64, canvas_height as f64);
    
    // Reset font after canvas resize
    ctx.set_font(&font_string);
    ctx.set_text_baseline("top");
    
    // Draw each line
    for (index, line) in lines.iter().enumerate() {
        let y_position = padding + index as f64 * line_height;
        
        // Look for colon separator
        if let Some(colon_index) = line.find(": ") {
            let username = &line[..colon_index];
            let message = &line[colon_index + 2..];
            
            // Draw username with colon in bold
            let bold_font_string = format!("bold {}px 'Arial', 'Inter', 'Helvetica Neue', sans-serif", font_size);
            ctx.set_font(&bold_font_string);
            ctx.set_fill_style_str(username_color);
            let username_with_colon = format!("{}:", username);
            ctx.fill_text(&username_with_colon, padding, y_position)?;
            
            // Calculate approximate username width
            let char_width = font_size as f64 * 0.6;
            let username_width = username_with_colon.len() as f64 * char_width;
            
            // Draw message in regular font
            ctx.set_font(&font_string);
            ctx.set_fill_style_str(message_color);
            ctx.fill_text(message, padding + username_width + spacing, y_position)?;
        } else {
            // No colon found, treat as regular message
            ctx.set_fill_style_str(message_color);
            ctx.fill_text(line, padding, y_position)?;
        }
    }
    
    Ok(canvas)
}

#[wasm_bindgen]
pub fn canvas_to_blob(canvas: &web_sys::HtmlCanvasElement, callback: &js_sys::Function) -> Result<(), JsValue> {
    canvas.to_blob(callback)
}

#[wasm_bindgen]
pub fn save_image_settings(user_color: &str, message_color: &str, background_color: &str, font_size: u32, max_width: u32) {
    let storage = web_sys::window().unwrap().local_storage().unwrap().unwrap();
    let settings = format!("{{\"user_color\":\"{}\",\"message_color\":\"{}\",\"background_color\":\"{}\",\"font_size\":{},\"max_width\":{}}}", 
                          user_color, message_color, background_color, font_size, max_width);
    let _ = storage.set_item("chat_image_settings", &settings);
}

#[wasm_bindgen]
pub fn load_image_settings() -> Option<String> {
    let storage = web_sys::window().unwrap().local_storage().unwrap().unwrap();
    storage.get_item("chat_image_settings").unwrap_or(None)
}

#[wasm_bindgen]
pub fn download_canvas_as_image(canvas: &web_sys::HtmlCanvasElement, filename: &str) -> Result<(), JsValue> {
    let document = web_sys::window().unwrap().document().unwrap();
    
    // Create download link
    let link = document.create_element("a")?.dyn_into::<web_sys::HtmlAnchorElement>()?;
    
    // Convert canvas to data URL
    let data_url = canvas.to_data_url_with_type("image/png")?;
    link.set_href(&data_url);
    link.set_download(filename);
    
    // Trigger download
    let _ = link.click();
    
    Ok(())
}

#[wasm_bindgen]
pub async fn copy_canvas_to_clipboard(canvas: &web_sys::HtmlCanvasElement) -> Result<(), JsValue> {
    let window = web_sys::window().unwrap();
    
    // Convert canvas to data URL
    let data_url = canvas.to_data_url_with_type("image/png")?;
    
    // Use the Clipboard API through reflection to avoid web-sys API issues
    let navigator = js_sys::Reflect::get(&window, &"navigator".into())?;
    let clipboard = js_sys::Reflect::get(&navigator, &"clipboard".into())?;
    
    // Convert data URL to blob
    let fetch_promise = window.fetch_with_str(&data_url);
    let response = wasm_bindgen_futures::JsFuture::from(fetch_promise).await?;
    let response_obj: web_sys::Response = response.dyn_into()?;
    let blob_promise = response_obj.blob()?;
    let blob = wasm_bindgen_futures::JsFuture::from(blob_promise).await?;
    
    // Create ClipboardItem
    let clipboard_item_constructor = js_sys::Reflect::get(&window, &"ClipboardItem".into())?;
    let clipboard_item_ctor = clipboard_item_constructor.dyn_into::<js_sys::Function>()?;
    
    let clipboard_data = js_sys::Object::new();
    js_sys::Reflect::set(&clipboard_data, &"image/png".into(), &blob)?;
    
    let args = js_sys::Array::new();
    args.push(&clipboard_data);
    let clipboard_item = js_sys::Reflect::construct(&clipboard_item_ctor, &args)?;
    
    // Write to clipboard
    let write_method = js_sys::Reflect::get(&clipboard, &"write".into())?;
    let write_fn = write_method.dyn_into::<js_sys::Function>()?;
    
    let items_array = js_sys::Array::new();
    items_array.push(&clipboard_item);
    
    let write_promise = write_fn.call1(&clipboard, &items_array)?;
    wasm_bindgen_futures::JsFuture::from(js_sys::Promise::from(write_promise)).await?;
    
    Ok(())
}