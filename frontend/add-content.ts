// State variables
let hasSearched = false;
let searchResults: any[] = [];

// HTMX form submission handles Enter key automatically

// URL validation function
function isValidUrl(urlString: string): boolean {
  try {
    const url = new URL(urlString);
    const hostname = url.hostname.toLowerCase();
    return hostname.includes('youtube.com') || 
           hostname.includes('youtu.be') || 
           hostname.includes('twitch.tv') ||
           hostname.includes('clips.twitch.tv');
  } catch (_) {
    return false;
  }
}

// Show broadcaster filter
function showBroadcasterFilter(): void {
  const broadcasterFilter = document.getElementById('broadcaster-filter') as HTMLElement;
  if (broadcasterFilter) {
    broadcasterFilter.style.display = 'block';
  }
}

// Check if URL is found in search results for selected broadcaster
function checkIfUrlFoundInResults(url: string, selectedBroadcasterId: string): boolean {
  if (!isValidUrl(url) || !selectedBroadcasterId) return true;
  
  // Check if the URL exists in search results for the selected broadcaster
  const foundInBroadcaster = searchResults.some(result => 
    result.broadcaster_id === selectedBroadcasterId && 
    (result.url === url || result.original_url === url)
  );
  
  return foundInBroadcaster;
}

// Update "Add to Queue" button visibility and state
function updateAddToQueueButton(): void {
  const urlInput = document.getElementById('url') as HTMLInputElement;
  const broadcasterSelect = document.getElementById('broadcaster_id') as HTMLSelectElement;
  const addBtn = document.getElementById('addToQueueBtn') as HTMLButtonElement;
  const resultsContainer = document.getElementById('results') as HTMLElement;
  
  if (!urlInput || !broadcasterSelect || !addBtn) return;
  
  const url = urlInput.value.trim();
  const selectedBroadcasterId = broadcasterSelect.value;
  const isUrl = isValidUrl(url);
  const isNoContentFound = resultsContainer && resultsContainer.innerHTML.includes('No existing content found');
  
  // Show "Add to Queue" button if:
  // 1. User has searched
  // 2. Input is a valid URL
  // 3. A broadcaster is selected
  // 4. Either no content was found OR the URL doesn't exist for the selected broadcaster
  if (hasSearched && isUrl && selectedBroadcasterId) {
    if (isNoContentFound) {
      // URL not found anywhere - show add button
      addBtn.style.display = 'inline-block';
      addBtn.disabled = false;
    } else {
      // Check if URL exists for the selected broadcaster
      const urlFoundInBroadcaster = checkIfUrlFoundInResults(url, selectedBroadcasterId);
      if (!urlFoundInBroadcaster) {
        addBtn.style.display = 'inline-block';
        addBtn.disabled = false;
      } else {
        addBtn.style.display = 'none';
      }
    }
  } else {
    addBtn.style.display = 'none';
  }
}

// Update broadcaster filter for new content
function updateBroadcasterFilterForNewContent(): void {
  const broadcasterFilter = document.getElementById('broadcaster-filter') as HTMLElement;
  const broadcasterLabel = broadcasterFilter?.querySelector('label') as HTMLLabelElement;
  const broadcasterSelect = document.getElementById('broadcaster_id') as HTMLSelectElement;
  const broadcasterHelp = broadcasterFilter?.querySelector('.form-text') as HTMLElement;
  
  if (broadcasterLabel) {
    broadcasterLabel.textContent = 'Who do you want to suggest this content to?';
  }
  
  if (broadcasterSelect) {
    // Change first option to require selection
    const firstOption = broadcasterSelect.querySelector('option[value=""]') as HTMLOptionElement;
    if (firstOption) {
      firstOption.textContent = 'Select a broadcaster...';
    }
  }
  
  if (broadcasterHelp) {
    broadcasterHelp.textContent = 'Choose which broadcaster\'s queue to add this new content to.';
  }
}

// Handle search completion to show broadcaster filter and store results
function handleSearchComplete(event: any): void {
  hasSearched = true;
  showBroadcasterFilter();
  
  // Check if this was a "No existing content found" response for a URL
  const resultsContainer = document.getElementById('results') as HTMLElement;
  const urlInput = document.getElementById('url') as HTMLInputElement;
  const isNoContentFound = resultsContainer && resultsContainer.innerHTML.includes('No existing content found');
  const isValidUrlInput = urlInput && isValidUrl(urlInput.value.trim());
  
  if (isNoContentFound && isValidUrlInput) {
    // This is a URL that wasn't found - change the broadcaster filter to a queue selector
    updateBroadcasterFilterForNewContent();
    searchResults = []; // No existing results since content wasn't found
  } else {
    // Try to extract search results from the response for existing content
    try {
      if (resultsContainer) {
        // Look for data attributes or hidden elements that might contain result data
        const resultElements = resultsContainer.querySelectorAll('[data-result]');
        searchResults = Array.from(resultElements).map(el => ({
          broadcaster_id: (el as HTMLElement).dataset.broadcasterId,
          url: (el as HTMLElement).dataset.url,
          original_url: (el as HTMLElement).dataset.originalUrl
        }));
      }
    } catch (e) {
      console.warn('Could not parse search results:', e);
      searchResults = [];
    }
  }
  
  updateAddToQueueButton();
}

