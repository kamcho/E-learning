(function () {
  function renderQuestionMath(root) {
    if (typeof renderMathInElement !== 'function') {
      return;
    }
    var scope = root || document;
    scope.querySelectorAll('[data-math-content]').forEach(function (el) {
      if (el.dataset.mathRendered === 'true') {
        return;
      }
      renderMathInElement(el, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\(', right: '\\)', display: false },
          { left: '\\[', right: '\\]', display: true },
        ],
        throwOnError: false,
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
      });
      el.dataset.mathRendered = 'true';
    });
  }

  window.renderQuestionMath = renderQuestionMath;

  document.addEventListener('DOMContentLoaded', function () {
    renderQuestionMath();
  });
})();
