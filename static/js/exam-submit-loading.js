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

  function copyAllowedTarget(target) {
    if (!target || !target.closest) {
      return false;
    }
    return !!target.closest(
      'input, textarea, select, button, .exam-text-answer, ' +
      '.demo-ai-box, .demo-feedback, #demo-feedback-panel'
    );
  }

  function wireQuestionCopyProtection() {
    document.querySelectorAll('.js-exam-no-copy').forEach(function (card) {
      ['copy', 'cut', 'contextmenu'].forEach(function (type) {
        card.addEventListener(type, function (ev) {
          if (copyAllowedTarget(ev.target)) {
            return;
          }
          if (!ev.target.closest('.exam-protected-content')) {
            return;
          }
          ev.preventDefault();
        });
      });
      card.addEventListener('dragstart', function (ev) {
        if (copyAllowedTarget(ev.target)) {
          return;
        }
        if (ev.target.closest('.exam-protected-content img, .exam-protected-content .demo-q-text')) {
          ev.preventDefault();
        }
      });
    });
  }

  function attachExamWatermarks() {
    document.querySelectorAll('.js-exam-no-copy').forEach(function (card) {
      if (card.querySelector('.exam-anti-leak-watermark')) {
        return;
      }
      var label = (card.getAttribute('data-exam-watermark') || 'Soma Smart').trim();
      var layer = document.createElement('div');
      layer.className = 'exam-anti-leak-watermark';
      layer.setAttribute('aria-hidden', 'true');
      for (var i = 0; i < 6; i += 1) {
        var line = document.createElement('span');
        line.className = 'exam-anti-leak-watermark__line';
        line.textContent = label + ' · Do not share';
        layer.appendChild(line);
      }
      card.insertBefore(layer, card.firstChild);
    });
  }

  function setQuestionCardsObscured(obscured) {
    document.querySelectorAll('.js-exam-no-copy').forEach(function (card) {
      card.classList.toggle('is-exam-obscured', obscured);
      var notice = card.querySelector('.exam-obscure-notice');
      if (notice) {
        notice.hidden = !obscured;
      }
    });
  }

  var obscureFlashTimer;
  function flashQuestionObscure(durationMs) {
    setQuestionCardsObscured(true);
    window.clearTimeout(obscureFlashTimer);
    obscureFlashTimer = window.setTimeout(function () {
      if (!document.hidden) {
        setQuestionCardsObscured(false);
      }
    }, durationMs || 2000);
  }

  function wireScreenshotDeterrents() {
    if (!document.body.classList.contains('exam-take-page')) {
      return;
    }
    attachExamWatermarks();

    document.addEventListener('visibilitychange', function () {
      setQuestionCardsObscured(document.hidden);
    });
    setQuestionCardsObscured(document.hidden);

    document.addEventListener('keyup', function (ev) {
      var key = ev.key || '';
      if (key === 'PrintScreen' || key === 'Snapshot') {
        flashQuestionObscure(2500);
      }
    });
  }

  preventPasteOnTypedAnswers(document);
  wireQuestionCopyProtection();
  wireScreenshotDeterrents();

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