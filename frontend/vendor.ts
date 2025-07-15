// Bundle all vendor dependencies
import htmx from 'htmx.org/dist/htmx.esm';
import 'socket.io-client';
import { render } from 'github-buttons';
import 'vanilla-cookieconsent';
import bootstrap from 'bootstrap/dist/js/bootstrap.bundle.min.js';
import { Chart, registerables } from 'chart.js';

// Register Chart.js components
Chart.register(...registerables);

// Make htmx available globally
(window as any).htmx = htmx;

// Make bootstrap available globally
(window as any).bootstrap = bootstrap;

// Make Chart.js available globally
(window as any).Chart = Chart;

// Initialize GitHub buttons when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  const buttons = document.querySelectorAll('.github-button');
  buttons.forEach(anchor => {
    render(anchor as HTMLAnchorElement, function (el) {
      anchor.parentNode?.replaceChild(el, anchor);
    });
  });
});

