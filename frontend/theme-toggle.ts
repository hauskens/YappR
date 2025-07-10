// Theme management system
declare global {
  interface Window {
    matchMedia: (query: string) => MediaQueryList;
  }
}

// Early theme setting to prevent flicker
function initializeTheme(): void {
  const theme = localStorage.getItem('theme') || 
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-bs-theme', theme);
}

// Theme toggle functionality
function initializeThemeToggle(): void {
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');
  
  if (!themeToggle) return;

  let currentTheme = localStorage.getItem('theme') || 'dark';
  
  // Apply initial theme
  document.documentElement.setAttribute('data-bs-theme', currentTheme);
  if (themeIcon) {
    themeIcon.className = currentTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
  }

  themeToggle.addEventListener('click', () => {
    currentTheme = (document.documentElement.getAttribute('data-bs-theme') === 'dark') ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', currentTheme);
    localStorage.setItem('theme', currentTheme);

    if (themeIcon) {
      themeIcon.className = currentTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
  });
}

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', () => {
  initializeThemeToggle();
});

// Initialize theme immediately to prevent flicker
initializeTheme();