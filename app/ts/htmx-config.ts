// HTMX configuration for CSRF token handling
import htmx from 'htmx.org/dist/htmx.esm';

declare global {
  interface Window {
    htmx: typeof htmx;
  }
}

document.addEventListener('DOMContentLoaded', function() {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
  
  if (csrfToken && window.htmx) {
    window.htmx.on('htmx:configRequest', function(evt: any) {
      if (evt.detail.headers === undefined) {
        evt.detail.headers = {};
      }
      evt.detail.headers['X-CSRFToken'] = csrfToken;
      // For POST/PUT/DELETE/PATCH requests, also add the token as a form parameter
      if (['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(evt.detail.verb.toUpperCase()) !== -1) {
        if (!evt.detail.parameters) {
          evt.detail.parameters = {};
        }
        evt.detail.parameters['csrf_token'] = csrfToken;
      }
    });
  }
});