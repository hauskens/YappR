// Handle Enter key press in URL input
function handleUrlKeyPress(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    event.preventDefault();
    const searchButton = document.querySelector('[hx-post*="search_content"]') as HTMLButtonElement;
    if (searchButton) {
      searchButton.click();
    }
  }
}

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

// Form validation
function validateForm(): void {
  const urlInput = document.getElementById('url') as HTMLInputElement;
  const broadcasterSelect = document.getElementById('broadcaster_id') as HTMLSelectElement;
  const addBtn = document.getElementById('addToQueueBtn') as HTMLButtonElement;
  const helpIcon = document.getElementById('addQueueHelp') as HTMLElement;
  
  if (!urlInput || !broadcasterSelect || !addBtn || !helpIcon) return;
  
  const hasValidUrl = urlInput.value.trim() !== '' && isValidUrl(urlInput.value.trim());
  const hasBroadcaster = broadcasterSelect.value !== '';
  
  // Update tooltip text based on validation
  let tooltipText = '';
  if (!hasValidUrl && !hasBroadcaster) {
    tooltipText = 'Enter a valid URL and select a broadcaster';
  } else if (!hasValidUrl) {
    tooltipText = 'Enter a valid YouTube or Twitch URL';
  } else if (!hasBroadcaster) {
    tooltipText = 'Select a broadcaster';
  } else {
    tooltipText = 'Ready to add content to the selected broadcaster\'s queue';
  }
  
  // Update help icon tooltip
  helpIcon.setAttribute('title', tooltipText);
  helpIcon.setAttribute('data-bs-original-title', tooltipText);
  
  // Update tooltip instance
  const tooltip = window.bootstrap?.Tooltip?.getInstance(helpIcon);
  if (tooltip) {
    tooltip.dispose();
    new window.bootstrap.Tooltip(helpIcon);
  }
  
  // Enable button only if both URL is valid and broadcaster is selected
  addBtn.disabled = !(hasValidUrl && hasBroadcaster);
}

// Make functions globally available for onclick handlers
(window as any).handleUrlKeyPress = handleUrlKeyPress;
(window as any).validateForm = validateForm;

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
  
  if (urlInput) {
    urlInput.addEventListener('input', validateForm);
    urlInput.addEventListener('keypress', handleUrlKeyPress);
  }
  
  if (broadcasterSelect) {
    broadcasterSelect.addEventListener('change', validateForm);
  }
});