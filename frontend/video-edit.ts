
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
  const chatSearchInput = document.getElementById('chatSearchInput') as HTMLInputElement;
  const usernameFilter = document.getElementById('userFilter') as HTMLSelectElement;
  const clearSearchBtn = document.getElementById('clearSearchBtn') as HTMLButtonElement;
  
  if (!chatSearchInput) {
    console.warn('Chat search input not found');
    return;
  }
  
  const performChatSearch = debounce((searchTerm: string, selectedUsername: string) => {
    const normalizedSearch = searchTerm.toLowerCase();
    const chatMessages = document.querySelectorAll('.chat-message');
    chatMessages.forEach(message => {
      const messageElement = message as HTMLElement;
      const messageTextElement = messageElement.querySelector('.chat-text');
      const messageText = messageTextElement?.textContent?.toLowerCase() || '';
      const username = messageElement.dataset.username || '';
      
      // Check if message matches search term and username filter
      const matchesSearch = !searchTerm || messageText.includes(normalizedSearch);
      const matchesUser = !selectedUsername || username === selectedUsername;
      
      if (matchesSearch && matchesUser) {
        messageElement.style.display = '';
        
        // Highlight search term in message text only
        if (searchTerm && messageTextElement) {
          const originalText = messageTextElement.getAttribute('data-original-text') || messageTextElement.innerHTML;
          messageTextElement.setAttribute('data-original-text', originalText);
          messageTextElement.innerHTML = highlightText(originalText, searchTerm);
        } else if (messageTextElement) {
          // Restore original text
          const originalText = messageTextElement.getAttribute('data-original-text');
          if (originalText) {
            messageTextElement.innerHTML = originalText;
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
  
  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', () => {
      chatSearchInput.value = '';
      if (usernameFilter) usernameFilter.value = '';
      performChatSearch('', '');
    });
  }
}

// Transcription search functionality
function initializeTranscriptionSearch(): void {
  const transcriptionSearchInput = document.getElementById('transcriptSearchInput') as HTMLInputElement;
  const clearTranscriptSearchBtn = document.getElementById('clearTranscriptSearchBtn') as HTMLButtonElement;
  
  if (!transcriptionSearchInput) {
    console.warn('Transcription search input not found');
    return;
  }
  
  const performTranscriptionSearch = debounce((searchTerm: string) => {
    const normalizedSearch = searchTerm.toLowerCase();
    const transcriptionSegments = document.querySelectorAll('.transcript-row');
    console.log('Performing transcription search, found segments:', transcriptionSegments.length);
    
    transcriptionSegments.forEach(segment => {
      const segmentElement = segment as HTMLElement;
      const segmentText = segmentElement.textContent?.toLowerCase() || '';
      
      if (!searchTerm || segmentText.includes(normalizedSearch)) {
        segmentElement.style.display = '';
        
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
  
  if (clearTranscriptSearchBtn) {
    clearTranscriptSearchBtn.addEventListener('click', () => {
      transcriptionSearchInput.value = '';
      performTranscriptionSearch('');
    });
  }
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
    console.log('HTMX after swap event:', event.detail.target);
    // Reinitialize search functionality after dynamic content loads
    if (event.detail.target.id === 'chat-messages-container') {
      console.log('Chat messages loaded, reinitializing chat search');
      setTimeout(() => initializeChatSearch(), 100);
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