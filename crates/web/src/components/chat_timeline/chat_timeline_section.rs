use super::chat_table::ChatTable;
// use super::tag_manager::TagManager;
// use super::timeline_chart::TimelineChart;
use crate::server_fns::{VideoDetailData, get_chat_logs};
use leptos::prelude::*;

#[component]
pub fn ChatTimelineSection(video: VideoDetailData) -> impl IntoView {
    // Load chat logs immediately on page load
    let chat_resource = Resource::new(
        move || video.id,
        |id| async move { get_chat_logs(id).await.ok() },
    );

    view! {
        <div class="chat-timeline-section">
            // Tag Categories Section
            // <div class="card mb-4">
            //     <div class="card-header">
            //         <h4 class="mb-0">
            //             <button
            //                 class="btn btn-link text-decoration-none w-100 text-start"
            //                 type="button"
            //                 data-bs-toggle="collapse"
            //                 data-bs-target="#tagCategoriesCollapse"
            //             >
            //                 <i class="bi bi-tags me-2"></i>
            //                 "Tag Categories"
            //                 <i class="bi bi-chevron-down float-end"></i>
            //             </button>
            //         </h4>
            //     </div>
            //     <div id="tagCategoriesCollapse" class="collapse">
            //         <div class="card-body">
            //             <TagManager/>
            //         </div>
            //     </div>
            // </div>

            // Chat Messages Table Section
            <div class="card mb-4">
                <div class="card-header">
                    <h4 class="mb-0">
                        <button
                            class="btn btn-link text-decoration-none w-100 text-start"
                            type="button"
                            data-bs-toggle="collapse"
                            data-bs-target="#chatMessagesCollapse"
                        >
                            <i class="bi bi-chat-dots me-2"></i>
                            "Chat Messages"
                            <i class="bi bi-chevron-down float-end"></i>
                        </button>
                    </h4>
                </div>
                <div id="chatMessagesCollapse" class="collapse">
                    <div class="card-body">
                        <Suspense fallback=|| view! { <p>"Loading chat messages..."</p> }>
                            {Suspend::new(async move {
                                chat_resource.await.map(move |chat_data| {
                                    if chat_data.is_empty() {
                                        view! { <p>"No chat messages found for this video."</p> }.into_any()
                                    } else {
                                        let (data_signal, _) = signal(chat_data);

                                        view! {
                                            <ChatTable chat_logs=data_signal video=video/>
                                        }.into_any()
                                    }
                                })
                            })}
                        </Suspense>
                    </div>
                </div>
            </div>
        </div>
    }
}
