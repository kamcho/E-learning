"""Prepare visible exam text for OpenAI speech (no persistence)."""

from __future__ import annotations

import html
import re

from django.conf import settings
from django.utils.html import strip_tags

_MAX_CHARS = 4096

# Newlines give OpenAI TTS short breath pauses; strength controls extra gaps.
_PAUSE_PROFILES = {
    'short': {
        'comma': ',\n',
        'sentence': '\n\n',
    },
    'medium': {
        'comma': ',\n\n',
        'sentence': '\n\n',
    },
    'long': {
        'comma': ',\n\n',
        'sentence': '\n\n\n',
    },
}


def tts_pause_profile() -> dict[str, str]:
    level = (getattr(settings, 'OPENAI_TTS_PAUSE_LEVEL', '') or 'long').strip().lower()
    return _PAUSE_PROFILES.get(level, _PAUSE_PROFILES['long'])


def insert_tts_pauses(text: str) -> str:
    """
    Insert pause cues after commas and sentence endings.

    OpenAI speech reads plain text; line breaks and short gaps improve rhythm.
    """
    if not text:
        return text

    profile = tts_pause_profile()
    comma_pause = profile['comma']
    sentence_pause = profile['sentence']

    # Sentence boundaries (. ! ?) — avoid "3.14" (decimal followed by digit).
    text = re.sub(r'(?<=[.!?])(?!\d)\s+', sentence_pause, text)
    text = re.sub(r',\s*', comma_pause, text)
    text = re.sub(r'[;:]\s*', lambda match: match.group(0).rstrip() + '\n', text)

    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()


def prepare_text_for_tts(raw: str) -> str:
    text = strip_tags(raw or '')
    text = html.unescape(text)
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\$+', '', text)
    text = insert_tts_pauses(text)
    if len(text) > _MAX_CHARS:
        text = text[: _MAX_CHARS - 3].rstrip() + '...'
    return text