(function () {
  var MATH_RENDER_OPTIONS = {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false },
      { left: '$', right: '$', display: false },
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

  var pendingReady = [];

  function shouldSkipInitialRender(el) {
    if (!el || !el.classList) {
      return false;
    }
    if (el.classList.contains('demo-ai-text') && !el.classList.contains('demo-ai-error')) {
      return !(el.textContent && el.textContent.trim());
    }
    if (el.classList.contains('ai-explanation-text')) {
      return !(el.textContent && el.textContent.trim());
    }
    return false;
  }

  function renderMathOnElement(el, force) {
    if (!el) {
      return;
    }
    if (force) {
      delete el.dataset.mathRendered;
    } else if (shouldSkipInitialRender(el)) {
      return;
    }
    if (el.dataset.mathRendered === 'true') {
      return;
    }
    if (typeof renderMathInElement !== 'function') {
      return;
    }
    renderMathInElement(el, MATH_RENDER_OPTIONS);
    el.dataset.mathRendered = 'true';
  }

  function renderQuestionMath(root, opts) {
    var force = opts && opts.force;
    var scope = root || document;
    if (scope.nodeType === 1 && scope.matches && scope.matches('[data-math-content], .demo-ai-text, .ai-explanation-text, .demo-q-text, .demo-option-text')) {
      renderMathOnElement(scope, !!force);
      return;
    }
    scope.querySelectorAll(MATH_SELECTORS).forEach(function (el) {
      renderMathOnElement(el, !!force);
    });
  }

  function flushQuestionMathReady() {
    if (typeof renderMathInElement !== 'function') {
      return;
    }
    var queue = pendingReady.slice();
    pendingReady.length = 0;
    queue.forEach(function (cb) {
      try {
        cb();
      } catch (error) {
        // Keep other explanation callbacks running if one fails.
      }
    });
  }

  function whenQuestionMathReady(callback) {
    if (typeof callback !== 'function') {
      return;
    }
    if (typeof renderMathInElement === 'function') {
      callback();
      return;
    }
    pendingReady.push(callback);
  }

  /** Call after dynamically setting explanation text (AI tutor). */
  function refreshExplanationMath(el) {
    whenQuestionMathReady(function () {
      renderMathOnElement(el, true);
    });
  }

  window.renderQuestionMath = renderQuestionMath;
  window.refreshExplanationMath = refreshExplanationMath;
  window.whenQuestionMathReady = whenQuestionMathReady;

  document.addEventListener('DOMContentLoaded', function () {
    flushQuestionMathReady();
    renderQuestionMath();
  });

  window.addEventListener('load', function () {
    flushQuestionMathReady();
    document.querySelectorAll('.demo-ai-text:not(.demo-ai-error), .ai-explanation-text').forEach(function (el) {
      if (el.textContent && el.textContent.trim()) {
        renderMathOnElement(el, true);
      }
    });
  });
})();
