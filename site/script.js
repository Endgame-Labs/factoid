/**
 * Factoid Landing Page JavaScript
 * Handles theme toggling, persistence, and clipboard copying.
 */

(function () {
  'use strict';

  // Theme Management
  var STORAGE_KEY = 'factoid-theme';
  var root = document.documentElement;
  var themeToggleBtn = document.getElementById('theme-toggle');
  var themeStatusText = document.getElementById('theme-status-text');

  function getPreferredTheme() {
    var storedTheme = localStorage.getItem(STORAGE_KEY);
    if (storedTheme === 'light' || storedTheme === 'dark') {
      return storedTheme;
    }
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    if (themeToggleBtn) {
      var nextTheme = theme === 'light' ? 'dark' : 'light';
      themeToggleBtn.setAttribute('aria-label', 'Switch to ' + nextTheme + ' theme');
      themeToggleBtn.setAttribute('title', 'Switch to ' + nextTheme + ' theme');
      if (themeStatusText) {
        themeStatusText.textContent = theme === 'light' ? 'Theme' : 'Dark';
      }
    }
  }

  // Initialize theme immediately
  var currentTheme = getPreferredTheme();
  applyTheme(currentTheme);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      var activeTheme = root.getAttribute('data-theme') || 'light';
      var newTheme = activeTheme === 'light' ? 'dark' : 'light';
      applyTheme(newTheme);
      try {
        localStorage.setItem(STORAGE_KEY, newTheme);
      } catch (err) {
        // Local storage unavailable or disabled
      }
    });
  }

  // Listen for system changes if user hasn't overridden
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!localStorage.getItem(STORAGE_KEY)) {
        applyTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  // Copy-to-clipboard functionality
  var copyBtn = document.getElementById('copy-install-btn');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      var targetId = copyBtn.getAttribute('data-copy-target');
      var targetElement = targetId ? document.getElementById(targetId) : null;
      var textToCopy = targetElement ? targetElement.innerText.trim() : 'uv tool install factoid';

      function markCopied() {
        copyBtn.classList.add('copied');
        var textNode = copyBtn.querySelector('.copy-text');
        if (textNode) {
          textNode.textContent = 'Copied!';
        }
        setTimeout(function () {
          copyBtn.classList.remove('copied');
          if (textNode) {
            textNode.textContent = 'Copy';
          }
        }, 2000);
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(textToCopy).then(markCopied).catch(function () {
          fallbackCopy(textToCopy, markCopied);
        });
      } else {
        fallbackCopy(textToCopy, markCopied);
      }
    });
  }

  function fallbackCopy(text, callback) {
    var textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '0';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      callback();
    } catch (e) {
      // Copy failed silently
    }
    document.body.removeChild(textArea);
  }
})();