// Handle submission completion (for "Add to Queue" button)
function handleSubmissionComplete(event: any): void {
  const resultsContainer = document.getElementById('results') as HTMLElement;
  const isSuccessMessage = resultsContainer && resultsContainer.innerHTML.includes('alert-success');
  
  if (isSuccessMessage) {
    // Reset the form after successful submission
    resetForm();
  }
}

// Reset form to initial state
function resetForm(): void {
  const urlInput = document.getElementById('url') as HTMLInputElement;
  const broadcasterSelect = document.getElementById('broadcaster_id') as HTMLSelectElement;
  const broadcasterFilter = document.getElementById('broadcaster-filter') as HTMLElement;
  const addBtn = document.getElementById('addToQueueBtn') as HTMLButtonElement;
  
  // Clear form inputs
  if (urlInput) {
    urlInput.value = '';
  }
  
  if (broadcasterSelect) {
    broadcasterSelect.selectedIndex = 0;
  }
  
  // Hide broadcaster filter and add button
  if (broadcasterFilter) {
    broadcasterFilter.style.display = 'none';
  }
  
  if (addBtn) {
    addBtn.style.display = 'none';
  }
  
  // Reset state variables
  hasSearched = false;
  searchResults = [];
  
  // Revalidate form
  validateForm();
}

// Filter results by broadcaster
function filterResults(): void {
  updateAddToQueueButton();
}

// Form validation
function validateForm(): void {
  const urlInput = document.getElementById('url') as HTMLInputElement;
  const searchBtn = document.getElementById('searchBtn') as HTMLButtonElement;
  const helpIcon = document.getElementById('helpIcon') as HTMLElement;
  
  if (!urlInput || !searchBtn || !helpIcon) return;
  
  const hasContent = urlInput.value.trim() !== '';
  let tooltipText = '';
  
  if (!hasContent) {
    tooltipText = 'Enter a URL or search terms to find content';
    searchBtn.disabled = true;
  } else {
    tooltipText = 'Click search to find existing content or add new content';
    searchBtn.disabled = false;
  }
  
  helpIcon.setAttribute('title', tooltipText);
  helpIcon.setAttribute('data-bs-original-title', tooltipText);
  
  const tooltip = window.bootstrap?.Tooltip?.getInstance(helpIcon);
  if (tooltip) {
    tooltip.dispose();
    new window.bootstrap.Tooltip(helpIcon);
  }
  
  updateAddToQueueButton();
}

// Make functions globally available for onclick handlers
(window as any).validateForm = validateForm;
(window as any).filterResults = filterResults;
(window as any).showBroadcasterFilter = showBroadcasterFilter;
(window as any).handleSearchComplete = handleSearchComplete;
(window as any).handleSubmissionComplete = handleSubmissionComplete;
(window as any).resetForm = resetForm;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  validateForm();
  
  // Initialize tooltips
  const tooltipTriggerList = Array.from(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.forEach(tooltipTriggerEl => {
    new window.bootstrap.Tooltip(tooltipTriggerEl);
  });
  
  // Add event listeners
  const urlInput = document.getElementById('url');
  const broadcasterSelect = document.getElementById('broadcaster_id');
  const contentForm = document.getElementById('contentForm');
  
  if (urlInput) {
    urlInput.addEventListener('input', validateForm);
  }
  
  if (broadcasterSelect) {
    broadcasterSelect.addEventListener('change', filterResults);
  }
  
  // Listen for HTMX events to handle search completion and submission
  const addToQueueBtn = document.getElementById('addToQueueBtn');
  
  if (contentForm) {
    document.body.addEventListener('htmx:afterRequest', function(event: any) {
      // Listen for requests from the form (search)
      if (event.detail.elt === contentForm) {
        handleSearchComplete(event);
      }
      // Listen for requests from the add button (submission)
      else if (event.detail.elt === addToQueueBtn) {
        handleSubmissionComplete(event);
      }
    });
  }
});