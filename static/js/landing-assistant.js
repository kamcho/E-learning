(function () {
  var root = document.getElementById('landing-assistant-root');
  if (!root) return;

  var messagesEl = document.getElementById('landing-assistant-messages');
  var form = document.getElementById('landing-assistant-form');
  var input = document.getElementById('landing-assistant-input');
  var sendBtn = document.getElementById('landing-assistant-send');
  var chatUrl = window.LANDING_ASSISTANT_CHAT_URL;

  function getCsrfToken() {
    var inputTok = form && form.querySelector('[name=csrfmiddlewaretoken]');
    if (inputTok && inputTok.value) return inputTok.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function scrollMessages() {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendMessage(role, text, extraClass) {
    var wrap = document.createElement('div');
    wrap.className =
      'landing-assistant-msg landing-assistant-msg--' +
      (role === 'user' ? 'user' : 'bot') +
      (extraClass ? ' ' + extraClass : '');
    var bubble = document.createElement('div');
    bubble.className = 'landing-assistant-msg__bubble';
    bubble.textContent = text;
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollMessages();
    return wrap;
  }

  function openAssistant() {
    root.classList.add('is-open');
    root.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    if (input && !input.disabled) {
      window.setTimeout(function () { input.focus(); }, 120);
    }
  }

  function closeAssistant() {
    root.classList.remove('is-open');
    root.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function bindOpenControls() {
    document.querySelectorAll('[data-landing-assistant-open]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        var panel = document.getElementById('landing-mobile-panel');
        if (panel && panel.classList.contains('is-open')) {
          panel.classList.remove('is-open');
          panel.setAttribute('aria-hidden', 'true');
          var toggle = document.getElementById('landing-menu-toggle');
          if (toggle) toggle.setAttribute('aria-expanded', 'false');
          document.body.style.overflow = '';
        }
        openAssistant();
      });
    });
  }
  bindOpenControls();

  root.querySelectorAll('[data-landing-assistant-close]').forEach(function (el) {
    el.addEventListener('click', closeAssistant);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && root.classList.contains('is-open')) {
      closeAssistant();
    }
  });

  if (!form || !chatUrl) return;

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = (input.value || '').trim();
    if (!text) return;

    appendMessage('user', text);
    input.value = '';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    var pending = appendMessage('bot', 'Thinking…', 'landing-assistant-msg--pending');

    fetch(chatUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      credentials: 'same-origin',
      body: JSON.stringify({ message: text }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        pending.remove();
        if (result.data && result.data.reply) {
          appendMessage('bot', result.data.reply);
        } else if (result.data && result.data.error) {
          appendMessage('bot', result.data.error);
        } else {
          appendMessage('bot', 'Something went wrong. Please try again.');
        }
      })
      .catch(function () {
        pending.remove();
        appendMessage('bot', 'Could not reach the server. Check your connection and try again.');
      })
      .finally(function () {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
      });
  });
})();