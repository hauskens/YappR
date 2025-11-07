use leptos::{html, prelude::*};
use std::str::FromStr;

#[cfg(feature = "hydrate")]
use web_sys;

#[cfg(feature = "hydrate")]
use wasm_bindgen::prelude::*;

#[cfg(feature = "hydrate")]
use js_sys;

#[allow(dead_code)]
enum Theme {
    Dark,
    Light,
}

impl Theme {
    pub fn is_dark(&self) -> bool {
        matches!(self, Theme::Dark)
    }
    pub fn default() -> Self {
        Theme::Light
    }
}

impl FromStr for Theme {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "dark" => Ok(Theme::Dark),
            "light" => Ok(Theme::Light),
            _ => Err(()),
        }
    }
}

#[component]
pub fn DarkModeToggle() -> impl IntoView {
    let (is_dark_mode, set_is_dark_mode) = signal(false);

    Effect::new(move |_| {
        let current_theme = get_stored_theme();
        set_is_dark_mode.set(current_theme.is_dark());
    });

    let toggle_theme = move |_| {
        let new_mode = !is_dark_mode.get();
        set_is_dark_mode.set(new_mode);
        apply_theme(new_mode);
        store_theme(new_mode);
    };

    view! {
        <button
            on:click=toggle_theme
            class="btn btn-link"
            style="cursor: pointer; user-select: none; margin: 0; padding: 0; border: none; font-size: 1.25rem;"
            aria-label="Toggle dark mode"
        >
            {move || {
                let icon_name = if is_dark_mode.get() { "moon" } else { "sun" };
                view! {
                    <FeatherIcon icon=icon_name />
                }
            }}
        </button>
    }
}

#[component]
fn FeatherIcon(icon: &'static str) -> impl IntoView {
    let container_ref = NodeRef::<html::Span>::new();

    // to prevent unused variable warning
    #[cfg(not(feature = "hydrate"))]
    let _icon = icon;
    #[cfg(feature = "hydrate")]
    Effect::new(move |_| {
        if let Some(svg) = get_feather_svg(icon) {
            if let Some(container) = container_ref.get() {
                container.set_inner_html(&svg);
            }
        }
    });

    view! {
        <span node_ref=container_ref></span>
    }
}

#[cfg(feature = "hydrate")]
fn get_feather_svg(icon: &str) -> Option<String> {
    let window = web_sys::window()?;
    let feather = js_sys::Reflect::get(&window, &JsValue::from_str("feather")).ok()?;
    let icons = js_sys::Reflect::get(&feather, &JsValue::from_str("icons")).ok()?;
    let icon_obj = js_sys::Reflect::get(&icons, &JsValue::from_str(icon)).ok()?;
    let to_svg_fn = js_sys::Reflect::get(&icon_obj, &JsValue::from_str("toSvg")).ok()?;
    let svg_js = js_sys::Reflect::apply(
        to_svg_fn.as_ref().unchecked_ref(),
        &icon_obj,
        &js_sys::Array::new(),
    )
    .ok()?;
    svg_js.as_string()
}

#[cfg(feature = "hydrate")]
fn get_stored_theme() -> Theme {
    if let Some(window) = web_sys::window()
        && let Ok(Some(storage)) = window.local_storage()
        && let Ok(Some(theme)) = storage.get_item("theme")
    {
        return Theme::from_str(&theme).unwrap_or(Theme::default());
    }
    Theme::default()
}

#[cfg(not(feature = "hydrate"))]
fn get_stored_theme() -> Theme {
    Theme::default()
}

#[cfg(feature = "hydrate")]
fn store_theme(is_dark: bool) {
    if let Some(window) = web_sys::window()
        && let Ok(Some(storage)) = window.local_storage()
    {
        let theme = if is_dark { "dark" } else { "light" };
        let _ = storage.set_item("theme", theme);
    }
}

#[cfg(not(feature = "hydrate"))]
fn store_theme(_is_dark: bool) {
    // No-op on server
}

#[cfg(feature = "hydrate")]
fn apply_theme(is_dark: bool) {
    if let Some(window) = web_sys::window()
        && let Some(document) = window.document()
        && let Some(html) = document.document_element()
    {
        let theme = if is_dark { "dark" } else { "light" };
        let _ = html.set_attribute("data-bs-theme", theme);
    }
}

#[cfg(not(feature = "hydrate"))]
fn apply_theme(_is_dark: bool) {
    // No-op on server
}
