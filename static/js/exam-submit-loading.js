(function () {
  'use strict';

  function busyLabel(form) {
    return form.getAttribute('data-submit-busy-text') || 'Please wait…';
  }

  function preventPasteOnTypedAnswers(root) {
    root.querySelectorAll('.js-exam-no-paste').forEach(function (el) {
      el.setAttribute('autocomplete', 'off');
      el.setAttribute('spellcheck', 'false');
      el.addEventListener('paste', function (ev) {
        ev.preventDefault();
      });
      el.addEventListener('drop', function (ev) {
        ev.preventDefault();
      });
      el.addEventListener('beforeinput', function (ev) {
        var t = ev.inputType || '';
        if (t === 'insertFromPaste' || t === 'insertFromDrop' || t === 'insertFromYank') {
          ev.preventDefault();
        }
      });
    });
  }

  function freezeFormForSubmit(form) {
    form.querySelectorAll('.exam-submit-clone').forEach(function (node) {
      node.remove();
    });

    var payload = new FormData(form);
    payload.forEach(function (value, key) {
      if (key === 'csrfmiddlewaretoken') {
        return;
      }
      var hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = key;
      hidden.value = value;
      hidden.className = 'exam-submit-clone';
      form.appendChild(hidden);
    });

    form.querySelectorAll('input, textarea, select, button').forEach(function (el) {
      if (el.classList.contains('exam-submit-clone')) {
        return;
      }
      if (el.name === 'csrfmiddlewaretoken') {
        return;
      }
      if (el.type === 'submit') {
        el.disabled = true;
        return;
      }
      el.disabled = true;
    });
  }

  function showQuestionCardOverlay(form) {
    var card = form.closest('.demo-question-card');
    if (!card || card.querySelector('.exam-question-submit-overlay')) {
      return;
    }
    card.classList.add('is-exam-submitting');

    var overlay = document.createElement('div');
    overlay.className = 'exam-question-submit-overlay';
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-live', 'polite');
    overlay.setAttribute('aria-busy', 'true');

    var spinner = document.createElement('span');
    spinner.className = 'demo-ai-spinner exam-question-submit-spinner';
    spinner.setAttribute('aria-hidden', 'true');

    var text = document.createElement('span');
    text.className = 'exam-question-submit-text';
    text.textContent = busyLabel(form);

    overlay.appendChild(spinner);
    overlay.appendChild(text);
    card.appendChild(overlay);
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
    form.classList.add('is-exam-submitting');

    freezeFormForSubmit(form);
    showQuestionCardOverlay(form);

    return true;
  }

  preventPasteOnTypedAnswers(document);

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