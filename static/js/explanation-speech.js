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
  var activeHighlight = null;
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

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function speechHighlightRoot(region) {
    if (!region) return null;
    var marked = region.querySelector('[data-speech-highlight]');
    if (marked) return marked;
    var text = region.querySelector('[data-speech-text]');
    if (text && !text.classList.contains('sr-only') && !text.hidden) return text;
    var card = region.closest('.demo-question-card, .question-card');
    if (card) {
      var visible = card.querySelector('.demo-q-text, .question-rich-text, .question-text');
      if (visible) return visible;
    }
    return null;
  }

  function canHighlightElement(el) {
    if (!el || el.classList.contains('sr-only')) return false;
    if (el.querySelector('.katex, .katex-display, img, table, figure')) return false;
    return el.children.length === 0;
  }

  function buildWordOffsets(plainText) {
    var offsets = [];
    var re = /\S+/g;
    var match;
    while ((match = re.exec(plainText))) {
      offsets.push({ start: match.index, index: offsets.length });
    }
    return offsets;
  }

  function clearSpeechHighlight() {
    if (!activeHighlight) return;
    if (activeHighlight.onTimeUpdate && activeHighlight.audio) {
      activeHighlight.audio.removeEventListener('timeupdate', activeHighlight.onTimeUpdate);
      activeHighlight.audio.removeEventListener('loadedmetadata', activeHighlight.onTimeUpdate);
    }
    if (activeHighlight.root) {
      activeHighlight.root.classList.remove('speech-readalong');
      if (activeHighlight.savedHtml !== null && activeHighlight.savedHtml !== undefined) {
        activeHighlight.root.innerHTML = activeHighlight.savedHtml;
      }
    }
    activeHighlight = null;
  }

  function setActiveHighlightWord(wordIndex) {
    if (!activeHighlight || !activeHighlight.root) return;
    var spans = activeHighlight.root.querySelectorAll('.speech-word');
    for (var i = 0; i < spans.length; i++) {
      spans[i].classList.toggle('speech-word--active', i === wordIndex);
      spans[i].classList.toggle('speech-word--past', i < wordIndex);
    }
    var active = spans[wordIndex];
    if (active && typeof active.scrollIntoView === 'function') {
      active.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
    }
  }

  function wordIndexForChar(offsets, charIndex) {
    var found = 0;
    for (var i = 0; i < offsets.length; i++) {
      if (charIndex >= offsets[i].start) found = offsets[i].index;
      else break;
    }
    return found;
  }

  function beginSpeechHighlight(region, plainText) {
    clearSpeechHighlight();
    if (!plainText) plainText = speechPlainText(region);
    if (!plainText) return null;
    var root = speechHighlightRoot(region);
    if (!root || !canHighlightElement(root)) return null;

    var savedHtml = root.innerHTML;
    var words = plainText.match(/\S+/g) || [];
    if (!words.length) return null;

    root.innerHTML = words.map(function (word, index) {
      return '<span class="speech-word" data-speech-word="' + index + '">' + escapeHtml(word) + '</span>';
    }).join(' ');
    root.classList.add('speech-readalong');

    activeHighlight = {
      root: root,
      words: words,
      offsets: buildWordOffsets(plainText),
      savedHtml: savedHtml,
      audio: null,
      onTimeUpdate: null,
    };
    return activeHighlight;
  }

  function attachAudioHighlight(audioEl) {
    if (!activeHighlight || !audioEl) return;
    activeHighlight.audio = audioEl;
    function syncFromTime() {
      if (!activeHighlight) return;
      if (!audioEl.duration || !isFinite(audioEl.duration)) return;
      var ratio = Math.min(1, Math.max(0, audioEl.currentTime / audioEl.duration));
      var idx = Math.min(
        activeHighlight.words.length - 1,
        Math.floor(ratio * activeHighlight.words.length)
      );
      setActiveHighlightWord(idx);
    }
    activeHighlight.onTimeUpdate = syncFromTime;
    audioEl.addEventListener('timeupdate', syncFromTime);
    audioEl.addEventListener('loadedmetadata', syncFromTime);
    syncFromTime();
  }

  function speechPlainTextForHighlight(region) {
    var text = speechPlainText(region);
    if (text) return text;
    var root = speechHighlightRoot(region);
    if (!root) return '';
    return (root.textContent || '').replace(/\s+/g, ' ').trim();
  }

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

  function finishPlayback(region, statusMessage) {
    clearSpeechHighlight();
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

  function stopSpeech(options) {
    var silent = options && options.silent;
    var exceptAudio = options && options.exceptAudio;

    pauseOtherAudioElements(exceptAudio);

    if (activeAudio && activeAudio !== exceptAudio) {
      activeAudio.pause();
      activeAudio.onended = null;
      activeAudio.onerror = null;
      activeAudio = null;
    }
    revokeObjectUrl();
    if (browserTtsSupported) window.speechSynthesis.cancel();
    if (activeRegion) {
      finishPlayback(activeRegion, silent ? '' : 'Speech stopped.');
    } else if (!exceptAudio) {
      clearSpeechHighlight();
    }
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
    return audioEl.play().then(function () {
      pauseOtherAudioElements(audioEl);
      beginSpeechHighlight(region, speechPlainTextForHighlight(region));
      attachAudioHighlight(audioEl);
    });
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
    beginSpeechHighlight(region, plainText);
    var utterance = new SpeechSynthesisUtterance(plainText);
    var voiceSelect = region.querySelector('[data-speech-voice]');
    var selectedVoice = voiceSelect && browserVoices.find(function (voice) {
      return voice.voiceURI === voiceSelect.value;
    });
    if (selectedVoice) utterance.voice = selectedVoice;
    utterance.lang = (selectedVoice && selectedVoice.lang) || document.documentElement.lang || 'en';
    utterance.onboundary = function (ev) {
      if (!activeHighlight || ev.charIndex === undefined) return;
      if (ev.name && ev.name !== 'word') return;
      setActiveHighlightWord(wordIndexForChar(activeHighlight.offsets, ev.charIndex));
    };
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

    stopSpeech({ silent: true });
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

  function bindInlineAudioPlayers() {
    document.querySelectorAll('audio').forEach(function (audioEl) {
      if (audioEl.dataset.somaExclusiveAudio === '1') return;
      audioEl.dataset.somaExclusiveAudio = '1';
      audioEl.addEventListener('play', function () {
        stopSpeech({ silent: true, exceptAudio: audioEl });
        pauseOtherAudioElements(audioEl);
      });
    });
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
    bindInlineAudioPlayers();
  };

  window.SomaStopAllAudio = function (options) {
    stopSpeech(options || { silent: true });
    pauseOtherAudioElements(options && options.exceptAudio);
  };

  function boot() {
    document.querySelectorAll('[data-speech-region]').forEach(bindRegion);
    bindInlineAudioPlayers();
    initBrowserVoicesOnce();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();