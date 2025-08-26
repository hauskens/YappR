// Broadcaster edit functionality
let twitchPlatformId: string | null = null;

// Helper function to add CSRF token to FormData
function addCsrfToken(formData: FormData): void {
  if ((window as any).csrfToken) {
    formData.set('csrf_token', (window as any).csrfToken);
  }
}

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

// Channel Link Management Modal functionality
function showChannelLinkModal(channelId: number, channelName: string, currentSourceChannelId: number | null, currentSourceChannelName: string): void {
  const modal = document.getElementById('channelLinkModal') as any;
  const form = document.getElementById('channelLinkForm') as HTMLFormElement;
  const saveBtn = document.getElementById('saveChannelLinkBtn') as HTMLButtonElement;
  const modalTitle = document.getElementById('channelLinkModalLabel') as HTMLElement;
  const dropdown = document.getElementById('modal_link_channel_id') as HTMLSelectElement;
  
  if (!modal || !form || !saveBtn || !dropdown) return;
  
  // Update modal title and form action
  modalTitle.textContent = `Manage Channel Link - ${channelName}`;
  form.action = `/channel/${channelId}/link`;
  
  // Clear and populate dropdown with channels from the same broadcaster
  dropdown.innerHTML = '<option value="None">None (No source channel)</option>';
  
  // Get all channels for this broadcaster from the table
  const channelRows = document.querySelectorAll('tbody tr');
  channelRows.forEach(row => {
    const rowChannelId = parseInt(row.querySelector('td:first-child')?.textContent || '0');
    const rowChannelName = row.querySelector('td:nth-child(3)')?.textContent;
    
    if (rowChannelId && rowChannelId !== channelId && rowChannelName) {
      const option = document.createElement('option');
      option.value = rowChannelId.toString();
      option.textContent = rowChannelName;
      
      if (currentSourceChannelId && rowChannelId === currentSourceChannelId) {
        option.selected = true;
      }
      
      dropdown.appendChild(option);
    }
  });
  
  // Show current status
  updateChannelLinkPreview(dropdown, currentSourceChannelName);
  
  // Add change listener for preview
  dropdown.onchange = () => updateChannelLinkPreview(dropdown);
  
  // Set up the save button click handler
  saveBtn.onclick = () => handleChannelLinkSubmit(channelId, channelName);
  
  // Show the modal
  const modalInstance = new (window as any).bootstrap.Modal(modal);
  modalInstance.show();
}

function updateChannelLinkPreview(dropdown: HTMLSelectElement, currentSourceName?: string): void {
  const preview = document.getElementById('channel-link-preview') as HTMLElement;
  if (!preview) return;
  
  const selectedValue = dropdown.value;
  const selectedText = dropdown.options[dropdown.selectedIndex]?.text || 'None';
  
  if (selectedValue === 'None') {
    preview.innerHTML = `
      <div class="alert alert-warning">
        <i class="bi bi-exclamation-triangle me-2"></i>
        <strong>No source channel:</strong> Enhanced video linking will not be available.
      </div>
    `;
  } else {
    const isCurrentlySelected = currentSourceName && selectedText.includes(currentSourceName);
    const alertClass = isCurrentlySelected ? 'alert-info' : 'alert-success';
    const statusText = isCurrentlySelected ? 'Current selection' : 'New selection';
    
    preview.innerHTML = `
      <div class="${alertClass}">
        <i class="bi bi-link-45deg me-2"></i>
        <strong>${statusText}:</strong> Videos will be matched from "${selectedText}".
      </div>
    `;
  }
}

