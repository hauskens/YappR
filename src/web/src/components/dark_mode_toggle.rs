use leptos::prelude::*;

#[cfg(feature = "hydrate")]
use web_sys;

enum Theme {
    Dark,
    Light,
}

impl Theme {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "dark" => Some(Theme::Dark),
            "light" => Some(Theme::Light),
            _ => None,
        }
    }
    pub fn is_dark(&self) -> bool {
        matches!(self, Theme::Dark)
    }
    pub fn default() -> Self {
        Theme::Light
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
            <span class={move || if is_dark_mode.get() { "bi bi-moon-fill" } else { "bi bi-sun-fill" }}></span>
        </button>
    }
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
