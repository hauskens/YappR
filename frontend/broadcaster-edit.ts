// Broadcaster edit functionality
let twitchPlatformId: string | null = null;

// // Find Twitch platform ID and setup
function initializeBroadcasterEdit(): void {
  const platformSelect = document.getElementById('platform_id') as HTMLSelectElement;
  if (!platformSelect) return;
  
  const options = platformSelect.options;
  
  for (let i = 0; i < options.length; i++) {
    if (options[i]?.text.toLowerCase() === 'twitch') {
      twitchPlatformId = options[i].value;
      break;
    }
  }
  
  toggleTwitchLookup();
  
  const lookupButton = document.getElementById('lookup-twitch-id');
  if (lookupButton) {
    lookupButton.addEventListener('click', lookupTwitchId);
  }
  
  // Add platform select change listener
  platformSelect.addEventListener('change', toggleTwitchLookup);
  
  // Auto-fade success messages
  setTimeout(() => {
    const alerts = document.querySelectorAll('#settings-feedback .alert-success');
    alerts.forEach(alert => {
      (alert as HTMLElement).style.opacity = '0';
      setTimeout(() => alert.remove(), 300);
    });
  }, 3000);
}

// Toggle Twitch lookup visibility
function toggleTwitchLookup(): void {
  const platformSelect = document.getElementById('platform_id') as HTMLSelectElement;
  const lookupContainer = document.getElementById('twitch-lookup-container') as HTMLElement;
  
  if (platformSelect && lookupContainer) {
    if (platformSelect.value === twitchPlatformId) {
      lookupContainer.style.display = 'block';
    } else {
      lookupContainer.style.display = 'none';
    }
  }
}

// Lookup Twitch ID from username
function lookupTwitchId(): void {
  const usernameInput = document.getElementById('twitch_username') as HTMLInputElement;
  const statusElement = document.getElementById('twitch-lookup-status') as HTMLElement;
  const platformRefInput = document.getElementById('platform_ref') as HTMLInputElement;
  const channelIdInput = document.getElementById('channel_id') as HTMLInputElement;
  
  if (!usernameInput || !statusElement || !platformRefInput || !channelIdInput) return;
  
  const username = usernameInput.value.trim();
  
  if (!username) {
    alert('Please enter a Twitch username');
    return;
  }
  
  // Show loading indicator
  statusElement.innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
  statusElement.style.display = 'inline-block';
  
  // Make API request
  fetch(`/api/lookup_twitch_id?username=${encodeURIComponent(username)}`)
    .then(response => response.json())
    .then(data => {
      if (data.success && data.user_id) {
        statusElement.innerHTML = '<i class="bi bi-check-circle-fill text-success" style="font-size: 1.5rem;"></i>';
        platformRefInput.value = data.user_id;
        channelIdInput.value = data.user_id;
        
        const nameInput = document.getElementById('name') as HTMLInputElement;
        if (nameInput && nameInput.value.trim() === '' && data.display_name) {
          nameInput.value = data.display_name;
        }
      } else {
        statusElement.innerHTML = '<i class="bi bi-x-circle-fill text-danger" style="font-size: 1.5rem;"></i>';
        if (data.error) {
          console.error('Error looking up Twitch ID:', data.error);
        }
      }
    })
    .catch(error => {
      statusElement.innerHTML = '<i class="bi bi-x-circle-fill text-danger" style="font-size: 1.5rem;"></i>';
      console.error('Error looking up Twitch ID:', error);
    });
}

// HTMX event listeners
function setupHtmxEventListeners(): void {
  document.body.addEventListener('htmx:beforeRequest', (evt) => {
    const spinner = document.getElementById('settings-spinner') as HTMLElement;
    if (spinner) {
      spinner.style.display = 'block';
    }
  });

  document.body.addEventListener('htmx:afterRequest', (evt) => {
    const spinner = document.getElementById('settings-spinner') as HTMLElement;
    if (spinner) {
      spinner.style.display = 'none';
    }
  });
}

// Make functions globally available for onclick handlers
(window as any).toggleTwitchLookup = toggleTwitchLookup;
(window as any).lookupTwitchId = lookupTwitchId;

