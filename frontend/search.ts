// Reset spinner state when page loads
function resetSpinner() {
    const searchSpinner = document.getElementById('search-spinner');
    if (searchSpinner) {
        searchSpinner.classList.add('d-none');
    }
    const searchText = document.getElementById('search-text');
    if (searchText) {
        searchText.textContent = 'Search';
    }
}

document.addEventListener('DOMContentLoaded', resetSpinner);
window.addEventListener('pageshow', resetSpinner);

const searchForm = document.getElementById('search-form');
if (searchForm) {
    searchForm.addEventListener('submit', function() {
        // Show spinner
        const searchSpinner = document.getElementById('search-spinner');
        if (searchSpinner) {
            searchSpinner.classList.remove('d-none');
        }
        // Optionally change button text
        const searchText = document.getElementById('search-text');
        if (searchText) {
            if (Math.random() < 0.1) {
                searchText.textContent = 'Looking...';
            } else {
                searchText.textContent = 'Searching...';
            }
        }
    });
}