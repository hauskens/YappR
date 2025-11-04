use crate::components::broadcaster::BroadcasterCard;
use crate::server_fns::get_broadcasters_with_auth;
use leptos::prelude::*;

#[component]
pub fn BroadcasterPage() -> impl IntoView {
    // Signal for the search term
    let (search_term, set_search_term) = signal(String::new());

    // Resource that fetches broadcasters from the server
    let broadcasters = Resource::new(|| (), |_| async move { get_broadcasters_with_auth().await });

    view! {
        <div class="container py-4">
            <div class="row justify-content-center">
                <div class="col-lg-10">
                    <div class="text-center mb-5 shadow">
                        <h1 class="display-4 mb-3">"Broadcasters"</h1>
                        <p class="lead text-muted">"Manage and browse available broadcasters"</p>
                    </div>

                    <div class="card shadow mb-4">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="bi bi-search me-2"></i>"Find Broadcasters"</h5>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-8">
                                    <div class="input-group">
                                        <span class="input-group-text">
                                            <i class="bi bi-search text-muted"></i>
                                        </span>
                                        <input
                                            type="text"
                                            class="form-control"
                                            id="broadcasterSearch"
                                            placeholder="Search broadcasters by name..."
                                            autocomplete="off"
                                            prop:value=move || search_term.get()
                                            on:input=move |ev| {
                                                set_search_term.set(event_target_value(&ev));
                                            }
                                        />
                                    </div>
                                </div>
                                <div class="col-md-4 text-md-end mt-2 mt-md-0 d-flex align-items-center justify-content-md-end">
                                    <Suspense fallback=|| view! { <span class="text-muted me-3">"Loading..."</span> }>
                                        {move || Suspend::new(async move {
                                            broadcasters.await.map(|all_broadcasters| {
                                                // Filter broadcasters based on search term
                                                let search = search_term.get().to_lowercase();
                                                let filtered: Vec<_> = all_broadcasters
                                                    .iter()
                                                    .filter(|b| {
                                                        if search.is_empty() {
                                                            true
                                                        } else {
                                                            b.name.to_lowercase().contains(&search)
                                                        }
                                                    })
                                                    .collect();
                                                let count = filtered.len();

                                                view! {
                                                    <small class="text-muted me-3">
                                                        <span>{count}</span>" broadcaster(s) found"
                                                    </small>
                                                }
                                            })
                                        })}
                                    </Suspense>
                                    <a href="/broadcaster/create" class="btn btn-primary">
                                        <i class="bi bi-plus me-1"></i>"Add New"
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>

                    <Suspense fallback=move || {
                        view! {
                            <div class="d-flex justify-content-center my-5">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">"Loading broadcasters..."</span>
                                </div>
                            </div>
                        }
                    }>
                        {move || Suspend::new(async move {
                            broadcasters.await.map(|all_broadcasters| {
                                // Filter broadcasters based on search term
                                let search = search_term.get().to_lowercase();
                                let filtered: Vec<_> = all_broadcasters
                                    .into_iter()
                                    .filter(|b| {
                                        if search.is_empty() {
                                            true
                                        } else {
                                            b.name.to_lowercase().contains(&search)
                                        }
                                    })
                                    .collect();

                                view! {
                                    <div>
                                        {
                                            if filtered.is_empty() {
                                                view! {
                                                    <div id="noResults" class="text-center py-5">
                                                        <div class="text-muted">
                                                            <i class="bi bi-search" style="font-size: 3rem; margin-bottom: 1rem;"></i>
                                                            <h5>"No broadcasters found"</h5>
                                                            <p>"Try adjusting your search terms"</p>
                                                        </div>
                                                    </div>
                                                }.into_any()
                                            } else {
                                                view! {
                                                    <div class="row" id="broadcastersGrid">
                                                        {filtered
                                                            .into_iter()
                                                            .map(|broadcaster| {
                                                                view! {
                                                                    <BroadcasterCard broadcaster=broadcaster/>
                                                                }
                                                            })
                                                            .collect_view()}
                                                    </div>
                                                }.into_any()
                                            }
                                        }
                                    </div>
                                }
                            })
                        })}
                    </Suspense>
                </div>
            </div>
        </div>
    }
}
