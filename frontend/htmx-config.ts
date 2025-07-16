document.addEventListener('DOMContentLoaded', function() {
  if (window.csrfToken) {
    window.htmx.on('htmx:configRequest', function(evt: CustomEvent) {
      if (evt.detail.headers === undefined) {
        evt.detail.headers = {};
      }
      evt.detail.headers['X-CSRFToken'] = window.csrfToken;
      // For POST/PUT/DELETE/PATCH requests, also add the token as a form parameter
      if (['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(evt.detail.verb.toUpperCase()) !== -1) {
        if (!evt.detail.parameters) {
          evt.detail.parameters = {};
        }
        evt.detail.parameters['csrf_token'] = window.csrfToken;
     }
    });
  }
});