
function initializeUtils(): void {
  // Handle file upload loading states
  document.body.addEventListener('htmx:beforeSend', (event: any) => {
    if (event.detail.elt.id === 'upload-form') {
      const loadingElement = document.getElementById('loading');
      if (loadingElement) {
        loadingElement.classList.remove('d-none');
      }
    }
  });

  document.body.addEventListener('htmx:afterOnLoad', (event: any) => {
    if (event.detail.elt.id === 'upload-form') {
      const loadingElement = document.getElementById('loading');
      if (loadingElement) {
        loadingElement.classList.add('d-none');
      }
      
      // Refresh transcription list after upload
      if (window.htmx) {
        window.htmx.trigger('#transcription-list', 'load');
      }
    }
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  initializeUtils();
});