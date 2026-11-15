(function () {
  'use strict';

  function pauseOtherAudioElements(exceptEl) {
    document.querySelectorAll('audio').forEach(function (el) {
      if (el !== exceptEl && !el.paused) {
        try {
          el.pause();
        } catch (error) {
          // ignore
        }
      }
    });
  }

  function onAudioPlay(event) {
    var current = event.currentTarget;
    if (typeof window.SomaStopAllAudio === 'function') {
      window.SomaStopAllAudio({ silent: true, exceptAudio: current });
    } else {
      pauseOtherAudioElements(current);
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    }
  }

  function bindInlineAudioPlayers() {
    document.querySelectorAll('audio').forEach(function (audioEl) {
      if (audioEl.dataset.somaExclusiveAudio === '1') return;
      audioEl.dataset.somaExclusiveAudio = '1';
      audioEl.addEventListener('play', onAudioPlay);
    });
  }

  window.SomaExclusiveAudio = {
    bind: bindInlineAudioPlayers,
    pauseOthers: pauseOtherAudioElements,
  };

  function boot() {
    bindInlineAudioPlayers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();