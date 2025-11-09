use crate::components::chat_timeline::types::get_contrast_color;
use crate::components::chat_timeline::types::save_tag_categories;

use super::types::{TagCategory, load_tag_categories};
use leptos::ev;
use leptos::prelude::*;

#[derive(Clone, PartialEq)]
#[allow(dead_code)]
struct TagCategoryForm {
    id: String,
    name: String,
    color: String,
    keywords: String, // Comma-separated
}

impl Default for TagCategoryForm {
    fn default() -> Self {
        Self {
            id: String::new(),
            name: String::new(),
            color: "#007bff".to_string(),
            keywords: String::new(),
        }
    }
}

impl From<&TagCategory> for TagCategoryForm {
    fn from(category: &TagCategory) -> Self {
        Self {
            id: category.id.clone(),
            name: category.name.clone(),
            color: category.color.clone(),
            keywords: category.keywords.join(", "),
        }
    }
}

#[allow(unused)]
fn process_keywords(input: &str) -> Vec<String> {
    input
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

#[component]
pub fn TagManager() -> impl IntoView {
    let (categories, set_categories) = signal(Vec::<TagCategory>::new());
    let (show_modal, set_show_modal) = signal(false);
    let (form_data, set_form_data) = signal(TagCategoryForm::default());
    let (is_editing, set_is_editing) = signal(false);

    // Load categories on mount
    Effect::new(move |_| {
        let loaded = load_tag_categories();
        set_categories.set(loaded);
    });

    let open_add_modal = move |_| {
        set_form_data.set(TagCategoryForm::default());
        set_is_editing.set(false);
        set_show_modal.set(true);
    };

    let open_edit_modal = move |category_id: String| {
        if let Some(category) = categories.get().iter().find(|c| c.id == category_id) {
            set_form_data.set(TagCategoryForm::from(category));
            set_is_editing.set(true);
            set_show_modal.set(true);
        }
    };

    let close_modal = move |_| {
        set_show_modal.set(false);
    };

    let save_category = move |_| {
        let form = form_data.get();

        if form.name.trim().is_empty() {
            #[cfg(feature = "hydrate")]
            if let Some(window) = web_sys::window() {
                let _ = window.alert_with_message("Please enter a category name");
            }
            return;
        }

        let keywords = process_keywords(&form.keywords);
        if keywords.is_empty() {
            #[cfg(feature = "hydrate")]
            if let Some(window) = web_sys::window() {
                let _ = window.alert_with_message("Please enter at least one keyword");
            }
            return;
        }

        let mut cats = categories.get();

        if is_editing.get() {
            if let Some(category) = cats.iter_mut().find(|c| c.id == form.id) {
                category.name = form.name.trim().to_string();
                category.color = form.color.clone();
                category.keywords = keywords;
            }
        } else {
            cats.push(TagCategory::new(
                form.name.trim().to_string(),
                form.color.clone(),
                keywords,
            ));
        }

        save_tag_categories(&cats);
        set_categories.set(cats);
        set_show_modal.set(false);
    };

    let delete_category = move |category_id: String| {
        #[cfg(feature = "hydrate")]
        {
            if let Some(window) = web_sys::window() {
                if let Ok(confirmed) =
                    window.confirm_with_message("Are you sure you want to delete this category?")
                {
                    if confirmed {
                        let mut cats = categories.get();
                        cats.retain(|c| c.id != category_id);
                        save_tag_categories(&cats);
                        set_categories.set(cats);
                    }
                }
            }
        }
        #[cfg(not(feature = "hydrate"))]
        {
            let _ = category_id; // Suppress unused warning
        }
    };

    let export_categories = move |_| {
        #[cfg(feature = "hydrate")]
        {
            use wasm_bindgen::JsCast;

            let cats = categories.get();
            if cats.is_empty() {
                if let Some(window) = web_sys::window() {
                    let _ = window.alert_with_message("No tag categories to export");
                }
                return;
            }

            if let Ok(json) = serde_json::to_string_pretty(&cats) {
                let date = js_sys::Date::new_0();
                let date_str = date.to_iso_string().as_string().unwrap_or_default();
                let date_part = date_str.split('T').next().unwrap_or("unknown");
                let filename = format!("yappr-chat-tags-{}.json", date_part);

                // Create blob and download
                if let Some(window) = web_sys::window()
                    && let Some(document) = window.document()
                {
                    let array = js_sys::Array::new();
                    array.push(&wasm_bindgen::JsValue::from_str(&json));

                    let mut blob_property_bag = web_sys::BlobPropertyBag::new();
                    blob_property_bag.type_("application/json");

                    if let Ok(blob) =
                        web_sys::Blob::new_with_str_sequence_and_options(&array, &blob_property_bag)
                    {
                        if let Ok(url) = web_sys::Url::create_object_url_with_blob(&blob) {
                            if let Ok(link) = document.create_element("a") {
                                let link: web_sys::HtmlAnchorElement = link.unchecked_into();
                                link.set_href(&url);
                                link.set_download(&filename);
                                link.click();
                                let _ = web_sys::Url::revoke_object_url(&url);
                            }
                        }
                    }
                }
            }
        }
    };

    let on_file_input = move |ev: ev::Event| {
        #[cfg(feature = "hydrate")]
        {
            use wasm_bindgen::JsCast;

            let input: web_sys::HtmlInputElement = ev.target().unwrap().unchecked_into();

            if let Some(files) = input.files() {
                if let Some(file) = files.get(0) {
                    let reader = web_sys::FileReader::new().unwrap();
                    let reader_clone = reader.clone();

                    let onload = wasm_bindgen::closure::Closure::wrap(Box::new(
                        move |_event: web_sys::ProgressEvent| {
                            if let Ok(result) = reader_clone.result() {
                                if let Some(text) = result.as_string() {
                                    match serde_json::from_str::<Vec<TagCategory>>(&text) {
                                        Ok(imported_categories) => {
                                            let valid = imported_categories.iter().all(|cat| {
                                                !cat.id.is_empty()
                                                    && !cat.name.is_empty()
                                                    && !cat.color.is_empty()
                                            });

                                            if !valid {
                                                if let Some(window) = web_sys::window() {
                                                    let _ = window
                                                        .alert_with_message("Invalid file format");
                                                }
                                                return;
                                            }

                                            let current_count = categories.get().len();
                                            let should_continue = if current_count > 0 {
                                                if let Some(window) = web_sys::window() {
                                                    window
                                                        .confirm_with_message(&format!(
                                                            "Replace {} existing categories?",
                                                            current_count
                                                        ))
                                                        .unwrap_or(false)
                                                } else {
                                                    false
                                                }
                                            } else {
                                                true
                                            };

                                            if should_continue {
                                                save_tag_categories(&imported_categories);
                                                set_categories.set(imported_categories);
                                                if let Some(window) = web_sys::window() {
                                                    let _ = window
                                                        .alert_with_message("Import successful!");
                                                }
                                            }
                                        }
                                        Err(_) => {
                                            if let Some(window) = web_sys::window() {
                                                let _ = window
                                                    .alert_with_message("Invalid JSON format");
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    )
                        as Box<dyn FnMut(_)>);

                    reader.set_onload(Some(onload.as_ref().unchecked_ref()));
                    onload.forget();

                    let _ = reader.read_as_text(&file);
                }
            }

            input.set_value("");
        }
        #[cfg(not(feature = "hydrate"))]
        {
            let _ = ev; // Suppress unused warning
        }
    };

    view! {
        <div class="tag-category-manager">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5>"Tag Categories"</h5>
                <div>
                    <label for="import-file" class="btn btn-outline-secondary btn-sm me-2">
                        <i class="bi bi-upload"></i> " Import"
                    </label>
                    <input
                        id="import-file"
                        type="file"
                        accept="application/json,.json"
                        style="display: none;"
                        on:change=on_file_input
                    />
                    <button class="btn btn-outline-secondary btn-sm me-2" on:click=export_categories>
                        <i class="bi bi-download"></i> " Export"
                    </button>
                    <button class="btn btn-primary btn-sm" on:click=open_add_modal>
                        <i class="bi bi-plus"></i> " Add Category"
                    </button>
                </div>
            </div>

            <div id="tagCategoriesContainer">
                {move || if categories.get().is_empty() {
                    view! {
                        <div class="text-muted text-center py-4">
                            "No tag categories defined. Click 'Add Category' to create one."
                        </div>
                    }.into_any()
                } else {
                    view! {
                        <div>
                            {categories.get().into_iter().map(|category| {
                                let edit_id = category.id.clone();
                                let delete_id = category.id.clone();
                                let contrast_color = get_contrast_color(&category.color);

                                view! {
                                    <div
                                        class="badge rounded-pill d-inline-flex align-items-center me-2 mb-2"
                                        style=format!(
                                            "background-color: {}; color: {}; font-size: 0.9rem; padding: 0.5em 0.8em;",
                                            category.color, contrast_color
                                        )
                                    >
                                        <span style="margin-right: 5px;">{category.name.clone()}</span>
                                        <span class="small opacity-75">{format!("({} keywords)", category.keywords.len())}</span>

                                        <button
                                            class="btn btn-sm ms-2 p-0"
                                            style=format!("line-height: 1; color: {};", contrast_color)
                                            on:click=move |_| open_edit_modal(edit_id.clone())
                                        >
                                            <i class="bi bi-pencil-fill" style="font-size: 0.8rem;"></i>
                                        </button>

                                        <button
                                            class="btn btn-sm ms-1 p-0"
                                            style=format!("line-height: 1; color: {};", contrast_color)
                                            on:click=move |_| delete_category(delete_id.clone())
                                        >
                                            <i class="bi bi-x-lg" style="font-size: 0.8rem;"></i>
                                        </button>
                                    </div>
                                }
                            }).collect_view()}
                        </div>
                    }.into_any()
                }}
            </div>

            {move || if show_modal.get() {
                view! {
                    <div class="modal show d-block" tabindex="-1" style="background-color: rgba(0,0,0,0.5);">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">
                                        {if is_editing.get() { "Edit Tag Category" } else { "Add Tag Category" }}
                                    </h5>
                                    <button type="button" class="btn-close" on:click=close_modal></button>
                                </div>
                                <div class="modal-body">
                                    <div class="mb-3">
                                        <label class="form-label">"Category Name"</label>
                                        <input
                                            type="text"
                                            class="form-control"
                                            prop:value=move || form_data.get().name
                                            on:input=move |ev| {
                                                let mut form = form_data.get();
                                                form.name = event_target_value(&ev);
                                                set_form_data.set(form);
                                            }
                                            placeholder="Enter category name"
                                        />
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">"Color"</label>
                                        <input
                                            type="color"
                                            class="form-control form-control-color"
                                            prop:value=move || form_data.get().color
                                            on:input=move |ev| {
                                                let mut form = form_data.get();
                                                form.color = event_target_value(&ev);
                                                set_form_data.set(form);
                                            }
                                        />
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">"Keywords (comma-separated)"</label>
                                        <textarea
                                            class="form-control"
                                            rows="3"
                                            prop:value=move || form_data.get().keywords
                                            on:input=move |ev| {
                                                let mut form = form_data.get();
                                                form.keywords = event_target_value(&ev);
                                                set_form_data.set(form);
                                            }
                                            placeholder="Enter keywords separated by commas"
                                        ></textarea>
                                    </div>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" on:click=close_modal>
                                        "Cancel"
                                    </button>
                                    <button type="button" class="btn btn-primary" on:click=save_category>
                                        {if is_editing.get() { "Update" } else { "Save" }}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                }.into_any()
            } else {
                view! { <div></div> }.into_any()
            }}
        </div>
    }
}
