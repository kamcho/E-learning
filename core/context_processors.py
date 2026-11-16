"""Template context for app-wide features."""

from __future__ import annotations

import json

from django.conf import settings

from core.ai.tts import OPENAI_TTS_VOICES, default_tts_voice


def openai_tts(request):
    """Expose read-aloud endpoint for OpenAI generation and saved audio playback."""
    return {
        'openai_tts_enabled': bool(getattr(settings, 'OPENAI_API_KEY', '')),
        'openai_tts_voices': json.dumps(list(OPENAI_TTS_VOICES)),
        'openai_tts_default_voice': default_tts_voice(),
    }
