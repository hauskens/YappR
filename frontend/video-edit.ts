
// // Debounce function for performance
// function debounce<T extends (...args: any[]) => any>(func: T, wait: number): T {
//   let timeout: NodeJS.Timeout;
//   return ((...args: Parameters<T>) => {
//     clearTimeout(timeout);
//     timeout = setTimeout(() => func(...args), wait);
//   }) as T;
// }

// // Text highlighting function
// function highlightText(text: string, searchTerm: string): string {
//   if (!searchTerm || !text) return text;
  
//   const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
//   return text.replace(regex, '<mark>$1</mark>');
// }

// // Type definitions for tag categories
// interface TagCategory {
//   id: string;
//   name: string;
//   color: string;
//   tags: string[];
// }

// // Global variables
// let timelineChart: any = null;
// let isClearing = false;
// let isSearching = false;
// let tagCategories: TagCategory[] = [];


// // Tag Category Management Functions
// function initializeTagCategories(): void {
//   loadTagCategories();
//   renderTagCategories();
//   setupTagCategoryEventListeners();
// }

// function loadTagCategories(): void {
//   const storedCategories = localStorage.getItem('tagCategories');
//   if (storedCategories) {
//     try {
//       tagCategories = JSON.parse(storedCategories);
//     } catch (e) {
//       console.error('Failed to parse tag categories from localStorage', e);
//       tagCategories = [];
//     }
//   }
// }

// function saveTagCategories(): void {
//   localStorage.setItem('tagCategories', JSON.stringify(tagCategories));
//   renderTagCategories();
// }

// // Export tag categories to a JSON file for sharing
// function exportTagCategories(): void {
//   if (tagCategories.length === 0) {
//     alert('No tag categories to export');
//     return;
//   }
  
//   // Create a JSON blob
//   const categoriesJson = JSON.stringify(tagCategories, null, 2);
//   const blob = new Blob([categoriesJson], { type: 'application/json' });
  
//   // Create download link
//   const downloadLink = document.createElement('a');
//   downloadLink.href = URL.createObjectURL(blob);
//   downloadLink.download = `vodmeta-tag-categories-${new Date().toISOString().split('T')[0]}.json`;
  
//   // Trigger download
//   document.body.appendChild(downloadLink);
//   downloadLink.click();
//   document.body.removeChild(downloadLink);
// }

// // Import tag categories from a JSON file
// async function importTagCategories(): Promise<void> {
//   return new Promise((resolve) => {
//     // Create file input
//     const fileInput = document.createElement('input');
//     fileInput.type = 'file';
//     fileInput.accept = 'application/json';
    
//     fileInput.onchange = (event) => {
//       const target = event.target as HTMLInputElement;
//       const file = target.files?.[0];
      
//       if (!file) {
//         resolve();
//         return;
//       }
      
//       const reader = new FileReader();
//       reader.onload = (e) => {
//         try {
//           const content = e.target?.result as string;
//           const imported = JSON.parse(content);
          
//           // Validate imported data
//           if (!Array.isArray(imported)) {
//             alert('Invalid format: Expected an array of categories');
//             resolve();
//             return;
//           }
          
//           const isValid = imported.every(item => 
//             typeof item === 'object' && 
//             item !== null &&
//             typeof item.id === 'string' && 
//             typeof item.name === 'string' && 
//             typeof item.color === 'string' && 
//             Array.isArray(item.tags)
//           );
          
//           if (!isValid) {
//             alert('Invalid format: Some categories are missing required fields');
//             resolve();
//             return;
//           }
          
//           // Confirm import
//           if (tagCategories.length > 0 && !confirm(`This will replace your ${tagCategories.length} existing categories. Continue?`)) {
//             resolve();
//             return;
//           }
          
//           // Import the categories
//           tagCategories = imported;
//           saveTagCategories();
//           updateCategoryChart();
//           alert(`Successfully imported ${tagCategories.length} tag categories`);
//           resolve();
//         } catch (error) {
//           alert(`Error importing categories: ${error}`);
//           resolve();
//         }
//       };
      
//       reader.readAsText(file);
//     };
    
//     // Trigger file selection
//     fileInput.click();
//   });
// }

// function renderTagCategories(): void {
//   const container = document.getElementById('tagCategoriesContainer');
//   const noTagsMsg = document.getElementById('noCategoriesMsg');
  
