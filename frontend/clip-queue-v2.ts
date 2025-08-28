// Clip queue v2 functionality
declare global {
  interface Window {
    htmx: any;
    // initializeBalloonFeedback?: () => void;
  }
}

// Global state
let currentClipId: string | null = null;
let isResizing = false;
let currentQueueWidth = 400; // Default width

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
      // if (typeof window.initializeBalloonFeedback === 'function') {
      //   window.initializeBalloonFeedback();
      // }
    }
    
    // Reinitialize popovers after any HTMX swap
    initializePopovers();
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
            
            // Update weight settings
            updateWeightSettingsForm(response);
            
            // Initialize toggle visibility after settings are loaded
            setTimeout(() => initializeToggleVisibility(), 100);
          }
        } catch (e) {
          console.error('Error parsing platform settings:', e);
        }
      }
    }
  });
}

// Update weight settings form with server data
function updateWeightSettingsForm(data: any): void {
  // Boolean weight settings
  const booleanFields = [
    { backend: 'prefer_shorter', frontend: 'prefer-shorter' },
    { backend: 'keep_fresh', frontend: 'keep-fresh' },
    { backend: 'ignore_popularity', frontend: 'ignore-popularity' },
    { backend: 'boost_variety', frontend: 'boost-variety' },
    { backend: 'viewer_priority', frontend: 'viewer-priority' }
  ];
  booleanFields.forEach(fieldMapping => {
    if (data.hasOwnProperty(fieldMapping.backend)) {
      const checkbox = document.getElementById(fieldMapping.frontend) as HTMLInputElement;
      if (checkbox) {
        checkbox.checked = data[fieldMapping.backend];
        // Update visibility after setting the checkbox state
        toggleSettingVisibility(fieldMapping.frontend);
      }
    }
  });
  
  // Range/numeric weight settings
  const rangeFields = [
    { backend: 'prefer_shorter_intensity', frontend: 'prefer-shorter-intensity' },
    { backend: 'keep_fresh_intensity', frontend: 'keep-fresh-intensity' },
    { backend: 'ignore_popularity_intensity', frontend: 'ignore-popularity-intensity' },
    { backend: 'boost_variety_intensity', frontend: 'boost-variety-intensity' },
    { backend: 'viewer_priority_intensity', frontend: 'viewer-priority-intensity' },
    { backend: 'short_clip_threshold_seconds', frontend: 'short-clip-threshold' },
    { backend: 'freshness_window_minutes', frontend: 'freshness-window' }
  ];
  rangeFields.forEach(fieldMapping => {
    if (data.hasOwnProperty(fieldMapping.backend)) {
      const input = document.getElementById(fieldMapping.frontend) as HTMLInputElement;
      if (input) {
        input.value = data[fieldMapping.backend].toString();
        // Update the value badge
        const valueSpan = document.getElementById(fieldMapping.frontend + '-value');
        if (valueSpan) {
          valueSpan.textContent = data[fieldMapping.backend].toString();
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
  
  // Always get the first unwatched item (excluding the currently active one)
  let nextItem = null;
  for (let i = 0; i < queueItems.length; i++) {
    if (queueItems[i] !== activeItem) {
      nextItem = queueItems[i];
      break;
    }
  }
  
  if (nextItem) {
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
(window as any).toggleSettingVisibility = toggleSettingVisibility;

// Resize functionality
function initializeResize(): void {
  const resizeHandle = document.getElementById('resize-handle');
  const queueElement = document.querySelector('.resizable-queue') as HTMLElement;
  
  if (!resizeHandle || !queueElement) return;
  
  // Load saved width from localStorage
  const savedWidth = localStorage.getItem('queueWidth');
  if (savedWidth) {
    const width = parseInt(savedWidth, 10);
    if (width >= 250 && width <= 800) {
      currentQueueWidth = width;
      queueElement.style.setProperty('width', `${width}px`, 'important');
      queueElement.style.setProperty('flex', `0 0 ${width}px`, 'important');
    }
  }
  
  // Check if we're on mobile
  const isMobile = (): boolean => {
    return window.matchMedia('(max-width: 991.98px)').matches;
  };
  
  let startX = 0;
  let startWidth = 0;
  
  const handleMouseDown = (e: PointerEvent): void => {
    if (isMobile()) return; // Disable on mobile
    
    isResizing = true;
    startX = e.clientX;
    startWidth = currentQueueWidth;
    
    // Use pointer capture for reliable drag handling
    resizeHandle.setPointerCapture(e.pointerId);
    resizeHandle.addEventListener('pointermove', handlePointerMove);
    resizeHandle.addEventListener('pointerup', handlePointerUp);
    resizeHandle.addEventListener('lostpointercapture', handlePointerUp);
    
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    
    e.preventDefault();
  };
  
  const handlePointerMove = (e: PointerEvent): void => {
    if (!isResizing) return;
    
    const deltaX = startX - e.clientX;
    const newWidth = startWidth + deltaX;
    
    // Apply constraints
    const minWidth = 250;
    const maxWidth = Math.min(800, window.innerWidth * 0.6);
    const constrainedWidth = Math.max(minWidth, Math.min(maxWidth, newWidth));
    
    currentQueueWidth = constrainedWidth;
    queueElement.style.setProperty('width', `${constrainedWidth}px`, 'important');
    queueElement.style.setProperty('flex', `0 0 ${constrainedWidth}px`, 'important');
  };
  
  const handlePointerUp = (e: PointerEvent): void => {
    if (!isResizing) return;
    
    isResizing = false;
    resizeHandle.releasePointerCapture(e.pointerId);
    resizeHandle.removeEventListener('pointermove', handlePointerMove);
    resizeHandle.removeEventListener('pointerup', handlePointerUp);
    resizeHandle.removeEventListener('lostpointercapture', handlePointerUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    
    // Save to localStorage
    localStorage.setItem('queueWidth', currentQueueWidth.toString());
  };
  
  // Add touch support for tablets
  const handleTouchStart = (e: TouchEvent): void => {
    if (isMobile()) return; // Disable on mobile
    
    // Make sure we have at least one touch point
    if (e.touches.length === 0) return;
    
    isResizing = true;
    startX = e.touches[0]?.clientX || 0;
    startWidth = currentQueueWidth;
    
    document.addEventListener('touchmove', handleTouchMove, { passive: false });
    document.addEventListener('touchend', handleTouchEnd);
    document.body.style.userSelect = 'none';
    
    e.preventDefault();
  };
  
  const handleTouchMove = (e: TouchEvent): void => {
    if (!isResizing) return;
    
    // Make sure we have at least one touch point
    if (e.touches.length === 0) return;
    
    const deltaX = startX - (e.touches[0]?.clientX || 0);
    const newWidth = startWidth + deltaX;
    
    // Apply constraints
    const minWidth = 250;
    const maxWidth = Math.min(800, window.innerWidth * 0.6);
    const constrainedWidth = Math.max(minWidth, Math.min(maxWidth, newWidth));
    
    currentQueueWidth = constrainedWidth;
    queueElement.style.setProperty('width', `${constrainedWidth}px`, 'important');
    queueElement.style.setProperty('flex', `0 0 ${constrainedWidth}px`, 'important');
    
    e.preventDefault();
  };
  
  const handleTouchEnd = (): void => {
    if (!isResizing) return;
    
    isResizing = false;
    document.removeEventListener('touchmove', handleTouchMove);
    document.removeEventListener('touchend', handleTouchEnd);
    document.body.style.userSelect = '';
    
    // Save to localStorage
    localStorage.setItem('queueWidth', currentQueueWidth.toString());
  };
  
  // Handle window resize to adjust max width constraint
  const handleWindowResize = (): void => {
    if (isMobile()) {
      // Reset width on mobile
      queueElement.style.width = '';
      return;
    }
    
    const maxWidth = Math.min(800, window.innerWidth * 0.6);
    if (currentQueueWidth > maxWidth) {
      currentQueueWidth = maxWidth;
      queueElement.style.setProperty('width', `${maxWidth}px`, 'important');
      queueElement.style.setProperty('flex', `0 0 ${maxWidth}px`, 'important');
      localStorage.setItem('queueWidth', currentQueueWidth.toString());
    }
  };
  
  // Event listeners
  resizeHandle.addEventListener('pointerdown', handleMouseDown);
  resizeHandle.addEventListener('touchstart', handleTouchStart);
  window.addEventListener('resize', handleWindowResize);
}

// Toggle visibility of setting bars based on toggle states
function toggleSettingVisibility(toggleId: string): void {
  const toggle = document.getElementById(toggleId) as HTMLInputElement;
  const settingsDiv = document.getElementById(toggleId + '-settings') as HTMLElement;
  
  if (toggle && settingsDiv) {
    if (toggle.checked) {
      settingsDiv.style.display = 'block';
    } else {
      settingsDiv.style.display = 'none';
    }
  }
}

// Initialize toggle visibility states
function initializeToggleVisibility(): void {
  const toggles = ['prefer-shorter', 'keep-fresh', 'ignore-popularity', 'viewer-priority'];
  
  toggles.forEach(function(toggleId) {
    const toggle = document.getElementById(toggleId) as HTMLInputElement;
    if (toggle) {
      // Set initial visibility
      toggleSettingVisibility(toggleId);
      
      // Add event listener for changes
      toggle.addEventListener('change', () => {
        toggleSettingVisibility(toggleId);
      });
    }
  });
}

// Weight settings functionality
function initializeWeightSettings(): void {
  function attachRangeUpdaters(): void {
    const rangeInputs = document.querySelectorAll('input[type="range"].weight-setting') as NodeListOf<HTMLInputElement>;
    rangeInputs.forEach(input => {
      const valueSpan = document.getElementById(input.id + '-value');
      if (valueSpan) {
        // Remove existing listener to avoid duplicates
        if ((input as any)._rangeUpdater) {
          input.removeEventListener('input', (input as any)._rangeUpdater);
        }
        // Create and store the updater function
        (input as any)._rangeUpdater = function(this: HTMLInputElement) {
          if (valueSpan) {
            valueSpan.textContent = this.value;
          }
        };
        input.addEventListener('input', (input as any)._rangeUpdater);
      }
    });
  }
  
  // Initial attachment
  attachRangeUpdaters();
  initializeToggleVisibility();
  
  // Re-attach after HTMX swaps (for reset functionality)
  document.body.addEventListener('htmx:afterSwap', (event: any) => {
    if (event.detail.target && event.detail.target.matches('#weight-settings-collapse .card-body')) {
      attachRangeUpdaters();
      initializeToggleVisibility();
    }
  });
}

// Show preview in player area
// Keep track of the preview state
let isPreviewVisible = false;
let originalPlayerContent: string | null = null;

function togglePreviewInPlayer(): void {
  const playerArea = document.getElementById('player-area');
  const previewButtonText = document.getElementById('preview-button-text');
  if (!playerArea) return;

  if (!isPreviewVisible) {
    // Store original content
    originalPlayerContent = playerArea.innerHTML;
    
    // Show preview alongside original content
    playerArea.innerHTML = `
      <div class="d-flex h-100">
        <div class="flex-fill me-3" style="flex: 1;">
          ${originalPlayerContent}
        </div>
        <div class="preview-container border rounded p-3" style="flex: 1;">
          <div class="d-flex justify-content-between align-items-center mb-3">
            <h6 class="mb-0">Queue Preview</h6>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="togglePreviewInPlayer()">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
          <div id="preview-content">
            <div class="text-center">
              <div class="spinner-border" role="status">
                <span class="visually-hidden">Loading...</span>
              </div>
              <p class="mt-2">Loading preview...</p>
            </div>
          </div>
        </div>
      </div>
    `;
    
    isPreviewVisible = true;
    updateButtonText();
    
    // Load preview content
    updatePreviewIfVisible();
  } else {
    // Restore original content
    if (originalPlayerContent) {
      playerArea.innerHTML = originalPlayerContent;
      originalPlayerContent = null;
    }
    
    // Show initial message
    const newInitialMessage = document.getElementById('initial-message');
    if (newInitialMessage) {
      newInitialMessage.style.display = 'flex';
    }
    
    isPreviewVisible = false;
    updateButtonText();
  }
}

function updateButtonText(): void {
  const previewButtonText = document.getElementById('preview-button-text');
  if (previewButtonText) {
    previewButtonText.textContent = isPreviewVisible ? 'Hide Preview' : 'Show Preview';
  }
}

// Function to update the preview if it's currently visible
function updatePreviewIfVisible(): void {
  if (!isPreviewVisible) return;
  
  const previewContentArea = document.getElementById('preview-content');
  if (!previewContentArea) return;
  
  // Get form data
  const form = document.getElementById('platform-settings-form') as HTMLFormElement;
  if (!form) return;
  
  const formData = new FormData(form);
  
  // Update preview content without showing loading state
  if (window.htmx) {
    window.htmx.ajax('POST', '/clip_queue/weight_settings_preview', {
      target: '#preview-content',
      swap: 'innerHTML',
      values: formData,
      indicator: false // Disable automatic indicators
    });
  }
}

// Make functions globally available
(window as any).togglePreviewInPlayer = togglePreviewInPlayer;
(window as any).updatePreviewIfVisible = updatePreviewIfVisible;

// Initialize weight settings preview updates
function initializeWeightSettingsPreviewUpdates(): void {
  const form = document.getElementById('platform-settings-form');
  if (!form) return;
  
  // Update preview when form changes
  form.addEventListener('change', () => {
    // Use a small debounce to avoid too many updates
    setTimeout(() => updatePreviewIfVisible(), 300);
  });
  
  // Listen for HTMX events in case elements are updated via HTMX
  document.body.addEventListener('htmx:afterSwap', (event) => {
    const target = (event as any).detail.target;
    // Check if the swap happened inside the weight settings
    if (target && target.closest && target.closest('#weight-settings-collapse')) {
      updatePreviewIfVisible();
    }
  });
}

// Popover management
function initializePopovers(): void {
  // Dispose of existing popovers first
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach(element => {
    const existingPopover = (window as any).bootstrap?.Popover?.getInstance(element);
    if (existingPopover) {
      existingPopover.dispose();
    }
  });
  
  // Initialize new popovers with proper dismissal behavior
  const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
  popoverTriggerList.map(function (popoverTriggerEl: Element) {
    return new (window as any).bootstrap.Popover(popoverTriggerEl, {
      trigger: 'click',
      placement: 'auto',
      dismissible: true
    });
  });
  
  // Add global click handler to dismiss popovers when clicking elsewhere
  document.addEventListener('click', function(event: Event) {
    const target = event.target as Element;
    
    // Don't dismiss if clicking on a popover trigger or inside a popover
    if (target.closest('[data-bs-toggle="popover"]') || target.closest('.popover')) {
      return;
    }
    
    // Dismiss all open popovers
    document.querySelectorAll('[data-bs-toggle="popover"]').forEach(element => {
      const popover = (window as any).bootstrap?.Popover?.getInstance(element);
      if (popover) {
        popover.hide();
      }
    });
  });
}

// Initialize priority settings collapse behavior
function initializePrioritySettingsCollapse(): void {
  const collapseElement = document.getElementById('weight-settings-collapse');
  if (collapseElement) {
    collapseElement.addEventListener('shown.bs.collapse', () => {
      // Auto-open preview when priority settings are expanded
      if (!isPreviewVisible) {
        togglePreviewInPlayer();
      }
    });
    
    collapseElement.addEventListener('hidden.bs.collapse', () => {
      // Auto-close preview when priority settings are collapsed
      if (isPreviewVisible) {
        togglePreviewInPlayer();
      }
    });
  }
}

// Initialize everything on page load
document.addEventListener('DOMContentLoaded', () => {
  initializePreferences();
  handleQueueUpdate();
  handlePlatformSettings();
  initializeTabSwitching();
  handleHtmxAfterSwap();
  initializeResize();
  initializeWeightSettingsPreviewUpdates();
  initializeWeightSettings();
  initializePopovers();
  initializePrioritySettingsCollapse();
});