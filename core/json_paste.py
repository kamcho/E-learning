"""Normalize JSON pasted from chat tools before parsing."""

import html
import json
import re


def normalize_json_paste(text):
    """
    Clean common AI/chat paste artifacts so json.loads can succeed.

    Handles markdown fences, HTML entities (e.g. &#x20;), UTF-8 BOM, and
    backslashes before line breaks (invalid in JSON but common in chat UIs).
    """
    if text is None:
        return ''
    text = str(text).strip().lstrip('\ufeff')
    text = html.unescape(text)
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```\s*$', '', text)
    text = re.sub(r'\\\s*\r?\n', '\n', text)
    # Chat tools often escape [ ] { } for markdown (e.g. "\["), which is invalid JSON.
    text = re.sub(r'\\([\[\]{}])', r'\1', text)
    return text.strip()


def parse_json_paste(text):
    """Return parsed object from pasted JSON text."""
    normalized = normalize_json_paste(text)
    return json.loads(normalized)
