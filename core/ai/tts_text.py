"""Prepare visible exam text for OpenAI speech (no persistence)."""

from __future__ import annotations

import html
import re

from django.utils.html import strip_tags

_MAX_CHARS = 4096


def prepare_text_for_tts(raw: str) -> str:
    text = strip_tags(raw or '')
    text = html.unescape(text)
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\$+', '', text)
    if len(text) > _MAX_CHARS:
        text = text[: _MAX_CHARS - 3].rstrip() + '...'
    return text