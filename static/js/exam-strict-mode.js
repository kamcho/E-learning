(function () {
  'use strict';

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) {
      return input.value;
    }
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function getRoot() {
    return document.getElementById('exam-take-root');
  }

  function updateStrictBanner(tabLeaves, maxLeaves, maxAwaySeconds) {
    var banner = document.getElementById('exam-strict-banner');
    if (!banner) {
      return;
    }
    var remaining = Math.max(0, maxLeaves - tabLeaves);
    banner.textContent =
      'Strict mode is on. You may leave this tab at most ' +
      maxLeaves +
      ' times, and not longer than ' +
      maxAwaySeconds +
      ' seconds each time. Remaining switches: ' +
      remaining +
      '.';
  }

  function wireStrictMode() {
    var root = getRoot();
    if (!root || root.getAttribute('data-exam-strict') !== '1') {
      return;
    }

    var maxLeaves = parseInt(root.getAttribute('data-strict-max-leaves') || '3', 10);
    var maxAwayMs = parseInt(root.getAttribute('data-strict-max-away-ms') || '10000', 10);
    var maxAwaySeconds = Math.round(maxAwayMs / 1000);
    var resetUrl = root.getAttribute('data-strict-reset-url') || '';
    if (!resetUrl) {
      return;
    }

    var tabLeaves = 0;
    var hiddenAt = null;
    var awayTimer = null;
    var resetting = false;

    updateStrictBanner(tabLeaves, maxLeaves, maxAwaySeconds);

    function clearAwayTimer() {
      if (awayTimer !== null) {
        window.clearTimeout(awayTimer);
        awayTimer = null;
      }
    }

    function setCardsObscured(obscured) {
      document.querySelectorAll('.js-exam-no-copy').forEach(function (card) {
        card.classList.toggle('is-exam-obscured', obscured);
        var notice = card.querySelector('.exam-obscure-notice');
        if (notice) {
          notice.hidden = !obscured;
        }
      });
    }

    function triggerReset(reason) {
      if (resetting) {
        return;
      }
      resetting = true;
      clearAwayTimer();
      root.classList.add('is-exam-strict-resetting');

      var body = 'reason=' + encodeURIComponent(reason || 'tab_violation');
      fetch(resetUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': csrfToken(),
        },
        credentials: 'same-origin',
        body: body,
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          if (data && data.redirect) {
            window.location.href = data.redirect;
            return;
          }
          window.location.reload();
        })
        .catch(function () {
          window.location.reload();
        });
    }

    document.addEventListener('visibilitychange', function () {
      if (resetting) {
        return;
      }
      if (document.hidden) {
        hiddenAt = Date.now();
        setCardsObscured(true);
        clearAwayTimer();
        awayTimer = window.setTimeout(function () {
          if (!document.hidden || hiddenAt === null) {
            return;
          }
          if (Date.now() - hiddenAt > maxAwayMs) {
            triggerReset('away_too_long');
          }
        }, maxAwayMs + 100);
        return;
      }

      if (hiddenAt === null) {
        return;
      }

      var awayMs = Date.now() - hiddenAt;
      hiddenAt = null;
      clearAwayTimer();
      setCardsObscured(false);

      if (awayMs > maxAwayMs) {
        triggerReset('away_too_long');
        return;
      }

      tabLeaves += 1;
      updateStrictBanner(tabLeaves, maxLeaves, maxAwaySeconds);
      if (tabLeaves > maxLeaves) {
        triggerReset('too_many_leaves');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireStrictMode);
  } else {
    wireStrictMode();
  }
})();