// Chat log upload functionality
function initializeChatLogUpload(): void {
  const fileInput = document.getElementById('chatlog-files') as HTMLInputElement;
  const channelSelect = document.getElementById('channel-select') as HTMLSelectElement;
  const uploadButton = document.getElementById('upload-chatlogs') as HTMLButtonElement;
  const fileList = document.getElementById('file-list') as HTMLElement;
  const selectedFilesList = document.getElementById('selected-files') as HTMLUListElement;

  if (!fileInput || !channelSelect || !uploadButton) return;

  // Handle file selection
  fileInput.addEventListener('change', () => {
    const files = fileInput.files;
    if (files && files.length > 0) {
      // Show selected files
      selectedFilesList.innerHTML = '';
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (!file) continue;
        
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.innerHTML = `
          <span><i class="bi bi-file-text me-2"></i>${file.name}</span>
          <span class="badge bg-secondary">${(file.size / 1024).toFixed(1)} KB</span>
        `;
        selectedFilesList.appendChild(li);
      }
      fileList.style.display = 'block';
    } else {
      fileList.style.display = 'none';
    }
    
    updateUploadButtonState();
  });

  // Handle channel selection change
  channelSelect.addEventListener('change', updateUploadButtonState);

  // Handle upload button click
  uploadButton.addEventListener('click', uploadChatLogs);
}

function updateUploadButtonState(): void {
  const fileInput = document.getElementById('chatlog-files') as HTMLInputElement;
  const channelSelect = document.getElementById('channel-select') as HTMLSelectElement;
  const uploadButton = document.getElementById('upload-chatlogs') as HTMLButtonElement;

  if (!fileInput || !channelSelect || !uploadButton) return;

  const hasFiles = fileInput.files && fileInput.files.length > 0;
  const hasChannel = channelSelect.value !== '';

  uploadButton.disabled = !(hasFiles && hasChannel);
}

async function uploadChatLogs(): Promise<void> {
  const fileInput = document.getElementById('chatlog-files') as HTMLInputElement;
  const channelSelect = document.getElementById('channel-select') as HTMLSelectElement;
  const progressDiv = document.getElementById('upload-progress') as HTMLElement;
  const progressBar = document.getElementById('upload-progress-bar') as HTMLElement;
  const statusDiv = document.getElementById('upload-status') as HTMLElement;
  const resultsDiv = document.getElementById('upload-results') as HTMLElement;
  const uploadButton = document.getElementById('upload-chatlogs') as HTMLButtonElement;

  if (!fileInput || !channelSelect || !fileInput.files) return;

  const files = fileInput.files;
  const channelId = channelSelect.value;

  // Show progress
  progressDiv.style.display = 'block';
  uploadButton.disabled = true;
  resultsDiv.innerHTML = '';

  let successCount = 0;
  let errorCount = 0;
  const results: string[] = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    if (!file) continue;
    const progress = Math.round(((i + 1) / files.length) * 100);
    
    progressBar.style.width = `${progress}%`;
    progressBar.textContent = `${progress}%`;
    statusDiv.textContent = `Processing ${file?.name}... (${i + 1}/${files.length})`;

    try {
      const formData = new FormData();
      formData.append('chatlog_file', file);
      formData.append('channel_id', channelId);

      const response = await fetch('/api/upload_chatlog', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();

      if (result.success) {
        successCount++;
        results.push(`<div class="alert alert-success">✓ ${file.name}: ${result.message}</div>`);
      } else {
        errorCount++;
        results.push(`<div class="alert alert-danger">✗ ${file.name}: ${result.error}</div>`);
      }
    } catch (error) {
      errorCount++;
      results.push(`<div class="alert alert-danger">✗ ${file.name}: Upload failed - ${error}</div>`);
    }
  }

  // Update final status
  statusDiv.innerHTML = `
    <strong>Upload Complete:</strong> 
    <span class="text-success">${successCount} successful</span>, 
    <span class="text-danger">${errorCount} failed</span>
  `;

  // Show results
  resultsDiv.innerHTML = results.join('');

  // Reset form
  uploadButton.disabled = false;
  if (successCount > 0) {
    fileInput.value = '';
    document.getElementById('file-list')!.style.display = 'none';
    updateUploadButtonState();
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  initializeBroadcasterEdit();
  setupHtmxEventListeners();
  initializeChatLogUpload();
  
  // Fix Bootstrap dropdown placement issues
  const dropdowns = document.querySelectorAll('[data-bs-toggle="dropdown"]');
  dropdowns.forEach(dropdown => {
    if (!dropdown.hasAttribute('data-bs-placement')) {
      dropdown.setAttribute('data-bs-placement', 'bottom');
    }
  });
});