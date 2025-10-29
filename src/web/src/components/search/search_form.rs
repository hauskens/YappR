use leptos::prelude::*;
use leptos::ev;
use crate::server_fns::{BroadcasterData, VideoResultData, SearchVideos};

/// Search form component
#[component]
pub fn SearchForm(
    broadcasters: Vec<BroadcasterData>,
    #[prop(into)]
    on_results: Callback<Vec<VideoResultData>>,
    #[prop(into)]
    on_loading: Callback<bool>,
) -> impl IntoView {
    let (search_term, set_search_term) = signal(String::new());
    let (selected_broadcaster, set_selected_broadcaster) = signal(
        broadcasters.first().map(|b| b.id).unwrap_or(0)
    );
    let (start_date, set_start_date) = signal(String::new());
    let (end_date, set_end_date) = signal(String::new());
    let (channel_type, set_channel_type) = signal(String::from("all"));

    // Action for performing the search
    let search_action = ServerAction::<SearchVideos>::new();

    // Watch for when the action completes
    Effect::new(move || {
        if search_action.pending().get() {
            on_loading.run(true);
        } else {
            on_loading.run(false);
            if let Some(Ok(results)) = search_action.value().get() {
                on_results.run(results);
            }
        }
    });

    let on_submit = move |ev: ev::SubmitEvent| {
        ev.prevent_default();

        let start_date_val = if start_date.get().is_empty() {
            None
        } else {
            Some(start_date.get())
        };

        let end_date_val = if end_date.get().is_empty() {
            None
        } else {
            Some(end_date.get())
        };

        search_action.dispatch(SearchVideos {
            search_term: search_term.get(),
            broadcaster_id: selected_broadcaster.get(),
            start_date: start_date_val,
            end_date: end_date_val,
            channel_type: channel_type.get(),
        });
    };

    view! {
        <form on:submit=on_submit class="search-form p-3 rounded shadow">
            // Main search bar with integrated submit button
            <div class="input-group mb-3">
                <input
                    type="search"
                    autocomplete="off"
                    class="form-control form-control-lg"
                    required
                    placeholder="Search..."
                    aria-label="Search"
                    prop:value=search_term
                    on:input=move |ev| set_search_term.set(event_target_value(&ev))
                />
                <button
                    type="submit"
                    class="btn btn-primary"
                    disabled=move || search_action.pending().get()
                >
                    <span class="d-flex align-items-center">
                        <i class="bi bi-search me-1"></i>
                        <span>"Search"</span>
                        {move || {
                            if search_action.pending().get() {
                                view! {
                                    <span
                                        class="spinner-border spinner-border-sm ms-1"
                                        role="status"
                                        aria-hidden="true"
                                    ></span>
                                }
                                    .into_any()
                            } else {
                                let _: () = view! { <></> };
                                ().into_any()
                            }
                        }}

                    </span>
                </button>
            </div>

            // Broadcaster selection
            <div class="row mb-3 align-items-center">
                <div class="col-md-6">
                    {if broadcasters.len() == 1 {
                        let broadcaster = broadcasters.first().unwrap();
                        view! {
                            <>
                                <div class="badge bg-secondary p-2">{broadcaster.name.clone()}</div>
                                <input type="hidden" value=broadcaster.id/>
                            </>
                        }
                            .into_any()
                    } else {
                        view! {
                            <div class="form-floating">
                                <select
                                    class="form-select"
                                    aria-label="Broadcaster selection"
                                    on:change=move |ev| {
                                        if let Ok(id) = event_target_value(&ev).parse::<i32>() {
                                            set_selected_broadcaster.set(id);
                                        }
                                    }
                                >

                                    {broadcasters
                                        .iter()
                                        .map(|broadcaster| {
                                            view! {
                                                <option value=broadcaster.id>
                                                    {broadcaster.name.clone()}
                                                </option>
                                            }
                                        })
                                        .collect_view()}

                                </select>
                                <label>"Broadcaster"</label>
                            </div>
                        }
                            .into_any()
                    }}

                </div>

                <div class="col-md-2" hidden>
                    <select
                        class="form-select"
                        on:change=move |ev| set_channel_type.set(event_target_value(&ev))
                    >
                        <option value="all" selected>
                            "All"
                        </option>
                        <option value="youtube">"YouTube"</option>
                        <option value="twitch">"Twitch"</option>
                    </select>
                </div>

                <div class="col-md-6 text-end">
                    <button
                        class="btn btn-outline-secondary"
                        type="button"
                        data-bs-toggle="collapse"
                        data-bs-target="#collapseSearch"
                        aria-expanded="false"
                        aria-controls="collapseSearch"
                    >
                        <i class="bi bi-funnel"></i>
                        " Filters"
                    </button>
                </div>
            </div>

            // Collapsible filters section
            <div class="collapse" id="collapseSearch">
                <div class="card card-body mb-3">
                    <div class="row g-3">
                        <div class="col-md-6">
                            <div class="form-floating">
                                <input
                                    type="date"
                                    class="form-control"
                                    id="start_date"
                                    prop:value=start_date
                                    on:input=move |ev| set_start_date.set(event_target_value(&ev))
                                />
                                <label for="start_date">"Start Date"</label>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="form-floating">
                                <input
                                    type="date"
                                    class="form-control"
                                    id="end_date"
                                    prop:value=end_date
                                    on:input=move |ev| set_end_date.set(event_target_value(&ev))
                                />
                                <label for="end_date">"End Date"</label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </form>
    }
}
