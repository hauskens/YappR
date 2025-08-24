
use serde::{Deserialize, Serialize};
use wasm_bindgen::prelude::*;
use yew::prelude::*;
use web_sys::HtmlInputElement;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
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


fn process_tag_string(input: &str) -> Vec<String> {
    input.split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

fn get_contrast_yiq(hex_color: &str) -> String {
    let hex = hex_color.trim_start_matches('#');
    if hex.len() != 6 {
        return "#000000".to_string();
    }
    
    let r = u8::from_str_radix(&hex[0..2], 16).unwrap_or(0);
    let g = u8::from_str_radix(&hex[2..4], 16).unwrap_or(0);
    let b = u8::from_str_radix(&hex[4..6], 16).unwrap_or(0);
    
    let yiq = ((r as f32 * 299.0) + (g as f32 * 587.0) + (b as f32 * 114.0)) / 1000.0;
    
    if yiq >= 128.0 {
        "#000000".to_string()
    } else {
        "#ffffff".to_string()
    }
}

pub fn load_tag_categories_yew() -> Vec<TagCategory> {
    let window = web_sys::window().unwrap();
    let storage = window.local_storage().unwrap().unwrap();
    
    match storage.get_item("tagCategories") {
        Ok(Some(stored)) => {
            match serde_json::from_str::<Vec<TagCategory>>(&stored) {
                Ok(categories) => categories,
                Err(_) => Vec::new()
            }
        }
        _ => Vec::new()
    }
}

fn save_tag_categories_yew(categories: Vec<TagCategory>) {
    let window = web_sys::window().unwrap();
    let storage = window.local_storage().unwrap().unwrap();
    
    let json = serde_json::to_string_pretty(&categories).unwrap();
    let _ = storage.set_item("tagCategories", &json);
    
    // Dispatch custom event to notify other components
    if let Ok(event) = web_sys::CustomEvent::new("tagCategoriesChanged") {
        let _ = window.dispatch_event(&event);
    }
}

#[derive(Clone, PartialEq)]
struct TagCategoryForm {
    id: String,
    name: String,
    color: String,
    tags: String,
}

impl Default for TagCategoryForm {
    fn default() -> Self {
        Self {
            id: String::new(),
            name: String::new(),
            color: "#007bff".to_string(),
            tags: String::new(),
        }
    }
}

#[function_component(TagCategoryManager)]
pub fn tag_category_manager() -> Html {
    let categories = use_state(|| Vec::<TagCategory>::new());
    let show_modal = use_state(|| false);
    let form_data = use_state(TagCategoryForm::default);
    let is_editing = use_state(|| false);
    
    // Load categories on component mount
    {
        let categories = categories.clone();
        use_effect_with((), move |_| {
            let loaded_categories = load_tag_categories_yew();
            categories.set(loaded_categories);
        });
    }
    
    let save_categories = {
        let categories = categories.clone();
        Callback::from(move |cats: Vec<TagCategory>| {
            save_tag_categories_yew(cats.clone());
            categories.set(cats);
        })
    };
    
    let open_add_modal = {
        let show_modal = show_modal.clone();
        let form_data = form_data.clone();
        let is_editing = is_editing.clone();
        Callback::from(move |_| {
            form_data.set(TagCategoryForm::default());
            is_editing.set(false);
            show_modal.set(true);
        })
    };
    
    let open_edit_modal = {
        let show_modal = show_modal.clone();
        let form_data = form_data.clone();
        let is_editing = is_editing.clone();
        let categories = categories.clone();
        Callback::from(move |category_id: String| {
            if let Some(category) = categories.iter().find(|c| c.id == category_id) {
                form_data.set(TagCategoryForm {
                    id: category.id.clone(),
                    name: category.name.clone(),
                    color: category.color.clone(),
                    tags: category.tags.join(", "),
                });
                is_editing.set(true);
                show_modal.set(true);
            }
        })
    };
    
    let close_modal = {
        let show_modal = show_modal.clone();
        Callback::from(move |_| {
            show_modal.set(false);
        })
    };
    
    let save_category = {
        let categories = categories.clone();
        let form_data = form_data.clone();
        let is_editing = is_editing.clone();
        let show_modal = show_modal.clone();
        let save_categories = save_categories.clone();
        Callback::from(move |_| {
            let form = &*form_data;
            
            if form.name.trim().is_empty() {
                web_sys::window().unwrap().alert_with_message("Please enter a category name").ok();
                return;
            }
            
            let tags = process_tag_string(&form.tags);
            if tags.is_empty() {
                web_sys::window().unwrap().alert_with_message("Please enter at least one tag").ok();
                return;
            }
            
            let mut cats = (*categories).clone();
            
            if *is_editing {
                if let Some(category) = cats.iter_mut().find(|c| c.id == form.id) {
                    category.name = form.name.trim().to_string();
                    category.color = form.color.clone();
                    category.tags = tags;
                }
            } else {
                let new_id = js_sys::Date::now().to_string();
                cats.push(TagCategory {
                    id: new_id,
                    name: form.name.trim().to_string(),
                    color: form.color.clone(),
                    tags,
                });
            }
            
            save_categories.emit(cats);
            show_modal.set(false);
        })
    };
    
    let delete_category = {
        let categories = categories.clone();
        let save_categories = save_categories.clone();
        Callback::from(move |category_id: String| {
            let confirm = web_sys::window().unwrap()
                .confirm_with_message("Are you sure you want to delete this category?")
                .unwrap_or(false);
            
            if confirm {
                let mut cats = (*categories).clone();
                cats.retain(|c| c.id != category_id);
                save_categories.emit(cats);
            }
        })
    };
    
    let on_name_input = {
        let form_data = form_data.clone();
        Callback::from(move |e: InputEvent| {
            let input: web_sys::HtmlInputElement = e.target_unchecked_into();
            let mut form = (*form_data).clone();
            form.name = input.value();
            form_data.set(form);
        })
    };
    
    let on_color_input = {
        let form_data = form_data.clone();
        Callback::from(move |e: InputEvent| {
            let input: web_sys::HtmlInputElement = e.target_unchecked_into();
            let mut form = (*form_data).clone();
            form.color = input.value();
            form_data.set(form);
        })
    };
    
    let on_tags_input = {
        let form_data = form_data.clone();
        Callback::from(move |e: InputEvent| {
            let input: web_sys::HtmlTextAreaElement = e.target_unchecked_into();
            let mut form = (*form_data).clone();
            form.tags = input.value();
            form_data.set(form);
        })
    };
    
    let export_categories = {
        let categories = categories.clone();
        Callback::from(move |_| {
            let cats = (*categories).clone();
            if cats.is_empty() {
                web_sys::window().unwrap().alert_with_message("No tag categories to export").ok();
                return;
            }
            
            let json = serde_json::to_string_pretty(&cats).unwrap();
            let date = js_sys::Date::new_0().to_iso_string();
            let date_string = date.as_string().unwrap();
            let date_str = date_string.split('T').next().unwrap();
            let filename = format!("vodmeta-tag-categories-{}.json", date_str);
            
            // Create blob and download link using web-sys
            let array = js_sys::Array::new();
            array.push(&JsValue::from_str(&json));
            
            let blob_parts = array;
            let blob_property_bag = web_sys::BlobPropertyBag::new();
            blob_property_bag.set_type("application/json");
            
            let blob = web_sys::Blob::new_with_str_sequence_and_options(
                &blob_parts, &blob_property_bag
            ).unwrap();
            
            let url = web_sys::Url::create_object_url_with_blob(&blob).unwrap();
            
            let document = web_sys::window().unwrap().document().unwrap();
            let link = document.create_element("a").unwrap();
            let link: web_sys::HtmlAnchorElement = link.dyn_into().unwrap();
            
            link.set_href(&url);
            link.set_download(&filename);
            link.click();
            
            web_sys::Url::revoke_object_url(&url).ok();
        })
    };
    
    let on_file_input = {
        let categories = categories.clone();
        let save_categories = save_categories.clone();
        
        Callback::from(move |e: Event| {
            let input: HtmlInputElement = e.target_unchecked_into();
            let current_count = categories.len();
            
            if let Some(files) = input.files() {
                let files = gloo::file::FileList::from(files);
                if let Some(file) = files.iter().next() {
                    web_sys::console::log_1(&JsValue::from_str(&format!("Processing file: {}", file.name())));
                    
                    if file.raw_mime_type() == "application/json" || file.name().ends_with(".json") {
                        web_sys::console::log_1(&JsValue::from_str("Starting file read"));
                        
                        let save_categories = save_categories.clone();
                        let _task = gloo::file::callbacks::read_as_text(file, move |result| {
                            web_sys::console::log_1(&JsValue::from_str("File read callback executed"));
                            match result {
                                Ok(content) => {
                                    web_sys::console::log_1(&JsValue::from_str(&format!("Content length: {}", content.len())));
                                    match serde_json::from_str::<Vec<TagCategory>>(&content) {
                                        Ok(imported_categories) => {
                                            let valid = imported_categories.iter().all(|cat| {
                                                !cat.id.is_empty() && !cat.name.is_empty() && !cat.color.is_empty()
                                            });
                                            
                                            if !valid {
                                                web_sys::window().unwrap().alert_with_message("Invalid format").ok();
                                                return;
                                            }
                                            
                                            let should_continue = if current_count > 0 {
                                                web_sys::window().unwrap()
                                                    .confirm_with_message(&format!("Replace {} existing categories?", current_count))
                                                    .unwrap_or(false)
                                            } else {
                                                true
                                            };
                                            
                                            if should_continue {
                                                save_categories.emit(imported_categories);
                                                web_sys::window().unwrap()
                                                    .alert_with_message("Import successful!")
                                                    .ok();
                                            }
                                        }
                                        Err(_) => {
                                            web_sys::window().unwrap().alert_with_message("Invalid JSON format").ok();
                                        }
                                    }
                                }
                                Err(_) => {
                                    web_sys::window().unwrap().alert_with_message("Failed to read file").ok();
                                }
                            }
                        });
                        
                        // Store the task to prevent it from being dropped
                        std::mem::forget(_task);
                    } else {
                        web_sys::window().unwrap().alert_with_message("Please select a JSON file").ok();
                    }
                }
            }
            
            input.set_value("");
        })
    };

    html! {
        <div class="tag-category-manager">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4>{"Tag Categories"}</h4>
                <div>
                    <label for="import-file" class="btn btn-outline-secondary btn-sm me-2">
                        <i class="bi bi-upload"></i> {"Import"}
                    </label>
                    <input 
                        id="import-file"
                        type="file" 
                        accept="application/json,.json"
                        style="display: none;"
                        onchange={on_file_input}
                    />
                    <button class="btn btn-outline-secondary btn-sm me-2" onclick={export_categories}>
                        <i class="bi bi-download"></i> {"Export"}
                    </button>
                    <button class="btn btn-primary btn-sm" onclick={open_add_modal}>
                        <i class="bi bi-plus"></i> {"Add Category"}
                    </button>
                </div>
            </div>
            
            <div id="tagCategoriesContainer">
                if categories.is_empty() {
                    <div id="noCategoriesMsg" class="text-muted text-center py-4">
                        {"No tag categories defined. Click 'Add Category' to create one."}
                    </div>
                } else {
                    {for categories.iter().map(|category| {
                        let _category_id = category.id.clone();
                        let edit_id = category.id.clone();
                        let delete_id = category.id.clone();
                        let contrast_color = get_contrast_yiq(&category.color);
                        
                        html! {
                            <div key={category.id.clone()} class="badge rounded-pill d-inline-flex align-items-center me-2 mb-2"
                                style={format!("background-color: {}; color: {}; font-size: 0.9rem; padding: 0.5em 0.8em;", 
                                    category.color, contrast_color)}>
                                
                                <span style="margin-right: 5px;">{&category.name}</span>
                                <span class="small opacity-75">{format!("({} tags)", category.tags.len())}</span>
                                
                                <button class="btn btn-sm ms-2 p-0" 
                                    style={format!("line-height: 1; color: {};", contrast_color)}
                                    onclick={
                                        let callback = open_edit_modal.clone();
                                        Callback::from(move |_| callback.emit(edit_id.clone()))
                                    }>
                                    <i class="bi bi-pencil-fill" style="font-size: 0.8rem;"></i>
                                </button>
                                
                                <button class="btn btn-sm ms-1 p-0" 
                                    style={format!("line-height: 1; color: {};", contrast_color)}
                                    onclick={
                                        let callback = delete_category.clone();
                                        Callback::from(move |_| callback.emit(delete_id.clone()))
                                    }>
                                    <i class="bi bi-x-lg" style="font-size: 0.8rem;"></i>
                                </button>
                            </div>
                        }
                    })}
                }
            </div>
            
            if *show_modal {
                <div class="modal show d-block" tabindex="-1" style="background-color: rgba(0,0,0,0.5);">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">
                                    {if *is_editing { "Edit Tag Category" } else { "Add Tag Category" }}
                                </h5>
                                <button type="button" class="btn-close" onclick={close_modal.clone()}></button>
                            </div>
                            <div class="modal-body">
                                <div class="mb-3">
                                    <label class="form-label">{"Category Name"}</label>
                                    <input type="text" class="form-control" 
                                        value={form_data.name.clone()} 
                                        oninput={on_name_input}
                                        placeholder="Enter category name" />
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">{"Color"}</label>
                                    <input type="color" class="form-control form-control-color" 
                                        value={form_data.color.clone()} 
                                        oninput={on_color_input} />
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">{"Tags (comma-separated)"}</label>
                                    <textarea class="form-control" rows="3" 
                                        value={form_data.tags.clone()} 
                                        oninput={on_tags_input}
                                        placeholder="Enter tags separated by commas"></textarea>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" onclick={close_modal}>
                                    {"Cancel"}
                                </button>
                                <button type="button" class="btn btn-primary" onclick={save_category}>
                                    {if *is_editing { "Update" } else { "Save" }}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            }
        </div>
    }
}
