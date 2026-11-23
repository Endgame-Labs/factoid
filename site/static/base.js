(function () {
  'use strict';

  // Theme Management
  var STORAGE_KEY = 'factoid-theme';
  var root = document.documentElement;
  var themeToggleBtn = document.getElementById('theme-toggle');
  var themeStatusText = document.getElementById('theme-status-text');

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    root.style.colorScheme = theme;
    if (themeToggleBtn) {
      var nextTheme = theme === 'light' ? 'dark' : 'light';
      themeToggleBtn.setAttribute('aria-label', 'Switch to ' + nextTheme + ' theme');
      themeToggleBtn.setAttribute('title', 'Switch to ' + nextTheme + ' theme');
      if (themeStatusText) {
        themeStatusText.textContent = theme === 'light' ? 'Theme' : 'Dark';
      }
    }
  }

  var initialTheme = root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  applyTheme(initialTheme);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      var activeTheme = root.getAttribute('data-theme') || 'dark';
      var newTheme = activeTheme === 'light' ? 'dark' : 'light';
      applyTheme(newTheme);
      try {
        localStorage.setItem(STORAGE_KEY, newTheme);
      } catch (err) {
        // Local storage unavailable or disabled
      }
    });
  }

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      try {
        if (!localStorage.getItem(STORAGE_KEY)) {
          applyTheme(e.matches ? 'dark' : 'light');
        }
      } catch (err) {
        // Local storage unavailable
      }
    });
  }

  // Mobile navigation
  var menuBtn = document.getElementById('mobile-menu-btn');
  var mobileNav = document.getElementById('mobile-nav');
  if (menuBtn && mobileNav) {
    menuBtn.addEventListener('click', function () {
      var open = mobileNav.classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', String(open));
    });
    mobileNav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobileNav.classList.remove('open');
        menuBtn.setAttribute('aria-expanded', 'false');
      });
    });
  }
})();

// Show the latest release from PyPI; the version in the page is the fallback.
fetch("https://pypi.org/pypi/factoid/json")
  .then(function (r) { return r.ok ? r.json() : null; })
  .then(function (d) {
    var v = d && d.info && d.info.version;
    if (v) document.querySelectorAll("[data-version]").forEach(function (el) { el.textContent = v; });
  })
  .catch(function () {});
