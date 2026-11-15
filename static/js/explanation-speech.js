(function () {
  'use strict';

  var openaiCfg = window.SomaOpenAITts;
  var openaiVoices = openaiCfg && Array.isArray(openaiCfg.voices) ? openaiCfg.voices : [];
  var openaiEnabled = !!(openaiCfg && openaiCfg.url && openaiVoices.length);
  var browserTtsSupported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

  var openaiVoiceKey = 'soma-openai-tts-voice';
  var browserVoiceKey = 'soma-smart-explanation-voice';

  var activeRegion = null;
  var activeAudio = null;
  var activeObjectUrl = null;
  var browserVoices = [];
  var browserVoicesReady = false;

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

  function prerecordedAudioUrl(region) {
    if (!region) return '';
    return (region.getAttribute('data-speech-audio-url') || '').trim();
  }

  function willPlayRecording(region) {
    return !!prerecordedAudioUrl(region) && region.getAttribute('data-speech-use-tts') !== '1';
  }

  function speechPlainText(region) {
    var text = region.querySelector('[data-speech-text]');
    if (!text || text.hidden) return '';
    return (text.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function speechControlsRoot(region) {
    return region.querySelector('.explanation-speech-controls') || region;
  }

  function ensureSpeechModeUi(region) {
    var root = speechControlsRoot(region);
    if (!root.querySelector('[data-speech-mode-badge]')) {
      var badge = document.createElement('span');
      badge.setAttribute('data-speech-mode-badge', '');
      badge.className = 'speech-mode-badge speech-mode-badge--recording';
      badge.hidden = true;
      var speak = root.querySelector('[data-speech-speak]');
      if (speak) root.insertBefore(badge, speak);
      else root.prepend(badge);
    }
    if (!root.querySelector('[data-speech-tts-hint]')) {
      var ttsHint = document.createElement('span');
      ttsHint.setAttribute('data-speech-tts-hint', '');
      ttsHint.className = 'speech-mode-badge speech-mode-badge--tts';
      ttsHint.textContent = 'AI voice';
      ttsHint.hidden = true;
      var voiceLabel = root.querySelector('.speech-voice-choice');
      if (voiceLabel) voiceLabel.insertBefore(ttsHint, voiceLabel.firstChild);
      else root.appendChild(ttsHint);
    }
  }

  function labelOpenAIVoice(name) {
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  function populateOpenAIVoiceSelect(select) {
    var preferred = getStoredVoice(openaiVoiceKey);
    if (preferred && openaiVoices.indexOf(preferred) === -1) {
      preferred = '';
      setStoredVoice(openaiVoiceKey, '');
    }
    if (!preferred && openaiCfg.defaultVoice && openaiVoices.indexOf(openaiCfg.defaultVoice) !== -1) {
      preferred = openaiCfg.defaultVoice;
    }
    select.replaceChildren();
    openaiVoices.forEach(function (voiceName) {
      var option = document.createElement('option');
      option.value = voiceName;
      option.textContent = labelOpenAIVoice(voiceName);
      select.appendChild(option);
    });
    select.value = preferred || openaiVoices[0] || '';
  }

  function populateBrowserVoiceSelect(select) {
    var preferredVoiceUri = getStoredVoice(browserVoiceKey);
    var uris = browserVoices.map(function (v) { return v.voiceURI; });
    if (preferredVoiceUri && uris.indexOf(preferredVoiceUri) === -1) {
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
    if (openaiEnabled) populateOpenAIVoiceSelect(select);
    else if (browserTtsSupported && browserVoices.length) populateBrowserVoiceSelect(select);
  }

  function initBrowserVoicesOnce() {
    if (!browserTtsSupported || openaiEnabled) return;
    function applyVoices() {
      var voices = window.speechSynthesis.getVoices();
      if (!voices.length) return false;
      browserVoices = voices;
      browserVoicesReady = true;
      document.querySelectorAll('[data-speech-voice]').forEach(populateVoiceSelect);
      return true;
    }
    if (applyVoices()) return;
    function onVoicesChanged() {
      if (applyVoices()) {
        window.speechSynthesis.removeEventListener('voiceschanged', onVoicesChanged);
      }
    }
    window.speechSynthesis.addEventListener('voiceschanged', onVoicesChanged);
    window.setTimeout(function () {
      if (!browserVoicesReady) onVoicesChanged();
    }, 250);
  }

  function finishPlayback(region, statusMessage) {
    if (!region) return;
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var status = region.querySelector('[data-speech-status]');
    if (speakButton) speakButton.disabled = false;
    setHidden(stopButton, true);
    if (status && statusMessage) status.textContent = statusMessage;
    if (activeRegion === region) activeRegion = null;
  }

  function setPlaybackState(region, playing) {
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var status = region.querySelector('[data-speech-status]');
    if (speakButton) speakButton.disabled = !!playing;
    setHidden(stopButton, !playing);
    if (status && playing) {
      status.textContent = willPlayRecording(region) ? 'Playing recording…' : 'Preparing AI voice…';
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
    if (browserTtsSupported) window.speechSynthesis.cancel();
    if (activeRegion) finishPlayback(activeRegion, 'Speech stopped.');
  }

  function wireAudioElement(region, audioEl) {
    audioEl.onended = function () {
      finishPlayback(region, 'Playback finished.');
      activeAudio = null;
      revokeObjectUrl();
    };
    audioEl.onerror = function () {
      finishPlayback(region, 'Could not play audio.');
      activeAudio = null;
      revokeObjectUrl();
    };
    var status = region.querySelector('[data-speech-status]');
    if (status) status.textContent = 'Speaking…';
    return audioEl.play();
  }

  function playRecordedUrl(region, url) {
    revokeObjectUrl();
    activeAudio = new Audio(url);
    return wireAudioElement(region, activeAudio);
  }

  function updateRegion(region) {
    ensureSpeechModeUi(region);
    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    var voiceSelect = region.querySelector('[data-speech-voice]');
    var voiceLabel = voiceSelect && voiceSelect.closest('.speech-voice-choice');
    var root = speechControlsRoot(region);
    var badge = root.querySelector('[data-speech-mode-badge]');
    var ttsHint = root.querySelector('[data-speech-tts-hint]');

    var useRecording = willPlayRecording(region);
    var plainText = speechPlainText(region);
    var hasTts = !!(plainText && (openaiEnabled || browserTtsSupported));
    var canSpeak = useRecording || hasTts;

    setHidden(speakButton, !canSpeak);
    if (speakButton && !speakButton.disabled) speakButton.disabled = false;

    if (useRecording) {
      region.classList.add('speech-region--recording');
      region.classList.remove('speech-region--tts');
      if (badge) {
        setHidden(badge, false);
        badge.textContent = 'Recorded audio';
      }
      if (ttsHint) setHidden(ttsHint, true);
      setHidden(voiceSelect, true);
      if (voiceLabel) setHidden(voiceLabel, true);
    } else if (hasTts) {
      region.classList.remove('speech-region--recording');
      region.classList.add('speech-region--tts');
      if (badge) setHidden(badge, true);
      if (ttsHint) setHidden(ttsHint, false);
      setHidden(voiceSelect, false);
      if (voiceLabel) setHidden(voiceLabel, false);
    } else {
      region.classList.remove('speech-region--recording', 'speech-region--tts');
      if (badge) setHidden(badge, true);
      if (ttsHint) setHidden(ttsHint, true);
      setHidden(voiceSelect, true);
      if (voiceLabel) setHidden(voiceLabel, true);
    }

    if (speakButton) {
      if (!speakButton.getAttribute('data-default-label')) {
        speakButton.setAttribute('data-default-label', (speakButton.textContent || '').trim());
      }
      var labelRecorded = speakButton.getAttribute('data-label-recorded') || 'Play recording';
      var labelTts = speakButton.getAttribute('data-default-label') || 'Listen';
      speakButton.textContent = useRecording ? labelRecorded : labelTts;
    }

    if (!canSpeak) setHidden(stopButton, true);
  }

  function speakWithBrowser(region, plainText) {
    var utterance = new SpeechSynthesisUtterance(plainText);
    var voiceSelect = region.querySelector('[data-speech-voice]');
    var selectedVoice = voiceSelect && browserVoices.find(function (voice) {
      return voice.voiceURI === voiceSelect.value;
    });
    if (selectedVoice) utterance.voice = selectedVoice;
    utterance.lang = (selectedVoice && selectedVoice.lang) || document.documentElement.lang || 'en';
    utterance.onend = function () {
      finishPlayback(region, 'Playback finished.');
    };
    utterance.onerror = function () {
      finishPlayback(region, 'Speech playback could not be completed.');
    };
    window.speechSynthesis.speak(utterance);
    var status = region.querySelector('[data-speech-status]');
    if (status) status.textContent = 'Speaking…';
  }

  function playOpenAIAudio(region, blob) {
    revokeObjectUrl();
    activeObjectUrl = URL.createObjectURL(blob);
    activeAudio = new Audio(activeObjectUrl);
    return wireAudioElement(region, activeAudio);
  }

  function requestOpenAISpeech(plainText, voiceName) {
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
        return res.json().catch(function () { return {}; }).then(function (data) {
          throw new Error((data && data.error) || 'Could not generate speech.');
        });
      }
      return res.blob();
    });
  }

  function playTtsForRegion(region, plainText) {
    var voiceSelect = region.querySelector('[data-speech-voice]');
    var selectedOpenAIVoice = voiceSelect && voiceSelect.value;

    if (openaiEnabled) {
      return requestOpenAISpeech(plainText, selectedOpenAIVoice)
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
          finishPlayback(region, err && err.message ? err.message : 'Could not generate speech.');
        });
    }

    if (browserTtsSupported) {
      speakWithBrowser(region, plainText);
      return;
    }
    finishPlayback(region, 'Text-to-speech is not available.');
  }

  function handleSpeakClick(region) {
    if (!region) return;
    var fileUrl = willPlayRecording(region) ? prerecordedAudioUrl(region) : '';
    var plainText = speechPlainText(region);
    if (!fileUrl && !plainText) return;

    stopSpeech();
    activeRegion = region;
    setPlaybackState(region, true);

    if (fileUrl) {
      playRecordedUrl(region, fileUrl).catch(function () {
        if (plainText) {
          region.setAttribute('data-speech-use-tts', '1');
          updateRegion(region);
          var status = region.querySelector('[data-speech-status]');
          if (status) status.textContent = 'Recording unavailable. Using AI voice instead.';
          playTtsForRegion(region, plainText);
        } else {
          finishPlayback(region, 'Recording unavailable.');
        }
      });
      return;
    }

    playTtsForRegion(region, plainText);
  }

  function bindRegion(region) {
    ensureSpeechModeUi(region);
    updateRegion(region);

    var voiceSelect = region.querySelector('[data-speech-voice]');
    if (voiceSelect) {
      populateVoiceSelect(voiceSelect);
      voiceSelect.addEventListener('change', function () {
        if (openaiEnabled) setStoredVoice(openaiVoiceKey, voiceSelect.value);
        else setStoredVoice(browserVoiceKey, voiceSelect.value);
      });
    }

    var speakButton = region.querySelector('[data-speech-speak]');
    var stopButton = region.querySelector('[data-speech-stop]');
    if (speakButton) {
      speakButton.addEventListener('click', function (event) {
        event.preventDefault();
        handleSpeakClick(region);
      });
    }
    if (stopButton) {
      stopButton.addEventListener('click', function (event) {
        event.preventDefault();
        stopSpeech();
      });
    }
  }

  window.SomaSpeechRefresh = function (el) {
    var region = el && el.closest ? el.closest('[data-speech-region]') : null;
    if (region) updateRegion(region);
  };

  function boot() {
    document.querySelectorAll('[data-speech-region]').forEach(bindRegion);
    initBrowserVoicesOnce();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();