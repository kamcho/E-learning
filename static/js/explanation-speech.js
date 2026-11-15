(function () {
  'use strict';

  var openaiCfg = window.SomaOpenAITts;
  var openaiVoices = openaiCfg && Array.isArray(openaiCfg.voices) ? openaiCfg.voices : [];
  var openaiEnabled = !!(openaiCfg && openaiCfg.url);
  window.__somaSpeechRevealQueue = window.__somaSpeechRevealQueue || [];
  var browserTtsSupported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

  var openaiVoiceKey = 'soma-openai-tts-voice';
  var browserVoiceKey = 'soma-smart-explanation-voice';

  var activeRegion = null;
  var activeAudio = null;
  var activeObjectUrl = null;
  var activeHighlight = null;
  var activeFetchAbort = null;
  var browserVoices = [];
  var browserVoicesReady = false;
  var openaiRandomVoices = ['sage', 'marin'];

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
    if (!region) return '';

    function normalize(node) {
      if (!node) return '';
      return (node.textContent || '').replace(/\s+/g, ' ').trim();
    }

    var textEl = region.querySelector('[data-speech-text]');
    var fromSpeech = normalize(textEl);
    if (fromSpeech) return fromSpeech;

    var alt = region.querySelector('.ai-explanation-text, .demo-ai-text');
    if (alt) {
      var fromAlt = normalize(alt);
      if (fromAlt) return fromAlt;
    }

    var card = region.closest('.demo-question-card, .question-card');
    if (card) {
      var cardSpeech = normalize(card.querySelector('[data-speech-text]'));
      if (cardSpeech) return cardSpeech;
      var visible = card.querySelector('.demo-q-text, .question-rich-text, .question-text');
      if (visible) {
        var fromVisible = normalize(visible);
        if (fromVisible) return fromVisible;
      }
    }

    return '';
  }

  function insertTtsPauses(text) {
    if (!text) return text;
    return text
      .replace(/([.!?])(?!\d)\s+/g, '$1\n\n\n')
      .replace(/,\s*/g, ',\n\n')
      .replace(/[;:]\s*/g, function (match) {
        return match.trim() + '\n';
      })
      .replace(/\n{4,}/g, '\n\n\n')
      .trim();
  }

  function speechControlsRoot(region) {
    return region.querySelector('.explanation-speech-controls') || region;
  }

  function pickRandomOpenAIVoice() {
    var choices = openaiRandomVoices.filter(function (name) {
      return !openaiVoices.length || openaiVoices.indexOf(name) !== -1;
    });
    if (!choices.length) {
      return openaiCfg && openaiCfg.defaultVoice ? openaiCfg.defaultVoice : 'sage';
    }
    return choices[Math.floor(Math.random() * choices.length)];
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

  function observeSpeechTextChanges(region) {
    var targets = region.querySelectorAll('[data-speech-text], .ai-explanation-text, .demo-ai-text');
    if (!targets.length) return;
    targets.forEach(function (el) {
      if (el.dataset.somaSpeechObserve === '1') return;
      el.dataset.somaSpeechObserve = '1';
      var observer = new MutationObserver(function () {
        updateRegion(region);
      });
      observer.observe(el, { childList: true, characterData: true, subtree: true });
    });
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

  function setButtonLoading(region, loading) {
    var speakButton = region && region.querySelector('[data-speech-speak]');
    if (!region || !speakButton) return;
    if (loading) {
      region.dataset.speechLoading = '1';
      speakButton.textContent = speakButton.getAttribute('data-label-loading') || 'Loading…';
      speakButton.classList.add('is-loading');
      speakButton.classList.remove('is-speaking');
      speakButton.setAttribute('aria-busy', 'true');
      speakButton.setAttribute('aria-pressed', 'false');
    } else {
      region.dataset.speechLoading = '';
      speakButton.classList.remove('is-loading');
      speakButton.removeAttribute('aria-busy');
    }
  }

  function restoreListenButtonLabel(region, speakButton) {
    if (!speakButton || !region) return;
    if (region.dataset.speechPlaying === '1' || region.dataset.speechLoading === '1') return;
    if (!speakButton.getAttribute('data-default-label')) {
      speakButton.setAttribute('data-default-label', (speakButton.textContent || '').trim());
    }
    var useRecording = willPlayRecording(region);
    var labelRecorded = speakButton.getAttribute('data-label-recorded') || 'Play recording';
    var labelTts = speakButton.getAttribute('data-default-label') || 'Listen with AI';
    speakButton.textContent = useRecording ? labelRecorded : labelTts;
    speakButton.setAttribute('aria-pressed', 'false');
    speakButton.classList.remove('is-speaking');
    speakButton.disabled = false;
  }

  function setTogglePlaybackUi(region, playing) {
    if (!region) return;
    region.dataset.speechPlaying = playing ? '1' : '';
    var speakButton = region.querySelector('[data-speech-speak]');
    if (!speakButton) return;
    speakButton.disabled = false;
    if (playing) {
      speakButton.textContent = speakButton.getAttribute('data-label-stop') || 'Stop speaking';
      speakButton.setAttribute('aria-pressed', 'true');
      speakButton.classList.add('is-speaking');
    } else {
      restoreListenButtonLabel(region, speakButton);
    }
  }

  function isRegionSpeechActive(region) {
    return !!region && activeRegion === region && (
      region.dataset.speechPlaying === '1' || region.dataset.speechLoading === '1'
    );
  }

  function finishPlayback(region, statusMessage) {
    clearSpeechHighlight();
    if (!region) return;
    setButtonLoading(region, false);
    setTogglePlaybackUi(region, false);
    if (activeRegion === region) activeRegion = null;
  }

  function markPlaybackStarted(region) {
    if (!region) return;
    setButtonLoading(region, false);
    setTogglePlaybackUi(region, true);
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

    if (activeFetchAbort) {
      activeFetchAbort.abort();
      activeFetchAbort = null;
    }

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
    return audioEl.play().then(function () {
      pauseOtherAudioElements(audioEl);
      markPlaybackStarted(region);
      beginSpeechHighlight(region, speechPlainTextForHighlight(region));
      attachAudioHighlight(audioEl);
    }).catch(function () {
      finishPlayback(region, 'Could not play audio.');
      activeAudio = null;
      revokeObjectUrl();
    });
  }

  function playRecordedUrl(region, url) {
    revokeObjectUrl();
    activeAudio = new Audio(url);
    return wireAudioElement(region, activeAudio);
  }

  function updateRegion(region) {
    var speakButton = region.querySelector('[data-speech-speak]');
    var useRecording = willPlayRecording(region);
    var plainText = speechPlainText(region);
    var hasReadableText = !!plainText;
    var hasTtsEngine = openaiEnabled || browserTtsSupported;
    var canUseTts = hasReadableText && hasTtsEngine;
    var contentReady = region.dataset.speechContentReady === '1';
    var autoShow = region.getAttribute('data-speech-auto-show') === '1';
    var showButton = useRecording || (canUseTts && (contentReady || autoShow));
    var canSpeak = useRecording || canUseTts;

    setHidden(speakButton, !showButton);
    if (speakButton) {
      speakButton.disabled = !canSpeak;
      speakButton.setAttribute('aria-disabled', canSpeak ? 'false' : 'true');
    }

    if (useRecording) {
      region.classList.add('speech-region--recording');
      region.classList.remove('speech-region--tts');
    } else if (canUseTts) {
      region.classList.remove('speech-region--recording');
      region.classList.add('speech-region--tts');
    } else {
      region.classList.remove('speech-region--recording', 'speech-region--tts');
    }

    if (speakButton && region.dataset.speechPlaying !== '1' && region.dataset.speechLoading !== '1') {
      restoreListenButtonLabel(region, speakButton);
    }
  }

  function speakWithBrowser(region, plainText) {
    beginSpeechHighlight(region, plainText);
    var utterance = new SpeechSynthesisUtterance(insertTtsPauses(plainText));
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
    markPlaybackStarted(region);
    window.speechSynthesis.speak(utterance);
  }

  function playOpenAIAudio(region, blob) {
    revokeObjectUrl();
    activeObjectUrl = URL.createObjectURL(blob);
    activeAudio = new Audio(activeObjectUrl);
    return wireAudioElement(region, activeAudio);
  }

  function requestOpenAISpeech(plainText, voiceName, signal) {
    return fetch(openaiCfg.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': openaiCfg.csrfToken || '',
      },
      credentials: 'same-origin',
      signal: signal,
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
    if (openaiEnabled) {
      if (activeFetchAbort) activeFetchAbort.abort();
      activeFetchAbort = new AbortController();
      var signal = activeFetchAbort.signal;
      var voiceName = pickRandomOpenAIVoice();
      return requestOpenAISpeech(plainText, voiceName, signal)
        .then(function (blob) {
          activeFetchAbort = null;
          if (activeRegion !== region) return;
          return playOpenAIAudio(region, blob);
        })
        .catch(function (err) {
          activeFetchAbort = null;
          if (activeRegion !== region) return;
          if (err && err.name === 'AbortError') {
            finishPlayback(region, '');
            return;
          }
          if (browserTtsSupported) {
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

  function handleToggleSpeechClick(region) {
    if (!region) return;
    if (isRegionSpeechActive(region)) {
      stopSpeech();
      return;
    }

    var fileUrl = willPlayRecording(region) ? prerecordedAudioUrl(region) : '';
    var plainText = speechPlainText(region);
    if (!fileUrl && !plainText) return;

    stopSpeech({ silent: true });
    activeRegion = region;
    setButtonLoading(region, true);

    if (fileUrl) {
      playRecordedUrl(region, fileUrl).catch(function () {
        if (plainText) {
          region.setAttribute('data-speech-use-tts', '1');
          updateRegion(region);
          setButtonLoading(region, true);
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
    observeSpeechTextChanges(region);
    updateRegion(region);

    var speakButton = region.querySelector('[data-speech-speak]');
    if (speakButton) {
      speakButton.addEventListener('click', function (event) {
        event.preventDefault();
        handleToggleSpeechClick(region);
      });
    }
    var stopButton = region.querySelector('[data-speech-stop]');
    if (stopButton) setHidden(stopButton, true);
  }

  function revealSpeechListen(el) {
    if (!el) return;
    var region = el.closest ? el.closest('[data-speech-region]') : null;
    if (!region) return;

    if (el.matches && el.matches('[data-speech-text], .ai-explanation-text, .demo-ai-text')) {
      if (!el.classList.contains('demo-ai-error')) {
        el.hidden = false;
        el.removeAttribute('hidden');
      }
    }

    var text = speechPlainText(region);
    if (!text) return;

    region.dataset.speechContentReady = '1';
    observeSpeechTextChanges(region);
    updateRegion(region);

    var speakButton = region.querySelector('[data-speech-speak]');
    if (speakButton && speechPlainText(region)) {
      speakButton.hidden = false;
    }
  }

  window.SomaSpeechRevealListen = revealSpeechListen;

  window.SomaSpeechRefresh = function (el) {
    revealSpeechListen(el);
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
    (window.__somaSpeechRevealQueue || []).forEach(revealSpeechListen);
    window.__somaSpeechRevealQueue = [];
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();