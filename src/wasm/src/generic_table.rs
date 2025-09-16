use yew::prelude::*;
use gloo_net::http::Request;
use web_sys::Event;
use yew::html::TargetCast;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TableColumn {
    pub key: String,
    pub title: String,
    pub width: Option<String>,
    pub sortable: bool,
    pub searchable: bool,
    pub render_type: ColumnRenderType,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum ColumnRenderType {
    Text,
    Link { url_key: Option<String> },
    Number,
    Duration, // For displaying time in seconds as mm:ss format
    Badge { color_map: Option<HashMap<String, String>> },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TableRow {
    pub id: String,
    pub data: HashMap<String, String>,
}

#[derive(Clone, PartialEq)]
pub enum SortField {
    Column(String),
}

#[derive(Clone, PartialEq)]
pub enum SortOrder {
    Asc,
    Desc,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct FilterOption {
    pub value: String,
    pub label: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CustomFilter {
    pub key: String,
    pub label: String,
    pub options: Vec<FilterOption>,
}

#[derive(Properties, PartialEq)]
pub struct GenericTableProps {
    pub data_endpoint: String,
    pub columns: Vec<TableColumn>,
    pub title: String,
    pub page_size: Option<usize>,
    pub show_search: Option<bool>,
    pub default_sort_column: Option<String>,
    pub default_sort_order: Option<SortOrder>,
    pub custom_filters: Option<Vec<CustomFilter>>,
}

#[function_component(GenericTable)]
pub fn generic_table(props: &GenericTableProps) -> Html {
    let rows = use_state(|| Vec::<TableRow>::new());
    let filtered_rows = use_state(|| Vec::<TableRow>::new());
    let search_term = use_state(|| String::new());
    let loading = use_state(|| true);
    let current_page = use_state(|| 1usize);
    let page_size = use_state(|| props.page_size.unwrap_or(50));
    let sort_field = use_state(|| {
        props.default_sort_column.as_ref()
            .map(|col| SortField::Column(col.clone()))
            .unwrap_or_else(|| SortField::Column(props.columns.first().map(|c| c.key.clone()).unwrap_or_default()))
    });
    let sort_order = use_state(|| props.default_sort_order.clone().unwrap_or(SortOrder::Asc));
    let error_message = use_state(|| None::<String>);
    let custom_filter_values = use_state(|| HashMap::<String, String>::new());

    // Load data from endpoint
    {
        let rows = rows.clone();
        let filtered_rows = filtered_rows.clone();
        let loading = loading.clone();
        let error_message = error_message.clone();
        let data_endpoint = props.data_endpoint.clone();

        use_effect_with((), move |_| {
            wasm_bindgen_futures::spawn_local(async move {
                match Request::get(&data_endpoint).send().await {
                    Ok(response) => {
                        if response.ok() {
                            match response.json::<serde_json::Value>().await {
                                Ok(data) => {
                                    let parsed_rows = parse_response_data(data);
                                    rows.set(parsed_rows.clone());
                                    filtered_rows.set(parsed_rows);
                                    loading.set(false);
                                }
                                Err(e) => {
                                    error_message.set(Some(format!("Failed to parse response: {}", e)));
                                    loading.set(false);
                                }
                            }
                        } else {
                            error_message.set(Some(format!("Request failed: {}", response.status())));
                            loading.set(false);
                        }
                    }
                    Err(e) => {
                        error_message.set(Some(format!("Network error: {}", e)));
                        loading.set(false);
                    }
                }
            });
        });
    }

    // Filter and sort data when search term, sort field, sort order, or custom filters change
    {
        let rows = rows.clone();
        let filtered_rows = filtered_rows.clone();
        let search_term = search_term.clone();
        let sort_field = sort_field.clone();
        let sort_order = sort_order.clone();
        let custom_filter_values = custom_filter_values.clone();
        let columns = props.columns.clone();
        let custom_filters = props.custom_filters.clone().unwrap_or_default();

        use_effect_with(((*search_term).clone(), (*sort_field).clone(), (*sort_order).clone(), (*custom_filter_values).clone()), move |(search, sort_field, sort_order, filter_values)| {
            let mut filtered = filter_rows(&*rows, search, &columns);
            filtered = apply_custom_filters(filtered, filter_values, &custom_filters);
            sort_rows(&mut filtered, sort_field, sort_order);
            filtered_rows.set(filtered);
        });
    }

    let on_search_input = {
        let search_term = search_term.clone();
        let current_page = current_page.clone();
        Callback::from(move |e: InputEvent| {
            let input: web_sys::HtmlInputElement = e.target_unchecked_into();
            search_term.set(input.value());
            current_page.set(1);
        })
    };

    let on_sort_header_click = {
        let sort_field = sort_field.clone();
        let sort_order = sort_order.clone();
        Callback::from(move |column_key: String| {
            let new_field = SortField::Column(column_key.clone());
            if *sort_field == new_field {
                sort_order.set(match *sort_order {
                    SortOrder::Asc => SortOrder::Desc,
                    SortOrder::Desc => SortOrder::Asc,
                });
            } else {
                sort_field.set(new_field);
                sort_order.set(SortOrder::Asc);
            }
        })
    };

    let on_page_size_change = {
        let page_size = page_size.clone();
        let current_page = current_page.clone();
        Callback::from(move |e: Event| {
            let select: web_sys::HtmlSelectElement = e.target_unchecked_into();
            if let Ok(new_size) = select.value().parse::<usize>() {
                page_size.set(new_size);
                current_page.set(1);
            }
        })
    };

    let on_page_change = {
        let current_page = current_page.clone();
        Callback::from(move |page: usize| {
            current_page.set(page);
        })
    };

    let on_clear_search = {
        let search_term = search_term.clone();
        let custom_filter_values = custom_filter_values.clone();
        let current_page = current_page.clone();
        Callback::from(move |_| {
            search_term.set(String::new());
            custom_filter_values.set(HashMap::new());
            current_page.set(1);
        })
    };

    let on_custom_filter_change = {
        let custom_filter_values = custom_filter_values.clone();
        let current_page = current_page.clone();
        Callback::from(move |e: Event| {
            let select: web_sys::HtmlSelectElement = e.target_unchecked_into();
            let filter_key = select.get_attribute("data-filter-key").unwrap_or_default();
            let value = select.value();
            
            let mut new_values = (*custom_filter_values).clone();
            if value.is_empty() || value == "all" {
                new_values.remove(&filter_key);
            } else {
                new_values.insert(filter_key, value);
            }
            custom_filter_values.set(new_values);
            current_page.set(1);
        })
    };

    if *loading {
        return html! {
            <div class="text-center">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">{"Loading..."}</span>
                </div>
            </div>
        };
    }

    if let Some(error) = (*error_message).as_ref() {
        return html! {
            <div class="alert alert-danger">
                {format!("Error loading data: {}", error)}
            </div>
        };
    }

    let total_filtered = filtered_rows.len();
    let total_pages = (total_filtered + *page_size - 1) / *page_size;
    let start_idx = (*current_page - 1) * *page_size;
    let end_idx = std::cmp::min(start_idx + *page_size, total_filtered);
    
    let paginated_rows = if start_idx < total_filtered {
        filtered_rows[start_idx..end_idx].to_vec()
    } else {
        Vec::new()
    };

    let sort_icon = |column_key: &str| -> Html {
        let SortField::Column(current_key) = &*sort_field;
        if current_key == column_key {
            match *sort_order {
                SortOrder::Asc => html! { <i class="bi bi-sort-up ms-1"></i> },
                SortOrder::Desc => html! { <i class="bi bi-sort-down ms-1"></i> },
            }
        } else {
            html! { <i class="bi bi-sort-up ms-1 text-muted"></i> }
        }
    };

    let has_search = props.show_search.unwrap_or(true);
    let has_active_search = !search_term.is_empty();
    let has_active_filters = has_active_search || !custom_filter_values.is_empty();

    // Generate pagination buttons
    let pagination_buttons = generate_pagination_buttons(*current_page, total_pages, on_page_change.clone());

    html! {
        <div class="generic-table">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5>{&props.title}</h5>
                <div class="d-flex align-items-center">
                    if has_search {
                        <div class="input-group me-3" style="width: 300px;">
                            <input
                                type="text"
                                class="form-control"
                                placeholder="Search..."
                                value={(*search_term).clone()}
                                oninput={on_search_input}
                            />
                            if has_active_search {
                                <button 
                                    class="btn btn-outline-secondary" 
                                    type="button"
                                    onclick={on_clear_search}
                                    title="Clear search"
                                >
                                    <i class="bi bi-x"></i>
                                </button>
                            }
                        </div>
                    }
                    
                    // Custom filter dropdowns
                    {
                        if let Some(custom_filters) = &props.custom_filters {
                            custom_filters.iter().map(|filter| {
                                html! {
                                    <select 
                                        class="form-select form-select-sm me-2" 
                                        style="width: auto;" 
                                        onchange={on_custom_filter_change.clone()}
                                        data-filter-key={filter.key.clone()}
                                        value={custom_filter_values.get(&filter.key).cloned().unwrap_or_default()}
                                    >
                                        <option value="all">{format!("All {}", filter.label)}</option>
                                        {for filter.options.iter().map(|option| {
                                            let selected = custom_filter_values.get(&filter.key)
                                                .map(|v| v == &option.value)
                                                .unwrap_or(false);
                                            html! {
                                                <option value={option.value.clone()} selected={selected}>
                                                    {&option.label}
                                                </option>
                                            }
                                        })}
                                    </select>
                                }
                            }).collect::<Html>()
                        } else {
                            html! {}
                        }
                    }
                    
                    <select class="form-select form-select-sm" style="width: auto;" onchange={on_page_size_change} value={page_size.to_string()}>
                        <option value="25">{"25 per page"}</option>
                        <option value="50" selected={*page_size == 50}>{"50 per page"}</option>
                        <option value="100">{"100 per page"}</option>
                        <option value="200">{"200 per page"}</option>
                    </select>
                </div>
            </div>

            <div class="text-muted small mb-2">
                {format!("Showing {} - {} of {} items", 
                    if total_filtered > 0 { start_idx + 1 } else { 0 },
                    end_idx,
                    total_filtered
                )}
                if has_active_filters {
                    <span class="badge bg-primary ms-2">{"Filtered"}</span>
                }
            </div>
            
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            {for props.columns.iter().map(|column| {
                                let column_key = column.key.clone();
                                let onclick = if column.sortable {
                                    let callback = on_sort_header_click.clone();
                                    Some(Callback::from(move |_| callback.emit(column_key.clone())))
                                } else {
                                    None
                                };

                                html! {
                                    <th 
                                        style={if column.sortable { "cursor: pointer;" } else { "" }}
                                        width={column.width.clone()}
                                        onclick={onclick}
                                    >
                                        {&column.title}
                                        if column.sortable {
                                            {sort_icon(&column.key)}
                                        }
                                    </th>
                                }
                            })}
                        </tr>
                    </thead>
                    <tbody>
                        {for paginated_rows.iter().map(|row| {
                            html! {
                                <tr key={row.id.clone()}>
                                    {for props.columns.iter().map(|column| {
                                        let cell_value = row.data.get(&column.key).cloned().unwrap_or_default();
                                        let cell_content = render_cell_content(&column.render_type, &cell_value, &row.data);
                                        
                                        html! {
                                            <td>{cell_content}</td>
                                        }
                                    })}
                                </tr>
                            }
                        })}
                    </tbody>
                </table>
            </div>
            
            if total_pages > 1 {
                <nav>
                    <ul class="pagination justify-content-center">
                        <li class={classes!("page-item", (*current_page == 1).then_some("disabled"))}>
                            <button class="page-link" onclick={
                                let callback = on_page_change.clone();
                                let current_page = current_page.clone();
                                Callback::from(move |_| {
                                    if *current_page > 1 {
                                        callback.emit(*current_page - 1);
                                    }
                                })
                            }>
                                {"Previous"}
                            </button>
                        </li>
                        
                        {for pagination_buttons}
                        
                        <li class={classes!("page-item", (*current_page == total_pages).then_some("disabled"))}>
                            <button class="page-link" onclick={
                                let callback = on_page_change.clone();
                                let current_page = current_page.clone();
                                Callback::from(move |_| {
                                    if *current_page < total_pages {
                                        callback.emit(*current_page + 1);
                                    }
                                })
                            }>
                                {"Next"}
                            </button>
                        </li>
                    </ul>
                </nav>
            }
        </div>
    }
}

fn parse_response_data(data: serde_json::Value) -> Vec<TableRow> {
    let mut rows = Vec::new();
    
    // Handle different response formats
    if let Some(segments) = data.get("segments").and_then(|s| s.as_array()) {
        // Transcription segments format
        for segment in segments {
            if let Some(obj) = segment.as_object() {
                let mut row_data = HashMap::new();
                for (key, value) in obj {
                    row_data.insert(key.clone(), format!("{}", value).trim_matches('"').to_string());
                }
                
                let id = row_data.get("id").cloned().unwrap_or_default();
                rows.push(TableRow { id, data: row_data });
            }
        }
    } else if let Some(chat_logs) = data.get("chat_logs").and_then(|s| s.as_array()) {
        // Chat logs format
        for log in chat_logs {
            if let Some(obj) = log.as_object() {
                let mut row_data = HashMap::new();
                for (key, value) in obj {
                    row_data.insert(key.clone(), format!("{}", value).trim_matches('"').to_string());
                }
                
                let id = row_data.get("id").cloned().unwrap_or_default();
                rows.push(TableRow { id, data: row_data });
            }
        }
    } else if let Some(events) = data.get("events").and_then(|s| s.as_array()) {
        // Broadcaster events format
        for event in events {
            if let Some(obj) = event.as_object() {
                let mut row_data = HashMap::new();
                for (key, value) in obj {
                    row_data.insert(key.clone(), format!("{}", value).trim_matches('"').to_string());
                }
                
                let id = row_data.get("id").cloned().unwrap_or_default();
                rows.push(TableRow { id, data: row_data });
            }
        }
    }
    
    rows
}

fn filter_rows(rows: &[TableRow], search_term: &str, columns: &[TableColumn]) -> Vec<TableRow> {
    if search_term.is_empty() {
        return rows.to_vec();
    }

    let search_lower = search_term.to_lowercase();
    rows.iter()
        .filter(|row| {
            columns.iter()
                .filter(|col| col.searchable)
                .any(|col| {
                    row.data.get(&col.key)
                        .map(|value| value.to_lowercase().contains(&search_lower))
                        .unwrap_or(false)
                })
        })
        .cloned()
        .collect()
}

fn apply_custom_filters(rows: Vec<TableRow>, filter_values: &HashMap<String, String>, _filters: &[CustomFilter]) -> Vec<TableRow> {
    if filter_values.is_empty() {
        return rows;
    }

    rows.into_iter()
        .filter(|row| {
            filter_values.iter().all(|(filter_key, filter_value)| {
                row.data.get(filter_key)
                    .map(|value| value == filter_value)
                    .unwrap_or(false)
            })
        })
        .collect()
}

fn sort_rows(rows: &mut [TableRow], sort_field: &SortField, sort_order: &SortOrder) {
    let SortField::Column(column_key) = sort_field;
    rows.sort_by(|a, b| {
        let a_val = a.data.get(column_key).cloned().unwrap_or_default();
        let b_val = b.data.get(column_key).cloned().unwrap_or_default();
        
        // Try to parse as numbers first for proper numeric sorting
        // Skip numeric parsing for values that contain letters (like timestamps with 's')
        let comparison = if !a_val.chars().any(|c| c.is_alphabetic()) && !b_val.chars().any(|c| c.is_alphabetic()) {
            if let (Ok(a_num), Ok(b_num)) = (a_val.parse::<f64>(), b_val.parse::<f64>()) {
                a_num.partial_cmp(&b_num).unwrap_or(std::cmp::Ordering::Equal)
            } else {
                a_val.cmp(&b_val)
            }
        } else {
            a_val.cmp(&b_val)
        };
        
        match sort_order {
            SortOrder::Asc => comparison,
            SortOrder::Desc => comparison.reverse(),
        }
    });
}

fn render_cell_content(render_type: &ColumnRenderType, value: &str, row_data: &HashMap<String, String>) -> Html {
    match render_type {
        ColumnRenderType::Text => html! { {value} },
        ColumnRenderType::Number => html! { {value} },
        ColumnRenderType::Duration => {
            if let Ok(seconds) = value.parse::<f64>() {
                let minutes = (seconds / 60.0) as i32;
                let secs = (seconds % 60.0) as i32;
                html! { {format!("{:02}:{:02}", minutes, secs)} }
            } else {
                html! { {value} }
            }
        },
        ColumnRenderType::Link { url_key } => {
            let url = url_key.as_ref()
                .and_then(|key| row_data.get(key))
                .cloned()
                .unwrap_or_else(|| value.to_string());
            
            html! {
                <a href={url} target="_blank" class="text-decoration-none">
                    {value}
                </a>
            }
        },
        ColumnRenderType::Badge { color_map } => {
            let color = color_map.as_ref()
                .and_then(|map| map.get(value))
                .cloned()
                .unwrap_or_else(|| "secondary".to_string());
            
            html! {
                <span class={format!("badge bg-{}", color)}>
                    {value}
                </span>
            }
        }
    }
}

fn generate_pagination_buttons(current_page: usize, total_pages: usize, on_page_change: Callback<usize>) -> Vec<Html> {
    if total_pages <= 1 {
        return Vec::new();
    }

    let max_visible = 7;
    let half_visible = max_visible / 2;
    
    let start_page = if current_page <= half_visible {
        1
    } else if current_page + half_visible >= total_pages {
        std::cmp::max(1, total_pages - max_visible + 1)
    } else {
        current_page - half_visible
    };
    
    let end_page = std::cmp::min(total_pages, start_page + max_visible - 1);
    
    let mut pages = Vec::new();
    
    // First page + ellipsis if needed
    if start_page > 1 {
        pages.push(html! {
            <li key={1} class="page-item">
                <button class="page-link" onclick={
                    let callback = on_page_change.clone();
                    Callback::from(move |_| callback.emit(1))
                }>
                    {"1"}
                </button>
            </li>
        });
        
        if start_page > 2 {
            pages.push(html! {
                <li key={"ellipsis-start"} class="page-item disabled">
                    <span class="page-link">{"..."}</span>
                </li>
            });
        }
    }
    
    // Main page range
    for page in start_page..=end_page {
        let is_current = page == current_page;
        pages.push(html! {
            <li key={page} class={classes!("page-item", is_current.then_some("active"))}>
                <button class="page-link" onclick={
                    let callback = on_page_change.clone();
                    Callback::from(move |_| callback.emit(page))
                }>
                    {page}
                </button>
            </li>
        });
    }
    
    // Last page + ellipsis if needed
    if end_page < total_pages {
        if end_page < total_pages - 1 {
            pages.push(html! {
                <li key={"ellipsis-end"} class="page-item disabled">
                    <span class="page-link">{"..."}</span>
                </li>
            });
        }
        
        pages.push(html! {
            <li key={total_pages} class="page-item">
                <button class="page-link" onclick={
                    let callback = on_page_change.clone();
                    Callback::from(move |_| callback.emit(total_pages))
                }>
                    {total_pages}
                </button>
            </li>
        });
    }
    
    pages
}