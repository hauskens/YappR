use yew::prelude::*;
use crate::generic_table::{GenericTable, TableColumn, ColumnRenderType, SortOrder};

#[derive(Properties, PartialEq)]
pub struct TranscriptionTableProps {
    pub video_id: i32,
}

#[function_component(TranscriptionTable)]
pub fn transcription_table(props: &TranscriptionTableProps) -> Html {
    let columns = vec![
        TableColumn {
            key: "start".to_string(),
            title: "Start".to_string(),
            width: Some("10%".to_string()),
            sortable: true,
            searchable: false,
            render_type: ColumnRenderType::Duration,
        },
        TableColumn {
            key: "end".to_string(),
            title: "End".to_string(),
            width: Some("10%".to_string()),
            sortable: true,
            searchable: false,
            render_type: ColumnRenderType::Duration,
        },
        TableColumn {
            key: "text".to_string(),
            title: "Text".to_string(),
            width: None,
            sortable: true,
            searchable: true,
            render_type: ColumnRenderType::Text,
        },
        TableColumn {
            key: "timestamp_url".to_string(),
            title: "Link".to_string(),
            width: Some("8%".to_string()),
            sortable: false,
            searchable: false,
            render_type: ColumnRenderType::Link { url_key: Some("timestamp_url".to_string()) },
        },
    ];

    html! {
        <GenericTable 
            data_endpoint={format!("/video/{}/transcription_segments", props.video_id)}
            columns={columns}
            title={"Transcription Segments".to_string()}
            page_size={Some(100)}
            show_search={Some(true)}
            default_sort_column={Some("start".to_string())}
            default_sort_order={Some(SortOrder::Asc)}
        />
    }
}

pub fn render_transcription_table(video_id: i32, element_id: &str) -> Result<(), String> {
    let document = web_sys::window().unwrap().document().unwrap();
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    yew::Renderer::<TranscriptionTable>::with_root_and_props(
        element, 
        TranscriptionTableProps { video_id }
    ).render();
    Ok(())
}