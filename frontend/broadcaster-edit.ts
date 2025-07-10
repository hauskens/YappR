// Broadcaster edit functionality
// declare global {
//   interface Window {
//     htmx: any;
//   }
// }

// let twitchPlatformId: string | null = null;

// // Find Twitch platform ID and setup
// function initializeBroadcasterEdit(): void {
//   const platformSelect = document.getElementById('platform_id') as HTMLSelectElement;
//   if (!platformSelect) return;
  
//   const options = platformSelect.options;
  
//   for (let i = 0; i < options.length; i++) {
//     if (options[i].text.toLowerCase() === 'twitch') {
//       twitchPlatformId = options[i].value;
//       break;
//     }
//   }
  
//   toggleTwitchLookup();
  
//   const lookupButton = document.getElementById('lookup-twitch-id');
//   if (lookupButton) {
//     lookupButton.addEventListener('click', lookupTwitchId);
//   }
  
//   // Add platform select change listener
//   platformSelect.addEventListener('change', toggleTwitchLookup);
  
//   // Auto-fade success messages
//   setTimeout(() => {
//     const alerts = document.querySelectorAll('#settings-feedback .alert-success');
//     alerts.forEach(alert => {
//       (alert as HTMLElement).style.opacity = '0';
//       setTimeout(() => alert.remove(), 300);
//     });
//   }, 3000);
// }

// // Toggle Twitch lookup visibility
// function toggleTwitchLookup(): void {
//   const platformSelect = document.getElementById('platform_id') as HTMLSelectElement;
//   const lookupContainer = document.getElementById('twitch-lookup-container') as HTMLElement;
  
//   if (platformSelect && lookupContainer) {
//     if (platformSelect.value === twitchPlatformId) {
//       lookupContainer.style.display = 'block';
//     } else {
//       lookupContainer.style.display = 'none';
//     }
//   }
// }

// // Lookup Twitch ID from username
// function lookupTwitchId(): void {
//   const usernameInput = document.getElementById('twitch_username') as HTMLInputElement;
//   const statusElement = document.getElementById('twitch-lookup-status') as HTMLElement;
//   const platformRefInput = document.getElementById('platform_ref') as HTMLInputElement;
//   const channelIdInput = document.getElementById('channel_id') as HTMLInputElement;
  
//   if (!usernameInput || !statusElement || !platformRefInput || !channelIdInput) return;
  
//   const username = usernameInput.value.trim();
  
//   if (!username) {
//     alert('Please enter a Twitch username');
//     return;
//   }
  
//   // Show loading indicator
//   statusElement.innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
//   statusElement.style.display = 'inline-block';
  
//   // Make API request
//   fetch(`/api/lookup_twitch_id?username=${encodeURIComponent(username)}`)
//     .then(response => response.json())
//     .then(data => {
//       if (data.success && data.user_id) {
//         statusElement.innerHTML = '<i class="bi bi-check-circle-fill text-success" style="font-size: 1.5rem;"></i>';
//         platformRefInput.value = data.user_id;
//         channelIdInput.value = data.user_id;
        
//         const nameInput = document.getElementById('name') as HTMLInputElement;
//         if (nameInput && nameInput.value.trim() === '' && data.display_name) {
//           nameInput.value = data.display_name;
//         }
//       } else {
//         statusElement.innerHTML = '<i class="bi bi-x-circle-fill text-danger" style="font-size: 1.5rem;"></i>';
//         if (data.error) {
//           console.error('Error looking up Twitch ID:', data.error);
//         }
//       }
//     })
//     .catch(error => {
//       statusElement.innerHTML = '<i class="bi bi-x-circle-fill text-danger" style="font-size: 1.5rem;"></i>';
//       console.error('Error looking up Twitch ID:', error);
//     });
// }

// // HTMX event listeners
// function setupHtmxEventListeners(): void {
//   document.body.addEventListener('htmx:beforeRequest', (evt) => {
//     const spinner = document.getElementById('settings-spinner') as HTMLElement;
//     if (spinner) {
//       spinner.style.display = 'block';
//     }
//   });

//   document.body.addEventListener('htmx:afterRequest', (evt) => {
//     const spinner = document.getElementById('settings-spinner') as HTMLElement;
//     if (spinner) {
//       spinner.style.display = 'none';
//     }
//   });
// }

// // Make functions globally available for onclick handlers
// (window as any).toggleTwitchLookup = toggleTwitchLookup;
// (window as any).lookupTwitchId = lookupTwitchId;

// // Initialize on page load
// document.addEventListener('DOMContentLoaded', () => {
//   initializeBroadcasterEdit();
//   setupHtmxEventListeners();
// });