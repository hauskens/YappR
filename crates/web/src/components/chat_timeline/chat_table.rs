use super::types::{TagCategory, load_tag_categories};
use crate::server_fns::{ChatLogData, VideoDetailData};
use leptos::prelude::*;

#[component]
pub fn ChatTable(
    #[prop(into)] chat_logs: Signal<Vec<ChatLogData>>,
    video: VideoDetailData,
) -> impl IntoView {
    let (search_term, set_search_term) = signal(String::new());
    let (_categories, set_categories) = signal(Vec::<TagCategory>::new());

    // Load categories and tagged messages on mount
    Effect::new(move |_| {
        set_categories.set(load_tag_categories());
    });

    // Listen for tag category changes
    #[cfg(feature = "hydrate")]
    Effect::new(move |_| {
        use wasm_bindgen::JsCast;
        use wasm_bindgen::closure::Closure;

        if let Some(window) = web_sys::window() {
            let listener = Closure::wrap(Box::new(move |_event: web_sys::Event| {
                set_categories.set(load_tag_categories());
            }) as Box<dyn FnMut(_)>);

            let _ = window.add_event_listener_with_callback(
                "tagCategoriesChanged",
                listener.as_ref().unchecked_ref(),
            );

            listener.forget();
        }
    });

    view! {
        <div class="chat-table-component">
            // Filters
            <div class="row mb-3">
                <div class="col-md-6">
                    <input
                        type="text"
                        class="form-control"
                        placeholder="Search by username or message..."
                        prop:value=move || search_term.get()
                        on:input=move |ev| set_search_term.set(event_target_value(&ev))
                    />
                </div>
            </div>

            // Table
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th style="width: 10%;">"Time"</th>
                            <th style="width: 15%;">"Username"</th>
                            <th style="width: 45%;">"Message"</th>
                        </tr>
                    </thead>
                    <tbody>
                        {move || {
                            let search = search_term.get().to_lowercase();
                            let logs = chat_logs.get();

                            logs.iter().filter(|log| {
                                    if !search.is_empty() {
                                        let matches = log.username.to_lowercase().contains(&search)
                                            || log.message.to_lowercase().contains(&search);
                                        if !matches {
                                            return false;
                                        }
                                    }
                                    true
                                })
                                .cloned()
                                .map(|log| {
                                    view! {
                                        <tr>
                                            <td><a href={video.platform.timestamp_url(&video.platform_ref, &log.offset_seconds).to_string()}>{format!("{:.0}s", log.offset_seconds)}</a></td>
                                            <td>{log.username.clone()}</td>
                                            <td>{log.message.clone()}</td>
                                        </tr>
                                    }
                                })
                                .collect_view()
                                .into_any()
                        }}
                    </tbody>
                </table>
            </div>

            // Result count
            <div class="text-muted small mt-2">
                {move || {
                    let search = search_term.get().to_lowercase();
                    let logs = chat_logs.get();

                    let filtered_count = logs
                        .iter()
                        .filter(|log| {
                            if !search.is_empty() {
                                let matches = log.username.to_lowercase().contains(&search)
                                    || log.message.to_lowercase().contains(&search);
                                if !matches {
                                    return false;
                                }
                            }
                            true
                        })
                        .count();

                    format!("Showing {} of {} messages", filtered_count, logs.len())
                }}
            </div>
        </div>
    }
}
