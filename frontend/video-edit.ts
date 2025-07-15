
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

// Global variable to store the chart instance
let timelineChart: any = null;
let isClearing = false;
let isSearching = false;

// Timeline chart for chat messages
function initializeChatTimeline(): void {
  const chatTimelineCanvas = document.getElementById('chatTimelineChart') as HTMLCanvasElement;
  const intervalSelect = document.getElementById('timelineInterval') as HTMLSelectElement;
  if (!chatTimelineCanvas) return;

  // Function to create/update the chart
  const updateChart = () => {
    if (isClearing || isSearching) return; // Skip chart update during clear/search operations
    
    const chatMessages = document.querySelectorAll('.chat-message');
    if (chatMessages.length === 0) return;

    const selectedInterval = parseInt(intervalSelect?.value || '5');
    const timelineData = processTimelineData(chatMessages, selectedInterval);
    
    const ctx = chatTimelineCanvas.getContext('2d');
    if (!ctx) return;

    // Destroy existing chart if it exists
    if (timelineChart) {
      timelineChart.destroy();
    }

    timelineChart = new (window as any).Chart(ctx, {
    type: 'line',
    data: {
      labels: timelineData.labels,
      datasets: [{
        label: 'Messages per interval',
        data: timelineData.data,
        borderColor: '#007bff',
        backgroundColor: 'rgba(0, 123, 255, 0.1)',
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: {
            display: true,
            text: 'Time'
          }
        },
        y: {
          title: {
            display: true,
            text: 'Message Count'
          },
          beginAtZero: true
        }
      },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          mode: 'index',
          intersect: false
        }
      },
      onClick: (event, elements) => {
        if (elements.length > 0) {
          const elementIndex = elements[0].index;
          const timestampUrl = timelineData.messageUrls[elementIndex];
          if (timestampUrl) {
            window.open(timestampUrl, '_blank');
          }
        }
      }
    }
    });
  };

  // Initial chart creation
  updateChart();

  // Add event listener for interval changes
  if (intervalSelect) {
    intervalSelect.addEventListener('change', updateChart);
  }
}

// Process chat messages to create timeline data
function processTimelineData(chatMessages: NodeListOf<Element>, intervalMinutes: number = 5): { labels: string[], data: number[], messageUrls: (string | null)[] } {
  const messageData: { time: Date, element: Element }[] = [];
  
  // Extract timestamps and elements from messages
  chatMessages.forEach(message => {
    const timestampElement = message.querySelector('.chat-timestamp[data-utc]');
    if (timestampElement) {
      const utcTime = timestampElement.getAttribute('data-utc');
      if (utcTime) {
        messageData.push({ time: new Date(utcTime), element: message });
      }
    }
  });

  if (messageData.length === 0) return { labels: [], data: [], messageUrls: [] };

  // Sort by time
  messageData.sort((a, b) => a.time.getTime() - b.time.getTime());

  // Create time buckets with first message in each bucket
  const buckets = new Map<string, { count: number, firstMessage: Element }>();

  messageData.forEach(({ time, element }) => {
    const bucketTime = new Date(time);
    bucketTime.setMinutes(Math.floor(bucketTime.getMinutes() / intervalMinutes) * intervalMinutes, 0, 0);
    const bucketKey = bucketTime.toISOString();
    
    const existing = buckets.get(bucketKey);
    if (existing !== undefined) {
      existing.count++;
    } else {
      buckets.set(bucketKey, { count: 1, firstMessage: element });
    }
  });

  // Convert to arrays for Chart.js
  const labels: string[] = [];
  const data: number[] = [];
  const messageUrls: (string | null)[] = [];
  
  for (const [bucketKey, bucket] of Array.from(buckets.entries()).sort()) {
    const date = new Date(bucketKey);
    labels.push(date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    data.push(bucket.count);
    
    // Get URL from first message in this bucket
    const timestampLink = bucket.firstMessage.querySelector('a[href*="t="]') as HTMLAnchorElement;
    messageUrls.push(timestampLink ? timestampLink.href : null);
  }

  return { labels, data, messageUrls };
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
    if (event.detail.target.id === 'chat-messages-container') {
      console.log('Chat messages loaded, reinitializing chat search');
      setTimeout(() => initializeChatSearch(), 100);
      convertTimestamps();
      initializeChatTimeline();
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