//   if (!container) return;
  
//   // Clear current categories (except for the noTagsMsg)
//   Array.from(container.children).forEach(child => {
//     if (child.id !== 'noCategoriesMsg') {
//       container.removeChild(child);
//     }
//   });
  
//   if (tagCategories.length === 0) {
//     if (noTagsMsg) noTagsMsg.style.display = 'block';
//     return;
//   }
  
//   if (noTagsMsg) noTagsMsg.style.display = 'none';
  
//   // Create badge for each category
//   tagCategories.forEach(category => {
//     const badge = document.createElement('div');
//     badge.className = 'badge rounded-pill d-inline-flex align-items-center me-2 mb-2';
//     badge.style.backgroundColor = category.color;
//     badge.style.color = getContrastYIQ(category.color);
//     badge.style.fontSize = '0.9rem';
//     badge.style.padding = '0.5em 0.8em';
    
//     const nameSpan = document.createElement('span');
//     nameSpan.textContent = category.name;
//     nameSpan.style.marginRight = '5px';
//     badge.appendChild(nameSpan);
    
//     const tagsCount = document.createElement('span');
//     tagsCount.textContent = `(${category.tags.length} tags)`;
//     tagsCount.className = 'small opacity-75';
//     badge.appendChild(tagsCount);
    
//     // Edit button
//     const editBtn = document.createElement('button');
//     editBtn.className = 'btn btn-sm ms-2 p-0';
//     editBtn.style.lineHeight = '1';
//     editBtn.innerHTML = '<i class="bi bi-pencil-fill" style="font-size: 0.8rem;"></i>';
//     editBtn.style.color = getContrastYIQ(category.color);
//     editBtn.setAttribute('data-id', category.id);
//     editBtn.addEventListener('click', (e) => {
//       e.stopPropagation();
//       editCategory(category.id);
//     });
//     badge.appendChild(editBtn);
    
//     // Delete button
//     const deleteBtn = document.createElement('button');
//     deleteBtn.className = 'btn btn-sm ms-1 p-0';
//     deleteBtn.style.lineHeight = '1';
//     deleteBtn.innerHTML = '<i class="bi bi-x-lg" style="font-size: 0.8rem;"></i>';
//     deleteBtn.style.color = getContrastYIQ(category.color);
//     deleteBtn.setAttribute('data-id', category.id);
//     deleteBtn.addEventListener('click', (e) => {
//       e.stopPropagation();
//       deleteCategory(category.id);
//     });
//     badge.appendChild(deleteBtn);
    
//     container.appendChild(badge);
//   });
// }

// function setupTagCategoryEventListeners(): void {
//   const addBtn = document.getElementById('addCategoryBtn');
//   const saveBtn = document.getElementById('saveCategoryBtn');
//   const exportBtn = document.getElementById('exportCategoriesBtn');
//   const importBtn = document.getElementById('importCategoriesBtn');
  
//   if (addBtn) {
//     addBtn.addEventListener('click', () => {
//       // Reset form
//       const nameInput = document.getElementById('categoryName') as HTMLInputElement;
//       const colorInput = document.getElementById('categoryColor') as HTMLInputElement;
//       const tagsInput = document.getElementById('categoryTags') as HTMLTextAreaElement;
//       const idInput = document.getElementById('editCategoryId') as HTMLInputElement;
      
//       if (nameInput) nameInput.value = '';
//       if (colorInput) colorInput.value = '#007bff';
//       if (tagsInput) tagsInput.value = '';
//       if (idInput) idInput.value = '';
      
//       // Show modal
//       const modal = new (window as any).bootstrap.Modal(document.getElementById('tagCategoryModal'));
//       modal.show();
//     });
//   }
  
//   if (exportBtn) {
//     exportBtn.addEventListener('click', () => {
//       exportTagCategories();
//     });
//   }
  
//   if (importBtn) {
//     importBtn.addEventListener('click', async () => {
//       await importTagCategories();
//     });
//   }
  
//   if (saveBtn) {
//     saveBtn.addEventListener('click', () => {
//       const nameInput = document.getElementById('categoryName') as HTMLInputElement;
//       const colorInput = document.getElementById('categoryColor') as HTMLInputElement;
//       const tagsInput = document.getElementById('categoryTags') as HTMLTextAreaElement;
//       const idInput = document.getElementById('editCategoryId') as HTMLInputElement;
      
