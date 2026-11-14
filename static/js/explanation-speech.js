(function () {
  var openaiCfg = window.SomaOpenAITts;
  var openaiEnabled = !!(openaiCfg && openaiCfg.url && openaiCfg.voices && openaiCfg.voices.length);
  var browserTtsSupported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  var canSpeak = openaiEnabled || browserTtsSupported;

  var openaiVoiceKey = 'soma-openai-tts-voice';
  var browserVoiceKey = 'soma-smart-explanation-voice';

  var activeRegion = null;
  var activeAudio = null;
  var activeObjectUrl = null;
  var browserVoices = [];

  function getStoredVoice(key) {
    try {
      return window.localStorage.getItem(key) || '';
    } catch (error) {
      return '';
    }
  }

  function setStoredVoice(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // Preference still applies for this page when storage is unavailable.
    }
  }

  function setHidden(element, hidden) {
    if (element && element.hidden !== hidden) element.hidden = hidden;
  }

  function getSpeechTextNode(region) {
    return region.querySelector('[data-speech-text]');
  }

  function speechPlainText(region) {
    var text = getSpeechTextNode(region);
    if (!text) return '';
    return text.textContent.replace(/\s+/g, ' ').trim();
  }

  function labelOpenAIVoice(name) {
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  function populateOpenAIVoiceSelect(select) {
    var preferred = getStoredVoice(openaiVoiceKey);
    var names = openaiCfg.voices.slice();

    if (preferred && names.indexOf(preferred) === -1) {
      preferred = '';
      setStoredVoice(openaiVoiceKey, '');
    }
    if (!preferred && openaiCfg.defaultVoice && names.indexOf(openaiCfg.defaultVoice) !== -1) {
      preferred = openaiCfg.defaultVoice;
    }

    select.replaceChildren();
    names.forEach(function (voiceName) {
      var option = document.createElement('option');
      option.value = voiceName;
      option.textContent = labelOpenAIVoice(voiceName);
      select.appendChild(option);
    });
    select.value = preferred || names[0] || '';
  }

  function populateBrowserVoiceSelect(select) {
    var preferredVoiceUri = getStoredVoice(browserVoiceKey);
    var availableVoiceUris = browserVoices.map(function (voice) {
      return voice.voiceURI;
    });

    if (preferredVoiceUri && availableVoiceUris.indexOf(preferredVoiceUri) === -1) {
      preferredVoiceUri = '';
      setStoredVoice(browserVoiceKey, '');
    }

    select.replaceChildren();
    var defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Default voice';
    select.appendChild(defaultOption);

    browserVoices.forEach(function (voice) {
      var option = document.createElement('option');
      option.value = voice.voiceURI;
      option.textContent = voice.lang ? voice.name + ' (' + voice.lang + ')' : voice.name;
      select.appendChild(option);
    });
    select.value = preferredVoiceUri;
  }

  function populateVoiceSelect(select) {
    if (openaiEnabled) {
      populateOpenAIVoiceSelect(select);
    } else if (browserTtsSupported) {
      populateBrowserVoiceSelect(select);
    }
  }

  function refreshBrowserVoices() {
    if (!browserTtsSupported) return;
    browserVoices = window.speechSynthesis.getVoices();
    if (!openaiEnabled) {
      document.querySelectorAll('[data-speech-voice]').forEach(populateVoiceSelect);
    }
  }

  function setPlaybackState(region, playing) {
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var status = region.querySelector('[data-speech-status]');

    if (speakButton && speakButton.disabled !== playing) speakButton.disabled = playing;
    setHidden(stopButton, !playing);
    if (status) {
      var message = playing ? 'Preparing read-aloud…' : '';
      if (status.textContent !== message) status.textContent = message;
    }
  }

  function revokeObjectUrl() {
    if (activeObjectUrl) {
      URL.revokeObjectURL(activeObjectUrl);
      activeObjectUrl = null;
    }
  }

  function stopSpeech() {
    if (activeAudio) {
      activeAudio.pause();
      activeAudio.onended = null;
      activeAudio.onerror = null;
      activeAudio = null;
    }
    revokeObjectUrl();

    if (browserTtsSupported) {
      window.speechSynthesis.cancel();
    }

    if (activeRegion) {
      setPlaybackState(activeRegion, false);
      activeRegion = null;
    }
  }

  function updateRegion(region) {
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var voiceSelect = region.querySelector('[data-speech-voice]');
    var status = region.querySelector('[data-speech-status]');
    var ready = !!speechPlainText(region);

    setHidden(speakButton, !ready || !canSpeak);
    setHidden(voiceSelect, !ready || !canSpeak);
    var voiceLabel = voiceSelect && voiceSelect.closest('.speech-voice-choice');
    if (voiceLabel) setHidden(voiceLabel, !ready || !canSpeak);
    if (!ready) setHidden(stopButton, true);

    if (!canSpeak && status) {
      var message = openaiCfg === null
        ? 'Read-aloud is not configured.'
        : 'Text-to-speech is not available in this browser.';
      if (status.textContent !== message) status.textContent = message;
    }
  }

  function speakWithBrowser(region, plainText) {
    var utterance = new SpeechSynthesisUtterance(plainText);
    var voiceSelect = region.querySelector('[data-speech-voice]');
    var selectedVoice = voiceSelect && browserVoices.find(function (voice) {
      return voice.voiceURI === voiceSelect.value;
    });
    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }
    utterance.lang = (selectedVoice && selectedVoice.lang) || document.documentElement.lang || 'en';
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
    var status = region.querySelector('[data-speech-status]');
    if (status) status.textContent = 'Speaking…';
  }

  function playOpenAIAudio(region, blob) {
    revokeObjectUrl();
    activeObjectUrl = URL.createObjectURL(blob);
    activeAudio = new Audio(activeObjectUrl);
    activeAudio.onended = function () {
      if (activeRegion === region) {
        setPlaybackState(region, false);
        activeRegion = null;
        var status = region.querySelector('[data-speech-status]');
        if (status) status.textContent = 'Playback finished.';
      }
      revokeObjectUrl();
      activeAudio = null;
    };
    activeAudio.onerror = function () {
      if (activeRegion === region) {
        setPlaybackState(region, false);
        activeRegion = null;
        var status = region.querySelector('[data-speech-status]');
        if (status) status.textContent = 'Speech playback could not be completed.';
      }
      revokeObjectUrl();
      activeAudio = null;
    };
    var status = region.querySelector('[data-speech-status]');
    if (status) status.textContent = 'Speaking…';
    return activeAudio.play();
  }

  function requestOpenAISpeech(region, plainText, voiceName) {
    return fetch(openaiCfg.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': openaiCfg.csrfToken || '',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ text: plainText, voice: voiceName || undefined }),
    }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () {
          return {};
        }).then(function (data) {
          var message = (data && data.error) || 'Could not generate speech.';
          throw new Error(message);
        });
      }
      return res.blob();
    });
  }

  document.querySelectorAll('[data-speech-region]').forEach(function (region) {
    updateRegion(region);
    var voiceSelect = region.querySelector('[data-speech-voice]');
    if (voiceSelect) {
      populateVoiceSelect(voiceSelect);
      voiceSelect.addEventListener('change', function () {
        if (openaiEnabled) {
          setStoredVoice(openaiVoiceKey, voiceSelect.value);
        } else {
          setStoredVoice(browserVoiceKey, voiceSelect.value);
        }
      });
    }

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

  if (browserTtsSupported) {
    refreshBrowserVoices();
    window.speechSynthesis.addEventListener('voiceschanged', refreshBrowserVoices);
  }

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
    var plainText = region && speechPlainText(region);
    if (!region || !plainText || !canSpeak) return;

    stopSpeech();
    activeRegion = region;
    setPlaybackState(region, true);

    var voiceSelect = region.querySelector('[data-speech-voice]');
    var selectedOpenAIVoice = voiceSelect && voiceSelect.value;

    if (openaiEnabled) {
      requestOpenAISpeech(region, plainText, selectedOpenAIVoice)
        .then(function (blob) {
          if (activeRegion !== region) return;
          return playOpenAIAudio(region, blob);
        })
        .catch(function (err) {
          if (activeRegion !== region) return;
          if (browserTtsSupported) {
            var status = region.querySelector('[data-speech-status]');
            if (status) {
              status.textContent = (err && err.message ? err.message + ' ' : '') + 'Using browser voice instead.';
            }
            speakWithBrowser(region, plainText);
            return;
          }
          setPlaybackState(region, false);
          activeRegion = null;
          var failStatus = region.querySelector('[data-speech-status]');
          if (failStatus) {
            failStatus.textContent = err && err.message ? err.message : 'Could not generate speech.';
          }
        });
      return;
    }

    if (browserTtsSupported) {
      speakWithBrowser(region, plainText);
    }
  });
})();