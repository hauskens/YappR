// Broadcaster add functionality

// Update broadcaster name from channel selection
function updateBroadcasterName(): void {
  const channelSelect = document.getElementById('twitch_channel') as HTMLSelectElement;
  const nameInput = document.getElementById('name') as HTMLInputElement;
  const channelIdInput = document.getElementById('channel_id') as HTMLInputElement;
  const channelNameInput = document.getElementById('channel_name') as HTMLInputElement;
  
  if (!channelSelect || !nameInput || !channelIdInput || !channelNameInput) return;
  
  if (channelSelect.value) {
    const [channelId, channelName] = (channelSelect.value as string).split('|');
    nameInput.value = channelName;
    channelIdInput.value = channelId;
    channelNameInput.value = channelName;
  }
  
  checkFormValidity();
}

// Check form validity
function checkFormValidity(): void {
  const saveButton = document.getElementById('saveButton') as HTMLButtonElement;
  const willbehaveCheckbox = document.getElementById('willbehave') as HTMLInputElement;
  const channelSelect = document.getElementById('twitch_channel') as HTMLSelectElement;
  
  if (!saveButton || !willbehaveCheckbox || !channelSelect) return;
  
  const selectedOption = channelSelect.options[channelSelect.selectedIndex];
  
  // Check if valid option is selected
  const hasValidChannel = channelSelect.selectedIndex > 0 && !selectedOption.disabled;
  
  // Enable save button only if willbehave is checked and valid channel selected
  saveButton.disabled = !(willbehaveCheckbox.checked && hasValidChannel);
}

// Make functions globally available for onclick handlers
(window as any).updateBroadcasterName = updateBroadcasterName;
(window as any).checkFormValidity = checkFormValidity;

// Initialize form validation
document.addEventListener('DOMContentLoaded', () => {
  checkFormValidity();
  
  // Add event listeners
  const channelSelect = document.getElementById('twitch_channel');
  const willbehaveCheckbox = document.getElementById('willbehave');
  
  if (channelSelect) {
    channelSelect.addEventListener('change', updateBroadcasterName);
  }
  
  if (willbehaveCheckbox) {
    willbehaveCheckbox.addEventListener('change', checkFormValidity);
  }
});