//       const name = nameInput.value.trim();
//       const color = colorInput.value;
//       const tagsText = tagsInput.value;
//       const id = idInput.value;
      
//       if (!name) {
//         alert('Please enter a category name');
//         return;
//       }
      
//       // Keep case but remove all spaces when storing tags
//       const tags = tagsText.split(',').map(tag => tag.trim().replace(/\s+/g, '')).filter(tag => tag);
      
//       if (tags.length === 0) {
//         alert('Please enter at least one tag');
//         return;
//       }
      
//       if (id) {
//         // Edit existing
//         const categoryIndex = tagCategories.findIndex(c => c.id === id);
//         if (categoryIndex >= 0) {
//           tagCategories[categoryIndex] = { id, name, color, tags };
//         }
//       } else {
//         // Add new
//         const newId = Date.now().toString();
//         tagCategories.push({ id: newId, name, color, tags });
//       }
      
//       saveTagCategories();
//       updateCategoryChart();
      
//       // Hide modal
//       const modal = (window as any).bootstrap.Modal.getInstance(document.getElementById('tagCategoryModal'));
//       if (modal) modal.hide();
//     });
//   }
// }

// function editCategory(categoryId: string): void {
//   const category = tagCategories.find(c => c.id === categoryId);
//   if (!category) return;
  
//   const nameInput = document.getElementById('categoryName') as HTMLInputElement;
//   const colorInput = document.getElementById('categoryColor') as HTMLInputElement;
//   const tagsInput = document.getElementById('categoryTags') as HTMLTextAreaElement;
//   const idInput = document.getElementById('editCategoryId') as HTMLInputElement;
//   const modalTitle = document.getElementById('tagCategoryModalLabel');
  
//   if (nameInput) nameInput.value = category.name;
//   if (colorInput) colorInput.value = category.color;
//   if (tagsInput) tagsInput.value = category.tags.join(', ');
//   if (idInput) idInput.value = category.id;
//   if (modalTitle) modalTitle.textContent = 'Edit Tag Category';
  
//   const modal = new (window as any).bootstrap.Modal(document.getElementById('tagCategoryModal'));
//   modal.show();
// }

// function deleteCategory(categoryId: string): void {
//   if (confirm('Are you sure you want to delete this category?')) {
//     tagCategories = tagCategories.filter(c => c.id !== categoryId);
//     saveTagCategories();
//     updateCategoryChart();
//   }
// }

// // Helper function to determine if text should be white or black based on background color
// function getContrastYIQ(hexcolor: string): string {
//   // If color doesn't have a # prefix, add it
//   if (!hexcolor.startsWith('#')) {
//     hexcolor = '#' + hexcolor;
//   }
  
//   // Convert hex to RGB
//   const r = parseInt(hexcolor.substr(1, 2), 16);
//   const g = parseInt(hexcolor.substr(3, 2), 16);
//   const b = parseInt(hexcolor.substr(5, 2), 16);
  
//   // Calculate brightness using YIQ formula
//   const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
  
//   // Return black or white depending on brightness
//   return (yiq >= 128) ? '#000000' : '#ffffff';
// }

// // Function to update chart with category data
// async function updateCategoryChart(): Promise<void> {
//   if (tagCategories.length === 0) {
//     // Fall back to standard chart if no categories defined
//     initializeChatTimeline();
//     return;
//   }
  
//   const chatTimelineCanvas = document.getElementById('chatTimelineChart') as HTMLCanvasElement;
//   const intervalSelect = document.getElementById('timelineInterval') as HTMLSelectElement;
//   if (!chatTimelineCanvas) return;
  
//   const videoId = getVideoIdFromUrl();
//   if (!videoId) {
//     console.error('Could not determine video ID from URL');
//     return;
//   }
  
//   const selectedInterval = parseInt(intervalSelect ? intervalSelect.value : '30');
  
//   try {
//     // Show loading state
//     chatTimelineCanvas.style.opacity = '0.5';
    
//     // Fetch category data from backend
//     const response = await fetch(`/video/${videoId}/category_chatlogs`, {
//       method: 'POST',
//       headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken },
//       body: JSON.stringify({
//         categories: tagCategories,
//         intervalMinutes: selectedInterval
//       })
//     });
    
//     if (!response.ok) {
//       throw new Error(`Failed to fetch category data: ${response.status}`);
//     }
    
