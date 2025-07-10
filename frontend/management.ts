// Management page functionality
declare global {
  interface Window {
    htmx: any;
  }
}

function initializeManagement(): void {
  // Debug HTMX requests
  document.body.addEventListener('htmx:beforeRequest', (evt: any) => {
    console.log('htmx request starting:', evt.detail);
    console.log('Parameters being sent:', evt.detail.parameters);
  });

  document.body.addEventListener('htmx:afterRequest', (evt: any) => {
    console.log('htmx request complete:', evt.detail);
  });

  document.body.addEventListener('htmx:responseError', (evt: any) => {
    console.error('htmx response error:', evt.detail);
  });
  
  // Checkbox change logging
  document.querySelectorAll('input[type="checkbox"].filter-control').forEach(checkbox => {
    checkbox.addEventListener('change', function(this: HTMLInputElement) {
      console.log(`Checkbox ${this.name} changed to ${this.checked}`);
    });
  });
  
  // Pagination handling
  document.body.addEventListener('click', (e: Event) => {
    const target = e.target as HTMLElement;
    const pageLink = target.matches('[data-page]') ? target : target.closest('[data-page]') as HTMLElement;
    
    if (pageLink) {
      e.preventDefault();
      const page = pageLink.getAttribute('data-page');
      if (!page) return;
      
      // Update page input
      const pageInput = document.createElement('input');
      pageInput.type = 'hidden';
      pageInput.name = 'page';
      pageInput.value = page;
      pageInput.className = 'filter-control';
      
      // Remove existing page input
      const existingPageInput = document.querySelector('input[name="page"].filter-control');
      if (existingPageInput) {
        existingPageInput.remove();
      }
      
      document.body.appendChild(pageInput);
      
      console.log('Pagination clicked: Page ' + page);
      
      // Trigger HTMX request
      if (window.htmx) {
        window.htmx.trigger('#queue-items-container', 'queue_update');
      }
    }
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  initializeManagement();
});