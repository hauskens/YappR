// Bundle all vendor dependencies
import htmx from 'htmx.org/dist/htmx.esm';
import 'socket.io-client';
import 'chart.js';
import 'github-buttons';
import 'vanilla-cookieconsent';
import bootstrap from 'bootstrap/dist/js/bootstrap.bundle.min.js';

// Make htmx available globally
(window as any).htmx = htmx;

// Make bootstrap available globally
(window as any).bootstrap = bootstrap;
