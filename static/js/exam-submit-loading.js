(function () {
  'use strict';

  function busyLabel(form) {
    return form.getAttribute('data-submit-busy-text') || 'Please wait…';
  }

  function lockExamForm(form) {
    if (form.dataset.examSubmitting === '1') {
      return false;
    }
    var submitBtn = form.querySelector('button[type="submit"]');
    if (!submitBtn || submitBtn.disabled) {
      return false;
    }

    form.dataset.examSubmitting = '1';
    form.setAttribute('aria-busy', 'true');

    var spinner = document.createElement('span');
    spinner.className = 'demo-ai-spinner exam-submit-btn-spinner';
    spinner.setAttribute('aria-hidden', 'true');

    var label = document.createElement('span');
    label.className = 'exam-submit-btn-label';
    label.textContent = busyLabel(form);

    submitBtn.replaceChildren(spinner, label);
    submitBtn.disabled = true;
    submitBtn.setAttribute('aria-busy', 'true');

    form.querySelectorAll('input, textarea, select, button').forEach(function (el) {
      if (el.type === 'hidden' || el === submitBtn) {
        return;
      }
      el.disabled = true;
    });

    return true;
  }

  document.querySelectorAll('form.js-exam-submit-form').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      if (form.dataset.examSubmitting === '1') {
        ev.preventDefault();
        return;
      }
      if (!lockExamForm(form)) {
        ev.preventDefault();
      }
    });
  });
})();