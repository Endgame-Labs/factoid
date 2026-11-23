(function () {
  'use strict';

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
