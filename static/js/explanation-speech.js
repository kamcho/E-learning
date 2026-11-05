(function () {
  var speechSupported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  var activeRegion = null;

  function setHidden(element, hidden) {
    if (element && element.hidden !== hidden) element.hidden = hidden;
  }

  function setPlaybackState(region, playing) {
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var status = region.querySelector('[data-speech-status]');

    if (speakButton && speakButton.disabled !== playing) speakButton.disabled = playing;
    setHidden(stopButton, !playing);
    if (status) {
      var message = playing ? 'Speaking explanation.' : '';
      if (status.textContent !== message) status.textContent = message;
    }
  }

  function stopSpeech() {
    if (!activeRegion) return;
    window.speechSynthesis.cancel();
    setPlaybackState(activeRegion, false);
    activeRegion = null;
  }

  function updateRegion(region) {
    var text = region.querySelector('[data-speech-text]');
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var status = region.querySelector('[data-speech-status]');
    var ready = text && !text.hidden && text.textContent.trim();

    setHidden(speakButton, !ready || !speechSupported);
    if (!ready) setHidden(stopButton, true);
    if (!speechSupported && status) {
      var message = 'Text-to-speech is not supported in this browser.';
      if (status.textContent !== message) status.textContent = message;
    }
  }

  document.querySelectorAll('[data-speech-region]').forEach(function (region) {
    updateRegion(region);

    var observer = new MutationObserver(function () {
      updateRegion(region);
    });
    observer.observe(region, {
      attributes: true,
      childList: true,
      characterData: true,
      subtree: true,
      attributeFilter: ['hidden'],
    });
  });

  document.addEventListener('click', function (event) {
    var speakButton = event.target.closest('[data-speech-speak]');
    var stopButton = event.target.closest('[data-speech-stop]');

    if (stopButton) {
      stopSpeech();
      var stoppedStatus = stopButton.closest('[data-speech-region]').querySelector('[data-speech-status]');
      if (stoppedStatus) stoppedStatus.textContent = 'Speech stopped.';
      return;
    }

    if (!speakButton) return;

    var region = speakButton.closest('[data-speech-region]');
    var text = region && region.querySelector('[data-speech-text]');
    if (!region || !text || !text.textContent.trim() || !speechSupported) return;

    stopSpeech();
    activeRegion = region;
    setPlaybackState(region, true);

    var utterance = new SpeechSynthesisUtterance(text.textContent.trim());
    utterance.lang = document.documentElement.lang || 'en';
    utterance.onend = function () {
      if (activeRegion === region) {
        setPlaybackState(region, false);
        activeRegion = null;
        var status = region.querySelector('[data-speech-status]');
        if (status) status.textContent = 'Playback finished.';
      }
    };
    utterance.onerror = function () {
      if (activeRegion === region) {
        setPlaybackState(region, false);
        activeRegion = null;
        var status = region.querySelector('[data-speech-status]');
        if (status) status.textContent = 'Speech playback could not be completed.';
      }
    };
    window.speechSynthesis.speak(utterance);
  });
})();