async function handleChannelLinkSubmit(channelId: number, channelName: string): Promise<void> {
  const form = document.getElementById('channelLinkForm') as HTMLFormElement;
  const saveBtn = document.getElementById('saveChannelLinkBtn') as HTMLButtonElement;
  const modal = document.getElementById('channelLinkModal') as any;
  const dropdown = document.getElementById('modal_link_channel_id') as HTMLSelectElement;
  const originalText = saveBtn.innerHTML;
  
  if (!form || !saveBtn || !dropdown) return;
  
  const selectedValue = dropdown.value;
  const selectedText = dropdown.options[dropdown.selectedIndex]?.text || 'None';
  
  // Show loading state
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>Saving...';
  
  try {
    const formData = new FormData(form);
    addCsrfToken(formData);
    
    const response = await fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'fetch'
      },
      body: formData
    });
    
    if (response.ok) {
      // Close modal and reload page to show updated state
      const modalInstance = (window as any).bootstrap.Modal.getInstance(modal);
      modalInstance.hide();
      
      const message = selectedValue === 'None' 
        ? `${channelName} unlinked successfully` 
        : `${channelName} linked to "${selectedText}" successfully`;
      alert(message);
      window.location.reload();
    } else {
      const errorText = await response.text();
      alert(`Error updating channel link: ${errorText}`);
    }
    
  } catch (error) {
    console.error('Error updating channel link:', error);
    alert(`Network error: ${error}`);
  } finally {
    // Reset button state
    saveBtn.disabled = false;
    saveBtn.innerHTML = originalText;
  }
}

// Enhanced Video Linking Modal functionality
function showEnhancedLinkingModal(channelId: number, channelName: string, sourceChannelName: string): void {
  const modal = document.getElementById('enhancedLinkingModal') as any;
  const form = document.getElementById('enhancedLinkingForm') as HTMLFormElement;
  const runBtn = document.getElementById('runLinkingBtn') as HTMLButtonElement;
  const modalTitle = document.getElementById('enhancedLinkingModalLabel') as HTMLElement;
  
  if (!modal || !form || !runBtn) return;
  
  // Update modal title and form action
  modalTitle.textContent = `Enhanced Video Linking - ${channelName}`;
  form.action = `/channel/${channelId}/link_videos`;
  
  // Update description
  const modalContent = document.getElementById('linking-modal-content');
  if (modalContent) {
    const description = modalContent.querySelector('p');
    if (description) {
      description.textContent = `Link videos from "${sourceChannelName}" to "${channelName}" using duration matching and title date parsing.`;
    }
  }
  
  // Set up the run button click handler
  runBtn.onclick = () => handleModalLinkingSubmit(channelId, channelName);
  
  // Show the modal
  const modalInstance = new (window as any).bootstrap.Modal(modal);
  modalInstance.show();
}

async function handleModalLinkingSubmit(channelId: number, channelName: string): Promise<void> {
  const form = document.getElementById('enhancedLinkingForm') as HTMLFormElement;
  const runBtn = document.getElementById('runLinkingBtn') as HTMLButtonElement;
  const modal = document.getElementById('enhancedLinkingModal') as any;
  const originalText = runBtn.innerHTML;
  
  if (!form || !runBtn) return;
  
  // Confirm action
  if (!confirm(`Run enhanced video linking for "${channelName}"?\n\nThis will analyze all videos and create links where matches are found.`)) {
    return;
  }
  
  // Show loading state
  runBtn.disabled = true;
  runBtn.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>Running...';
  
  try {
    const formData = new FormData(form);
    addCsrfToken(formData);
    
    const response = await fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'fetch'
      },
      body: formData
    });
    
    if (response.ok) {
      // Close modal and show success
      const modalInstance = (window as any).bootstrap.Modal.getInstance(modal);
      modalInstance.hide();
      
      alert(`Video linking completed for ${channelName}. Check the logs for details.`);
    } else {
      const errorText = await response.text();
      alert(`Error running video linking: ${errorText}`);
    }
    
  } catch (error) {
    console.error('Error running video linking:', error);
    alert(`Network error: ${error}`);
  } finally {
    // Reset button state
    runBtn.disabled = false;
    runBtn.innerHTML = originalText;
  }
}

