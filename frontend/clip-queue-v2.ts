// Clip queue v2 functionality
declare global {
  interface Window {
    htmx: any;
    initializeBalloonFeedback?: () => void;
  }
}

// Global state
let currentClipId: string | null = null;

// Queue update custom event
function triggerQueueUpdate(): void {
  document.body.dispatchEvent(new CustomEvent('queue_update'));
}

// HTMX afterSwap event handler for player initialization
function handleHtmxAfterSwap(): void {
  document.body.addEventListener('htmx:afterSwap', (event: any) => {
    if (event.detail.target.id === 'player-container') {
      initPlayer();
      
      // Update currentClipId from iframe data
      const iframe = event.detail.target.querySelector('iframe[data-clip-id]');
      if (iframe && iframe.getAttribute('data-clip-id')) {
        currentClipId = iframe.getAttribute('data-clip-id');
      }
      
      // Show Next button when clip is playing
      if (currentClipId) {
        const markWatchedBtn = document.getElementById('mark-watched-btn');
        if (markWatchedBtn) markWatchedBtn.style.display = 'block';
      }
    }
    
    // Queue items active state management
    if (event.detail.target.id === 'queue-items' && currentClipId) {
      // Reapply active styling to current clip after queue refresh
      setTimeout(() => {
        const currentItem = document.querySelector(`.queue-item[data-id="${currentClipId}"]`);
        if (currentItem) {
          document.querySelectorAll('.queue-item').forEach(item => {
            item.classList.remove('active', 'bg-primary-subtle', 'border-start', 'border-2', 'border-primary-subtle');
          });
          currentItem.classList.add('active', 'bg-primary-subtle', 'border-start', 'border-2', 'border-primary-subtle');
        }
      }, 100);
    }
    
    // Clip details interactions
    const clipDetailsEl = document.getElementById('clip-details');
    if (clipDetailsEl && (event.detail.target === clipDetailsEl || clipDetailsEl.contains(event.detail.target))) {
      initializeClipDetailsInteractions();
      if (typeof window.initializeBalloonFeedback === 'function') {
        window.initializeBalloonFeedback();
      }
    }
  });
}

// Initialize clip details interactions
function initializeClipDetailsInteractions(): void {
  // Add any clip details specific interactions here
  console.log('Clip details interactions initialized');
}

// Preference management
function initializePreferences(): void {
  const preferShortToggle = document.getElementById('prefer-short-toggle') as HTMLInputElement;
  if (preferShortToggle) {
    const savedPreference = localStorage.getItem('preferShortContent');
    if (savedPreference === null) {
      localStorage.setItem('preferShortContent', 'true');
      preferShortToggle.checked = true;
    } else {
      preferShortToggle.checked = savedPreference === 'true';
    }
    
    // Add event listener for preference changes
    preferShortToggle.addEventListener('change', () => {
      localStorage.setItem('preferShortContent', preferShortToggle.checked.toString());
      
      const upcomingTab = document.getElementById('upcoming');
      if (upcomingTab && upcomingTab.classList.contains('active')) {
        if (window.htmx) {
          window.htmx.trigger('#queue-items', 'queue_update');
        }
      } else {
        if (window.htmx) {
          window.htmx.trigger('#history-items', 'history_update');
        }
      }
    });
  }
}

// Queue update event handler
function handleQueueUpdate(): void {
  document.body.addEventListener('queue_update', () => {
    setTimeout(() => {
      if (currentClipId) {
        const currentItem = document.querySelector(`.queue-item[data-id="${currentClipId}"]`);
        if (currentItem) {
          // Mark item as active
          document.querySelectorAll('.queue-item').forEach(item => {
            item.classList.remove('active', 'bg-primary-subtle', 'border-start', 'border-2', 'border-primary-subtle');
          });
          currentItem.classList.add('active', 'bg-primary-subtle', 'border-start', 'border-2', 'border-primary-subtle');
        }
      }
    }, 100);
  });
}

// Platform settings handling
function handlePlatformSettings(): void {
  document.addEventListener('htmx:afterRequest', (event: any) => {
    if (event.detail.elt && event.detail.elt.id === 'options-tab') {
      if (event.detail.successful) {
        try {
          const response = JSON.parse(event.detail.xhr.responseText);
          if (response.status === 'success') {
            // Update prefer shorter content toggle
            if (response.hasOwnProperty('prefer_shorter_content')) {
              const preferShortToggle = document.getElementById('prefer-short-toggle') as HTMLInputElement;
              if (preferShortToggle) {
                preferShortToggle.checked = response.prefer_shorter_content;
                localStorage.setItem('preferShortContent', response.prefer_shorter_content.toString());
              }
            }
            
            // Update platform checkboxes
            if (response.platforms) {
              document.querySelectorAll('.platform-toggle').forEach(checkbox => {
                (checkbox as HTMLInputElement).checked = false;
              });
              response.platforms.forEach((platform: string) => {
                const checkbox = document.getElementById('platform-' + platform) as HTMLInputElement;
                if (checkbox) {
                  checkbox.checked = true;
                }
              });
            }
          }
        } catch (e) {
          console.error('Error parsing platform settings:', e);
        }
      }
    }
  });
}