//     const data = await response.json();
    
//     // Reset loading state
//     chatTimelineCanvas.style.opacity = '1';
    
//     // Create chart datasets
//     const datasets = [];
    
//     // Add dataset for each category
//     for (const categoryId in data.categoryData) {
//       const categoryInfo = data.categoryData[categoryId];
//       datasets.push({
//         label: categoryInfo.name,
//         data: categoryInfo.counts,
//         backgroundColor: categoryInfo.color,
//         borderColor: categoryInfo.color,
//         // No border for stacked bar chart
//         borderWidth: 0
//       });
//     }
    
//     const ctx = chatTimelineCanvas.getContext('2d');
//     if (!ctx) return;
    
//     // Destroy existing chart if it exists
//     if (timelineChart) {
//       timelineChart.destroy();
//     }
    
//     // Create stacked bar chart
//     timelineChart = new (window as any).Chart(ctx, {
//       type: 'bar',
//       data: {
//         labels: data.intervals,
//         datasets: datasets
//       },
//       options: {
//         responsive: true,
//         maintainAspectRatio: false,
//         scales: {
//           x: {
//             stacked: true,
//             title: {
//               display: true,
//               text: 'Time'
//             }
//           },
//           y: {
//             stacked: true,
//             title: {
//               display: true,
//               text: 'Message Count'
//             },
//             beginAtZero: true
//           }
//         },
//         plugins: {
//           legend: {
//             display: true,
//             position: 'top'
//           },
//           tooltip: {
//             mode: 'index',
//             intersect: false
//           }
//         }
//       }
//     });
//   } catch (error) {
//     console.error('Error updating category chart:', error);
//     chatTimelineCanvas.style.opacity = '1';
//   }
// }

// // Helper function to extract video ID from URL
// function getVideoIdFromUrl(): string | null {
//   const pathMatch = window.location.pathname.match(/\/video\/([0-9]+)/);
//   if (pathMatch && pathMatch[1]) {
//     return pathMatch[1];
//   }
//   return null;
// }

// // Timeline chart for chat messages
// function initializeChatTimeline(): void {
//   const chatTimelineCanvas = document.getElementById('chatTimelineChart') as HTMLCanvasElement;
//   const intervalSelect = document.getElementById('timelineInterval') as HTMLSelectElement;
//   if (!chatTimelineCanvas) return;

//   // Function to create/update the chart
//   const updateChart = () => {
//     if (isClearing || isSearching) return; // Skip chart update during clear/search operations
    
//     // If tag categories are defined, use category chart instead
//     if (tagCategories.length > 0) {
//       updateCategoryChart();
//       return;
//     }
    
//     const chatMessages = document.querySelectorAll('.chat-message');
//     if (chatMessages.length === 0) return;

//     const selectedInterval = parseInt(intervalSelect?.value || '5');
//     const timelineData = processTimelineData(chatMessages, selectedInterval);
    
//     const ctx = chatTimelineCanvas.getContext('2d');
//     if (!ctx) return;

//     // Destroy existing chart if it exists
//     if (timelineChart) {
//       timelineChart.destroy();
//     }

//     timelineChart = new (window as any).Chart(ctx, {
//     type: 'line',
//     data: {
//       labels: timelineData.labels,
//       datasets: [{
//         label: 'Messages per interval',
//         data: timelineData.data,
//         borderColor: '#007bff',
//         backgroundColor: 'rgba(0, 123, 255, 0.1)',
//         fill: true,
//         tension: 0.4
//       }]
//     },
//     options: {
//       responsive: true,
//       maintainAspectRatio: false,
//       scales: {
//         x: {
//           title: {
//             display: true,
//             text: 'Time'
//           }
//         },
//         y: {
//           title: {
//             display: true,
//             text: 'Message Count'
//           },
//           beginAtZero: true
//         }
//       },
//       plugins: {
//         legend: {
//           display: false
//         },
//         tooltip: {
//           mode: 'index',
//           intersect: false
//         }
//       },
//       onClick: (event: any, elements: any) => {
//         if (elements.length > 0) {
//           const elementIndex = elements[0].index;
//           const timestampUrl = timelineData.messageUrls[elementIndex];
//           if (timestampUrl) {
//             window.open(timestampUrl, '_blank');
//           }
//         }
//       }
//     }
//     });
//   };

