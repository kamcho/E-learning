/**
 * Soma Smart theme switcher — light / dark
 * Persists preference in localStorage and syncs all toggle buttons.
 */
(function () {
  var STORAGE_KEY = 'soma-smart-theme';

  function getPreferred() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'light' || stored === 'dark') return stored;
      var legacy = localStorage.getItem('somakenya-theme');
      if (legacy === 'light' || legacy === 'dark') {
        localStorage.setItem(STORAGE_KEY, legacy);
        return legacy;
      }
    } catch (e) { /* ignore */ }
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  function applyTheme(theme) {
    var next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) { /* ignore */ }
    syncButtons(next);
  }

  function syncButtons(theme) {
    var isDark = theme === 'dark';
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      btn.setAttribute(
        'aria-label',
        isDark ? 'Switch to light theme' : 'Switch to dark theme'
      );
      btn.title = isDark ? 'Switch to light theme' : 'Switch to dark theme';
    });
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || getPreferred();
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Apply immediately (also called from inline head script before paint)
  applyTheme(getPreferred());

  document.addEventListener('DOMContentLoaded', function () {
    syncButtons(document.documentElement.getAttribute('data-theme') || 'light');
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        toggleTheme();
      });
    });
  });

  // Cross-tab sync
  window.addEventListener('storage', function (e) {
    if (e.key === STORAGE_KEY && (e.newValue === 'light' || e.newValue === 'dark')) {
      applyTheme(e.newValue);
    }
  });

  window.SomaSmartTheme = { apply: applyTheme, toggle: toggleTheme, get: getPreferred };
})();