// Make functions globally available for onclick handlers
(window as any).toggleTwitchLookup = toggleTwitchLookup;
(window as any).lookupTwitchId = lookupTwitchId;
(window as any).showChannelLinkModal = showChannelLinkModal;
(window as any).showEnhancedLinkingModal = showEnhancedLinkingModal;

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
      addCsrfToken(formData);

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

// Enhanced Video Linking functionality
function initializeVideoLinking(): void {
  // Find all enhanced video linking forms
  const linkingForms = document.querySelectorAll('form[action*="/link_videos"]') as NodeListOf<HTMLFormElement>;
  
  linkingForms.forEach(form => {
    form.addEventListener('submit', handleVideoLinkingSubmit);
  });
}

// Channel-to-Channel Linking functionality
function initializeChannelLinking(): void {
  const channelLinkForms = document.querySelectorAll('form[action*="/channel/"][action$="/link"]:not([action*="/link_videos"])') as NodeListOf<HTMLFormElement>;
  
  channelLinkForms.forEach(form => {
    form.addEventListener('submit', handleChannelLinkingSubmit);
  });
}

async function handleChannelLinkingSubmit(event: Event): Promise<void> {
  event.preventDefault();
  
  const form = event.target as HTMLFormElement;
  const submitButton = form.querySelector('button[type="submit"]') as HTMLButtonElement;
  const originalText = submitButton.innerHTML;
  
  // Show loading state
  submitButton.disabled = true;
  submitButton.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>Updating...';
  
  try {
    const formData = new FormData(form);
    addCsrfToken(formData);
    
    const response = await fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'fetch'
      },
      body: formData
    });
    
    if (response.ok) {
      // Show success and reload page to reflect changes
      alert('Channel link updated successfully');
      window.location.reload();
    } else {
      const errorText = await response.text();
      alert(`Error updating channel link: ${errorText}`);
    }
    
  } catch (error) {
    console.error('Error updating channel link:', error);
    alert(`Network error: ${error}`);
  } finally {
    // Reset button state
    submitButton.disabled = false;
    submitButton.innerHTML = originalText;
  }
}

async function handleVideoLinkingSubmit(event: Event): Promise<void> {
  event.preventDefault();
  
  const form = event.target as HTMLFormElement;
  const submitButton = form.querySelector('button[type="submit"]') as HTMLButtonElement;
  const originalText = submitButton.innerHTML;
  
  // Get channel name from form context
  const channelCard = form.closest('.card');
  const channelName = channelCard?.querySelector('.card-title')?.textContent || 'this channel';
  
  // Show loading state
  submitButton.disabled = true;
  submitButton.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status"></div>Running...';
  
  try {
    const formData = new FormData(form);
    const response = await fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'fetch'
      },
      body: formData
    });
    
    if (response.ok) {
      // Show success message
      showLinkingFeedback('success', `Video linking completed for ${channelName}. Check the logs for details.`);
    } else {
      // Show error message
      const errorText = await response.text();
      showLinkingFeedback('danger', `Error running video linking: ${errorText}`);
    }
    
  } catch (error) {
    console.error('Error running video linking:', error);
    showLinkingFeedback('danger', `Network error running video linking: ${error}`);
  } finally {
    // Reset button state
    submitButton.disabled = false;
    submitButton.innerHTML = originalText;
  }
}

