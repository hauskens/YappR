use pyo3::prelude::*;
use std::collections::HashSet;

/// Check if all search words are present in a sentence (any order)
#[pyfunction]
fn search_words_present_in_sentence(sentence: Vec<String>, search_words: Vec<String>) -> bool {
    let sentence_set: HashSet<&str> = sentence.iter().map(|s| s.as_str()).collect();
    search_words.iter().all(|word| sentence_set.contains(word.as_str()))
}

/// Check if search words appear consecutively in sentence (strict/quoted search)
#[pyfunction]
fn search_words_present_in_sentence_strict(sentence: Vec<String>, search_words: Vec<String>) -> bool {
    if search_words.is_empty() {
        return false;
    }

    let sentence_len = sentence.len();
    let search_len = search_words.len();

    if search_len > sentence_len {
        return false;
    }

    // Use sliding window to check for consecutive matches
    for i in 0..=(sentence_len - search_len) {
        let window: Vec<&str> = sentence[i..i + search_len].iter().map(|s| s.as_str()).collect();
        let search_slice: Vec<&str> = search_words.iter().map(|s| s.as_str()).collect();
        
        if window == search_slice {
            return true;
        }
    }
    false
}

/// A Python module implemented in Rust.
#[pymodule]
fn yappr_search(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(search_words_present_in_sentence, m)?)?;
    m.add_function(wrap_pyfunction!(search_words_present_in_sentence_strict, m)?)?;
    Ok(())
}