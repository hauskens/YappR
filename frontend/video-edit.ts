
// Debounce function for performance
function debounce<T extends (...args: any[]) => any>(func: T, wait: number): T {
  let timeout: NodeJS.Timeout;
  return ((...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  }) as T;
}

// Text highlighting function
function highlightText(text: string, searchTerm: string): string {
  if (!searchTerm || !text) return text;
  
  const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  return text.replace(regex, '<mark>$1</mark>');
}

// Chat search functionality
function initializeChatSearch(): void {
  const chatSearchInput = document.getElementById('chat-search') as HTMLInputElement;
  const chatMessages = document.querySelectorAll('.chat-message');
  const usernameFilter = document.getElementById('username-filter') as HTMLSelectElement;
  
  if (!chatSearchInput || !chatMessages.length) return;
  
  const performChatSearch = debounce((searchTerm: string, selectedUsername: string) => {
    const normalizedSearch = searchTerm.toLowerCase();
    
    chatMessages.forEach(message => {
      const messageElement = message as HTMLElement;
      const messageText = messageElement.textContent?.toLowerCase() || '';
      const username = messageElement.dataset.username || '';
      
      // Check if message matches search term and username filter
      const matchesSearch = !searchTerm || messageText.includes(normalizedSearch);
      const matchesUser = !selectedUsername || username === selectedUsername;
      
      if (matchesSearch && matchesUser) {
        messageElement.style.display = 'block';
        
        // Highlight search term
        if (searchTerm) {
          const originalText = messageElement.getAttribute('data-original-text') || messageElement.innerHTML;
          messageElement.setAttribute('data-original-text', originalText);
          messageElement.innerHTML = highlightText(originalText, searchTerm);
        } else {
          // Restore original text
          const originalText = messageElement.getAttribute('data-original-text');
          if (originalText) {
            messageElement.innerHTML = originalText;
          }
        }
      } else {
        messageElement.style.display = 'none';
      }
    });
  }, 300);
  
  // Add event listeners
  chatSearchInput.addEventListener('input', (e) => {
    const searchTerm = (e.target as HTMLInputElement).value;
    const selectedUsername = usernameFilter ? usernameFilter.value : '';
    performChatSearch(searchTerm, selectedUsername);
  });
  
  if (usernameFilter) {
    usernameFilter.addEventListener('change', (e) => {
      const selectedUsername = (e.target as HTMLSelectElement).value;
      const searchTerm = chatSearchInput.value;
      performChatSearch(searchTerm, selectedUsername);
    });
  }
}

// Transcription search functionality
function initializeTranscriptionSearch(): void {
  const transcriptionSearchInput = document.getElementById('transcription-search') as HTMLInputElement;
  const transcriptionSegments = document.querySelectorAll('.transcription-segment');
  
  if (!transcriptionSearchInput || !transcriptionSegments.length) return;
  
  const performTranscriptionSearch = debounce((searchTerm: string) => {
    const normalizedSearch = searchTerm.toLowerCase();
    
    transcriptionSegments.forEach(segment => {
      const segmentElement = segment as HTMLElement;
      const segmentText = segmentElement.textContent?.toLowerCase() || '';
      
      if (!searchTerm || segmentText.includes(normalizedSearch)) {
        segmentElement.style.display = 'block';
        
        // Highlight search term
        if (searchTerm) {
          const originalText = segmentElement.getAttribute('data-original-text') || segmentElement.innerHTML;
          segmentElement.setAttribute('data-original-text', originalText);
          segmentElement.innerHTML = highlightText(originalText, searchTerm);
        } else {
          // Restore original text
          const originalText = segmentElement.getAttribute('data-original-text');
          if (originalText) {
            segmentElement.innerHTML = originalText;
          }
        }
      } else {
        segmentElement.style.display = 'none';
      }
    });
  }, 300);
  
  // Add event listener
  transcriptionSearchInput.addEventListener('input', (e) => {
    const searchTerm = (e.target as HTMLInputElement).value;
    performTranscriptionSearch(searchTerm);
  });
}

// Local timestamp conversion for chat messages
function convertTimestamps(): void {
  const timestampElements = document.querySelectorAll('.chat-timestamp[data-utc]');
  
  timestampElements.forEach(element => {
    const utcTime = element.getAttribute('data-utc');
    if (utcTime) {
      const localTime = new Date(utcTime).toLocaleString();
      element.textContent = localTime;
    }
  });
}

// Initialize HTMX integration
function initializeHtmxIntegration(): void {
  // Handle dynamic content loading
  document.body.addEventListener('htmx:afterSwap', (event: any) => {
    // Reinitialize search functionality after dynamic content loads
    if (event.detail.target.classList.contains('chat-container')) {
      initializeChatSearch();
      convertTimestamps();
    }
    
    if (event.detail.target.classList.contains('transcription-container')) {
      initializeTranscriptionSearch();
    }
  });
}

// Initialize everything on page load
document.addEventListener('DOMContentLoaded', () => {
  initializeChatSearch();
  initializeTranscriptionSearch();
  convertTimestamps();
  initializeHtmxIntegration();
});