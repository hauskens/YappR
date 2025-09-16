use yew::prelude::*;
use crate::generic_table::{GenericTable, TableColumn, ColumnRenderType, SortOrder, CustomFilter, FilterOption};
use std::collections::HashMap;

#[derive(Properties, PartialEq)]
pub struct BroadcasterEventsTableProps {
    pub broadcaster_id: i32,
}

#[function_component(BroadcasterEventsTable)]
pub fn broadcaster_events_table(props: &BroadcasterEventsTableProps) -> Html {
    let mut event_type_colors = HashMap::new();
    event_type_colors.insert("Live".to_string(), "success".to_string());
    event_type_colors.insert("Offline".to_string(), "secondary".to_string());
    event_type_colors.insert("Subscription".to_string(), "primary".to_string());
    event_type_colors.insert("Gift".to_string(), "warning".to_string());
    event_type_colors.insert("Raid".to_string(), "info".to_string());
    event_type_colors.insert("Follow".to_string(), "danger".to_string());
    event_type_colors.insert("Cheer".to_string(), "purple".to_string());
    
    let columns = vec![
        TableColumn {
            key: "event_type".to_string(),
            title: "Type".to_string(),
            width: Some("120px".to_string()),
            sortable: true,
            searchable: true,
            render_type: ColumnRenderType::Badge { color_map: Some(event_type_colors) },
        },
        TableColumn {
            key: "channel_name".to_string(),
            title: "Channel".to_string(),
            width: Some("150px".to_string()),
            sortable: true,
            searchable: true,
            render_type: ColumnRenderType::Text,
        },
        TableColumn {
            key: "username".to_string(),
            title: "Username".to_string(),
            width: Some("120px".to_string()),
            sortable: true,
            searchable: true,
            render_type: ColumnRenderType::Text,
        },
        TableColumn {
            key: "raw_message".to_string(),
            title: "Message".to_string(),
            width: None,
            sortable: true,
            searchable: true,
            render_type: ColumnRenderType::Text,
        },
        TableColumn {
            key: "date_display".to_string(),
            title: "Date".to_string(),
            width: Some("100px".to_string()),
            sortable: true,
            searchable: false,
            render_type: ColumnRenderType::Text,
        },
        TableColumn {
            key: "time_display".to_string(),
            title: "Time".to_string(),
            width: Some("80px".to_string()),
            sortable: true,
            searchable: false,
            render_type: ColumnRenderType::Text,
        },
    ];

    let custom_filters = vec![
        CustomFilter {
            key: "event_type".to_string(),
            label: "Types".to_string(),
            options: vec![
                FilterOption { value: "live".to_string(), label: "Live".to_string() },
                FilterOption { value: "offline".to_string(), label: "Offline".to_string() },
                FilterOption { value: "subscription".to_string(), label: "Subscription".to_string() },
                FilterOption { value: "gift".to_string(), label: "Gift".to_string() },
                FilterOption { value: "raid".to_string(), label: "Raid".to_string() },
            ],
        },
    ];

    html! {
        <GenericTable 
            data_endpoint={format!("/broadcaster/{}/events_data", props.broadcaster_id)}
            columns={columns}
            title={"Broadcaster Events".to_string()}
            page_size={Some(50)}
            show_search={Some(true)}
            default_sort_column={Some("timestamp".to_string())}
            default_sort_order={Some(SortOrder::Desc)}
            custom_filters={Some(custom_filters)}
        />
    }
}

pub fn render_broadcaster_events_table(broadcaster_id: i32, element_id: &str) -> Result<(), String> {
    let document = web_sys::window().unwrap().document().unwrap();
    let element = document.get_element_by_id(element_id)
        .ok_or(format!("Element with id '{}' not found", element_id))?;
    
    yew::Renderer::<BroadcasterEventsTable>::with_root_and_props(
        element, 
        BroadcasterEventsTableProps { broadcaster_id }
    ).render();
    Ok(())
}