function showLinkingFeedback(type: 'success' | 'danger', message: string): void {
  // Find or create feedback container
  let feedbackContainer = document.getElementById('linking-feedback');
  if (!feedbackContainer) {
    feedbackContainer = document.createElement('div');
    feedbackContainer.id = 'linking-feedback';
    feedbackContainer.className = 'mt-3';
    
    // Insert after the first linking form we find
    const firstForm = document.querySelector('form[action*="/link_videos"]');
    if (firstForm && firstForm.parentNode) {
      firstForm.parentNode.insertBefore(feedbackContainer, firstForm.nextSibling);
    } else {
      // Fallback: add to settings feedback area
      const settingsFeedback = document.getElementById('settings-feedback');
      if (settingsFeedback) {
        settingsFeedback.appendChild(feedbackContainer);
      }
    }
  }
  
  // Create alert
  const alert = document.createElement('div');
  alert.className = `alert alert-${type} alert-dismissible fade show`;
  alert.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  `;
  
  // Clear previous alerts and add new one
  feedbackContainer.innerHTML = '';
  feedbackContainer.appendChild(alert);
  
  // Auto-dismiss after 5 seconds
  if (type === 'success') {
    setTimeout(() => {
      if (alert.parentNode) {
        alert.classList.remove('show');
        setTimeout(() => alert.remove(), 150);
      }
    }, 5000);
  }
}

// Advanced parameters toggle functionality
function initializeAdvancedParameters(): void {
  const toggleButtons = document.querySelectorAll('[data-bs-target="#linkingOptions"]');
  
  toggleButtons.forEach(button => {
    button.addEventListener('click', () => {
      const icon = button.querySelector('i');
      if (icon) {
        // Toggle between chevron-down and chevron-up
        setTimeout(() => {
          const isExpanded = button.getAttribute('aria-expanded') === 'true';
          icon.className = isExpanded ? 'bi bi-chevron-up me-2' : 'bi bi-chevron-down me-2';
        }, 100);
      }
    });
  });
}

// Parameter validation and hints
function initializeParameterValidation(): void {
  // Add real-time validation feedback
  const parameterInputs = document.querySelectorAll('input[name="margin_sec"], input[name="min_duration"], input[name="date_margin_hours"]');
  
  parameterInputs.forEach(input => {
    input.addEventListener('input', validateParameter);
    input.addEventListener('change', validateParameter);
  });
}

function validateParameter(event: Event): void {
  const input = event.target as HTMLInputElement;
  const value = parseInt(input.value);
  const name = input.name;
  
  // Remove existing validation classes
  input.classList.remove('is-invalid', 'is-valid');
  
  // Get or create feedback div
  let feedback = input.parentElement?.querySelector('.invalid-feedback') as HTMLElement;
  if (!feedback) {
    feedback = document.createElement('div');
    feedback.className = 'invalid-feedback';
    input.parentElement?.appendChild(feedback);
  }
  
  // Validate based on parameter type
  let isValid = true;
  let message = '';
  
  switch (name) {
    case 'margin_sec':
      if (value < 0 || value > 20) {
        isValid = false;
        message = 'Duration margin should be between 0-20 seconds';
      } else if (value > 5) {
        message = 'High values may create false matches';
        input.classList.add('is-warning');
      }
      break;
      
    case 'min_duration':
      if (value < 60) {
        isValid = false;
        message = 'Minimum duration should be at least 60 seconds';
      } else if (value < 300) {
        message = 'Low values may include short clips';
        input.classList.add('is-warning');
      }
      break;
      
    case 'date_margin_hours':
      if (value < 1 || value > 168) {
        isValid = false;
        message = 'Date margin should be between 1-168 hours (1 week)';
      } else if (value > 72) {
        message = 'Long time windows may create false matches';
        input.classList.add('is-warning');
      }
      break;
  }
  
  if (!isValid) {
    input.classList.add('is-invalid');
    feedback.textContent = message;
    feedback.style.display = 'block';
  } else {
    input.classList.add('is-valid');
    if (message) {
      feedback.textContent = message;
      feedback.className = 'form-text text-warning';
      feedback.style.display = 'block';
    } else {
      feedback.style.display = 'none';
    }
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  initializeBroadcasterEdit();
  setupHtmxEventListeners();
  initializeChatLogUpload();
  initializeChannelLinking();
  initializeVideoLinking();
  initializeAdvancedParameters();
  initializeParameterValidation();
  
  // Fix Bootstrap dropdown placement issues
  const dropdowns = document.querySelectorAll('[data-bs-toggle="dropdown"]');
  dropdowns.forEach(dropdown => {
    if (!dropdown.hasAttribute('data-bs-placement')) {
      dropdown.setAttribute('data-bs-placement', 'bottom');
    }
  });
});