// Tab switching and search input management
function initializeTabSwitching(): void {
  const upcomingTab = document.getElementById('upcoming-tab');
  const historyTab = document.getElementById('history-tab');
  const optionsTab = document.getElementById('options-tab');
  const upcomingSearch = document.getElementById('upcoming-search') as HTMLElement;
  const historySearch = document.getElementById('history-search') as HTMLElement;
  
  if (upcomingTab && upcomingSearch && historySearch) {
    upcomingTab.addEventListener('click', () => {
      upcomingSearch.style.display = 'flex';
      historySearch.style.display = 'none';
    });
  }
  
  if (historyTab && upcomingSearch && historySearch) {
    historyTab.addEventListener('click', () => {
      upcomingSearch.style.display = 'none';
      historySearch.style.display = 'flex';
    });
  }
  
  if (optionsTab && upcomingSearch && historySearch) {
    optionsTab.addEventListener('click', () => {
      upcomingSearch.style.display = 'none';
      historySearch.style.display = 'none';
    });
  }
}

// Mark item as watched functionality
function markItemAsWatched(itemId: string, callback?: () => void): void {
  const xhr = new XMLHttpRequest();
  xhr.open('POST', `/clip_queue/mark_watched/${itemId}`);
  xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
  
  if (window.csrfToken) {
    xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
  }
  
  xhr.onload = function() {
    if (xhr.status === 200) {
      if (typeof callback === 'function') callback();
      if (window.htmx) {
        window.htmx.trigger(document.body, 'queue_update');
        window.htmx.trigger(document.body, 'history_update');
      }
    }
  };
  xhr.send();
}

// Mark current watched and advance to next clip
function markCurrentWatched(): void {
  let itemId = currentClipId;
  
  if (!itemId) {
    const activeItem = document.querySelector('.queue-item.active');
    if (!activeItem) return;
    itemId = activeItem.getAttribute('data-item-id');
  }
  
  if (!itemId) return;
  
  // Find next clip logic and mark current as watched
  const upcomingTab = document.getElementById('upcoming');
  const activeQueue = upcomingTab && upcomingTab.classList.contains('active') 
    ? document.getElementById('queue-items') 
    : document.getElementById('history-items');
    
  if (!activeQueue) {
    markItemAsWatched(itemId);
    return;
  }
  
  const activeItem = document.querySelector('.queue-item.active');
  if (!activeItem) {
    markItemAsWatched(itemId);
    return;
  }
  
  const queueItems = activeQueue.querySelectorAll('.queue-item:not(.watched-item)');
  let nextIndex = -1;
  
  for (let i = 0; i < queueItems.length; i++) {
    if (queueItems[i] === activeItem) {
      nextIndex = i + 1;
      break;
    }
  }
  
  if (nextIndex >= 0 && nextIndex < queueItems.length) {
    const nextItem = queueItems[nextIndex];
    const nextItemId = nextItem.getAttribute('data-id');
    
    if (nextItemId) {
      markItemAsWatched(itemId, () => {
        currentClipId = nextItemId;
        localStorage.setItem('activeQueueItemId', nextItemId);
        
        if (window.htmx) {
          window.htmx.ajax('GET', `/clip_queue/player/${nextItemId}`, '#player-container');
          window.htmx.ajax('GET', `/clip_queue/details/${nextItemId}`, '#clip-details');
        }
      });
    } else {
      markItemAsWatched(itemId);
    }
  } else {
    markItemAsWatched(itemId, () => {
      // Show completion message
      const playerMessage = document.getElementById('player-message');
      const playerContainer = document.getElementById('player-container');
      if (playerMessage && playerContainer) {
        playerMessage.innerHTML = '<div class="d-flex align-items-center justify-content-center h-100"><div class="text-center"><h3>All clips have been watched!</h3><p>There are no more clips in the queue.</p></div></div>';
        playerContainer.style.display = 'none';
        playerMessage.style.display = 'block';
      }
      
      const markWatchedBtn = document.getElementById('mark-watched-btn');
      if (markWatchedBtn) markWatchedBtn.style.display = 'none';
    });
  }
}

// Initialize player function
function initPlayer(): void {
  const playerContainer = document.getElementById('player-container') as HTMLElement;
  const playerMessage = document.getElementById('player-message') as HTMLElement;
  
  if (playerContainer && playerContainer.dataset && playerContainer.dataset.clipId) {
    currentClipId = playerContainer.dataset.clipId;
    console.log('Set currentClipId to:', currentClipId);
  }
  
  if (playerContainer && playerMessage) {
    if (playerContainer.querySelector('iframe')) {
      playerContainer.style.display = 'block';
      playerMessage.style.display = 'none';
    } else {
      playerContainer.style.display = 'none';
      playerMessage.style.display = 'block';
    }
  }
  console.log('Player initialized');
}

// Make functions globally available for onclick handlers
(window as any).markCurrentWatched = markCurrentWatched;
(window as any).initPlayer = initPlayer;
(window as any).markItemAsWatched = markItemAsWatched;
(window as any).initializeClipDetailsInteractions = initializeClipDetailsInteractions;

// Initialize everything on page load
document.addEventListener('DOMContentLoaded', () => {
  initializePreferences();
  handleQueueUpdate();
  handlePlatformSettings();
  initializeTabSwitching();
  handleHtmxAfterSwap();
});