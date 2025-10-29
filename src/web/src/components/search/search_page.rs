use leptos::prelude::*;
use crate::server_fns::{get_broadcasters, VideoResultData};
use crate::components::search::{search_form::SearchForm, search_tips::SearchTips, search_results::SearchResults};

/// Main search page component
#[component]
pub fn SearchPage() -> impl IntoView {
    // Resource to fetch broadcasters (non-hidden only)
    let broadcasters = Resource::new(|| (), |_| async { get_broadcasters(false).await });

    // State for search results
    let (search_results, set_search_results) = signal::<Option<Vec<VideoResultData>>>(None);
    let (is_loading, set_is_loading) = signal(false);

    view! {
        <div class="container py-4">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="text-center mb-5 shadow">
                        <h1 class="display-4 mb-3">"Search"</h1>
                        <p class="lead text-muted">
                            "Find exactly when something was said in Streams or VODs"
                        </p>
                    </div>

                    // Show loading spinner or search form
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
                            match broadcasters.await {
                                Ok(broadcasters_list) => {
                                    if broadcasters_list.is_empty() {
                                        view! {
                                            <div class="alert alert-warning" role="alert">
                                                "No broadcasters available. Please check back later."
                                            </div>
                                        }
                                            .into_any()
                                    } else {
                                        view! {
                                            <SearchForm
                                                broadcasters=broadcasters_list
                                                on_results=Callback::new(move |results| {
                                                    set_search_results.set(Some(results));
                                                })

                                                on_loading=Callback::new(move |loading| {
                                                    set_is_loading.set(loading);
                                                })
                                            />
                                        }
                                            .into_any()
                                    }
                                }
                                Err(e) => {
                                    view! {
                                        <div class="alert alert-danger" role="alert">
                                            "Failed to load broadcasters: " {e.to_string()}
                                        </div>
                                    }
                                        .into_any()
                                }
                            }
                        })}

                    </Suspense>
                </div>
            </div>

            // Search Tips
            <div class="row justify-content-center mt-4">
                <div class="col-md-8">
                    <SearchTips/>
                </div>
            </div>

            // Search Results
            <div class="row justify-content-center mt-2">
                <div class="col-md-8">
                    <SearchResults
                        results=Signal::derive(move || search_results.get())
                        loading=Signal::derive(move || is_loading.get())
                    />
                </div>
            </div>
        </div>
    }
}
