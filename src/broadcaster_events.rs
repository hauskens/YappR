use wasm_bindgen::prelude::*;
use web_sys::{HtmlSelectElement, HtmlFormElement, Event};
use wasm_bindgen::JsCast;

#[derive(Clone, Debug)]
pub struct BroadcasterEventsManager;

impl BroadcasterEventsManager {
    pub fn new() -> Self {
        Self
    }

    fn get_element_by_id<T: JsCast>(id: &str) -> Option<T> {
        let document = web_sys::window()?.document()?;
        let element = document.get_element_by_id(id)?;
        element.dyn_into::<T>().ok()
    }

    pub fn initialize(&self) {
        self.setup_filter_listeners();
    }

    fn setup_filter_listeners(&self) {
        if let Some(filter_form) = Self::get_element_by_id::<HtmlFormElement>("filterForm") {
            let selects = filter_form.query_selector_all("select").unwrap();
            
            for i in 0..selects.length() {
                if let Some(select_element) = selects.get(i) {
                    if let Ok(select) = select_element.dyn_into::<HtmlSelectElement>() {
                        let form_clone = filter_form.clone();
                        let closure = Closure::wrap(Box::new(move |_: Event| {
                            let _ = form_clone.submit();
                        }) as Box<dyn FnMut(_)>);
                        
                        select.set_onchange(Some(closure.as_ref().unchecked_ref()));
                        closure.forget();
                    }
                }
            }
        }
    }
}

// Main initialization function
pub fn init_broadcaster_events() {
    let manager = BroadcasterEventsManager::new();
    manager.initialize();
}