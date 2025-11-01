use leptos::prelude::*;
use crate::server_fns::BroadcasterData;

#[component]
pub fn BroadcasterCard(broadcaster: BroadcasterData) -> impl IntoView {
    // Generate URL for viewing broadcaster details
    let broadcaster_url = format!("/broadcaster/edit/{}", broadcaster.id);

    view! {
        <div class="col-xl-3 col-lg-4 col-md-6 mb-4 broadcaster-card" data-name={broadcaster.name.to_lowercase()}>
            <div class="card border-0 shadow h-100">
                <div class="card-body text-center d-flex flex-column">
                    <div class="mb-3">
                        <div class="d-flex justify-content-center mb-3">
                            {if let Some(profile_image_url) = &broadcaster.profile_image_url {
                                view! {
                                    <img src={profile_image_url.clone()}
                                         class="rounded-circle"
                                         style="width: 60px; height: 60px; object-fit: cover;"
                                         alt={format!("{} profile image", broadcaster.name)}/>
                                }.into_any()
                            } else {
                                view! {
                                    <div class="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center"
                                         style="width: 60px; height: 60px;">
                                        <i class="bi bi-broadcast fs-4"></i>
                                    </div>
                                }.into_any()
                            }}
                        </div>
                        <h5 class="card-title mb-2">{broadcaster.name.clone()}</h5>
                        {if broadcaster.hidden {
                            view! {
                                <span class="badge bg-warning text-dark mb-2">
                                    <i class="bi bi-eye-slash me-1"></i>"Hidden"
                                </span>
                            }.into_any()
                        } else {
                            view! { <></> }.into_any()
                        }}
                    </div>
                    <div class="mt-auto">
                        <a href={broadcaster_url} class="btn btn-primary w-100">
                            <i class="bi bi-eye me-2"></i>"View Details"
                        </a>
                    </div>
                </div>
            </div>
        </div>
    }
}
