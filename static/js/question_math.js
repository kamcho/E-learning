(function () {
  var MATH_RENDER_OPTIONS = {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
      { left: '\\(', right: '\\)', display: false },
      { left: '\\[', right: '\\]', display: true },
    ],
    throwOnError: false,
    ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
  };

  var MATH_SELECTORS = [
    '[data-math-content]',
    '.demo-q-text',
    '.demo-option-text',
    '.demo-ai-text:not(.demo-ai-error)',
    '.ai-explanation-text',
  ].join(', ');

  function renderMathOnElement(el, force) {
    if (!el || typeof renderMathInElement !== 'function') {
      return;
    }
    if (force) {
      delete el.dataset.mathRendered;
    }
    if (el.dataset.mathRendered === 'true') {
      return;
    }
    renderMathInElement(el, MATH_RENDER_OPTIONS);
    el.dataset.mathRendered = 'true';
  }

  function renderQuestionMath(root) {
    var scope = root || document;
    if (scope.nodeType === 1 && scope.matches && scope.matches(MATH_SELECTORS)) {
      renderMathOnElement(scope, true);
      return;
    }
    scope.querySelectorAll(MATH_SELECTORS).forEach(function (el) {
      renderMathOnElement(el, false);
    });
  }

  /** Call after dynamically setting explanation text (AI tutor). */
  function refreshExplanationMath(el) {
    renderMathOnElement(el, true);
  }

  window.renderQuestionMath = renderQuestionMath;
  window.refreshExplanationMath = refreshExplanationMath;

  document.addEventListener('DOMContentLoaded', function () {
    renderQuestionMath();
  });
})();