//   // Initial chart creation
//   updateChart();

//   // Add event listener for interval changes
//   if (intervalSelect) {
//     intervalSelect.addEventListener('change', () => {
//       if (tagCategories.length > 0) {
//         updateCategoryChart();
//       } else {
//         updateChart();
//       }
//     });
//   }
// }

// // Process chat messages to create timeline data
// function processTimelineData(chatMessages: NodeListOf<Element>, intervalMinutes: number = 5): { labels: string[], data: number[], messageUrls: (string | null)[] } {
//   const messageData: { time: Date, element: Element }[] = [];
  
//   // Extract timestamps and elements from messages
//   chatMessages.forEach(message => {
//     const timestampElement = message.querySelector('.chat-timestamp[data-utc]');
//     if (timestampElement) {
//       const utcTime = timestampElement.getAttribute('data-utc');
//       if (utcTime) {
//         messageData.push({ time: new Date(utcTime), element: message });
//       }
//     }
//   });

//   if (messageData.length === 0) return { labels: [], data: [], messageUrls: [] };

//   // Sort by time
//   messageData.sort((a, b) => a.time.getTime() - b.time.getTime());

//   // Create time buckets with first message in each bucket
//   const buckets = new Map<string, { count: number, firstMessage: Element }>();

//   messageData.forEach(({ time, element }) => {
//     const bucketTime = new Date(time);
//     bucketTime.setMinutes(Math.floor(bucketTime.getMinutes() / intervalMinutes) * intervalMinutes, 0, 0);
//     const bucketKey = bucketTime.toISOString();
    
//     const existing = buckets.get(bucketKey);
//     if (existing !== undefined) {
//       existing.count++;
//     } else {
//       buckets.set(bucketKey, { count: 1, firstMessage: element });
//     }
//   });

//   // Convert to arrays for Chart.js
//   const labels: string[] = [];
//   const data: number[] = [];
//   const messageUrls: (string | null)[] = [];
  
//   for (const [bucketKey, bucket] of Array.from(buckets.entries()).sort()) {
//     const date = new Date(bucketKey);
//     labels.push(date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
//     data.push(bucket.count);
    
//     // Get URL from first message in this bucket
//     const timestampLink = bucket.firstMessage.querySelector('a[href*="t="]') as HTMLAnchorElement;
//     messageUrls.push(timestampLink ? timestampLink.href : null);
//   }

//   return { labels, data, messageUrls };
// }


// // Chat search functionality
// function initializeChatSearch(): void {
//   const chatSearchInput = document.getElementById('chatSearchInput') as HTMLInputElement;
//   const usernameFilter = document.getElementById('userFilter') as HTMLSelectElement;
//   const clearSearchBtn = document.getElementById('clearSearchBtn') as HTMLButtonElement;
  
//   if (!chatSearchInput) {
//     console.warn('Chat search input not found');
//     return;
//   }
  
//   const performChatSearch = debounce((searchTerm: string, selectedUsername: string) => {
//     const normalizedSearch = searchTerm.toLowerCase();
//     const chatMessages = document.querySelectorAll('.chat-message');
//       chatMessages.forEach(message => {
//         const messageElement = message as HTMLElement;
//         const messageTextElement = messageElement.querySelector('.chat-text');
//         const messageText = messageTextElement?.textContent?.toLowerCase() || '';
//         const username = messageElement.dataset.username || '';
        
//       // Check if message matches search term and username filter
//         const matchesSearch = !searchTerm || messageText.includes(normalizedSearch);
//         const matchesUser = !selectedUsername || username === selectedUsername;
        
//         if (matchesSearch && matchesUser) {
//         messageElement.style.display = '';
        
//         // Highlight search term in message text only
//         if (searchTerm && messageTextElement) {
//           const originalText = messageTextElement.getAttribute('data-original-text') || messageTextElement.innerHTML;
//           messageTextElement.setAttribute('data-original-text', originalText);
//           messageTextElement.innerHTML = highlightText(originalText, searchTerm);
//         } else if (messageTextElement) {
//           // Restore original text
//           const originalText = messageTextElement.getAttribute('data-original-text');
//           if (originalText) {
//             messageTextElement.innerHTML = originalText;
//         }
//         }
//     } else {
//         messageElement.style.display = 'none';
//       }
//     });
//   }, 300);
  
