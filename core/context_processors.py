"""Template context for app-wide features."""

from __future__ import annotations

import json

from django.conf import settings

from core.ai.tts import OPENAI_TTS_VOICES, default_tts_voice


def openai_tts(request):
    """Expose OpenAI read-aloud config when the API key is set."""
    if not getattr(settings, 'OPENAI_API_KEY', ''):
        return {'openai_tts_enabled': False}
    return {
        'openai_tts_enabled': True,
        'openai_tts_voices': json.dumps(list(OPENAI_TTS_VOICES)),
        'openai_tts_default_voice': default_tts_voice(),
    }