//   // Add event listeners
//   // chatSearchInput.addEventListener('input', (e) => {
//   //   const searchTerm = (e.target as HTMLInputElement).value;
//   //   const selectedUsername = usernameFilter ? usernameFilter.value : '';
//   //   performChatSearch(searchTerm, selectedUsername);
//   // });
  
//   // if (usernameFilter) {
//   //   usernameFilter.addEventListener('change', (e) => {
//   //     const selectedUsername = (e.target as HTMLSelectElement).value;
//   //     const searchTerm = chatSearchInput.value;
//   //     performChatSearch(searchTerm, selectedUsername);
//   //   });
//   // }
  
//   if (clearSearchBtn) {
//     clearSearchBtn.addEventListener('click', () => {
//       chatSearchInput.value = '';
//       window.htmx.trigger('body', 'search-cleared');
//       if (usernameFilter) usernameFilter.value = '';
//       performChatSearch('', '');
//     });
//   }
// }

// // Transcription search functionality
// function initializeTranscriptionSearch(): void {
//   const transcriptionSearchInput = document.getElementById('transcriptSearchInput') as HTMLInputElement;
//   const clearTranscriptSearchBtn = document.getElementById('clearTranscriptSearchBtn') as HTMLButtonElement;
  
//   if (!transcriptionSearchInput) {
//     console.warn('Transcription search input not found');
//     return;
//   }
  
//   const performTranscriptionSearch = debounce((searchTerm: string) => {
//     const normalizedSearch = searchTerm.toLowerCase();
//     const transcriptionSegments = document.querySelectorAll('.transcript-row');
//     console.log('Performing transcription search, found segments:', transcriptionSegments.length);
    
//     transcriptionSegments.forEach(segment => {
//       const segmentElement = segment as HTMLElement;
//       const segmentText = segmentElement.textContent?.toLowerCase() || '';
      
//       if (!searchTerm || segmentText.includes(normalizedSearch)) {
//         segmentElement.style.display = '';
        
//         // Highlight search term
//         if (searchTerm) {
//           const originalText = segmentElement.getAttribute('data-original-text') || segmentElement.innerHTML;
//           segmentElement.setAttribute('data-original-text', originalText);
//           segmentElement.innerHTML = highlightText(originalText, searchTerm);
//         } else {
//           // Restore original text
//           const originalText = segmentElement.getAttribute('data-original-text');
//           if (originalText) {
//             segmentElement.innerHTML = originalText;
//           }
//         }
//       } else {
//         segmentElement.style.display = 'none';
//       }
//     });
//   }, 300);
  
//   // Add event listener
//   transcriptionSearchInput.addEventListener('input', (e) => {
//     const searchTerm = (e.target as HTMLInputElement).value;
//     performTranscriptionSearch(searchTerm);
//   });
  
//   if (clearTranscriptSearchBtn) {
//     clearTranscriptSearchBtn.addEventListener('click', () => {
//       transcriptionSearchInput.value = '';
//       performTranscriptionSearch('');
//     });
//   }
// }

// // Local timestamp conversion for chat messages
// function convertTimestamps(): void {
//   const timestampElements = document.querySelectorAll('.chat-timestamp[data-utc]');
  
//   timestampElements.forEach(element => {
//     const utcTime = element.getAttribute('data-utc');
//     if (utcTime) {
//       const localTime = new Date(utcTime).toLocaleString();
//       element.textContent = localTime;
//     }
//   });
// }

// Initialize HTMX integration
// function initializeHtmxIntegration(): void {
//   // Handle dynamic content loading
//   document.body.addEventListener('htmx:afterSwap', (event: any) => {
//     if (event.detail.target.id === 'chat-messages-container') {
//       console.log('Chat messages loaded, reinitializing chat search');
//       setTimeout(() => initializeChatSearch(), 100);
//       convertTimestamps();
//       initializeChatTimeline();
//     }
    
//     if (event.detail.target.classList.contains('transcription-container')) {
//       initializeTranscriptionSearch();
//     }
//   });
// }

// // Initialize everything on page load
// document.addEventListener('DOMContentLoaded', () => {
//   initializeTagCategories();
//   initializeChatSearch();
//   initializeTranscriptionSearch();
//   convertTimestamps();
//   initializeHtmxIntegration();
  
//   // Initialize chat timeline chart
//   initializeChatTimeline();
// });