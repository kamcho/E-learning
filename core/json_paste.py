"""Normalize JSON pasted from chat tools before parsing."""

import html
import json
import re


def _normalize_smart_quotes(text):
    """WhatsApp, Word, and some AI UIs use curly quotes instead of JSON \" characters."""
    for char in ('\u201c', '\u201d', '\u201e', '\u2033', '\u00ab', '\u00bb'):
        text = text.replace(char, '"')
    # Apostrophe-style quotes inside strings
    text = text.replace('\u2018', "'").replace('\u2019', "'").replace('\u201a', "'")
    return text


_VALID_JSON_ESCAPE = re.compile(
    r'(?<!\\)\\(?!["\\/bfnrt]|u(?:[0-9a-fA-F]{4}))'
)


def _fix_invalid_json_escapes(text):
    """
    Double backslashes that are not valid JSON escapes (e.g. LaTeX \\(, \\_, \\times).
    """
    return _VALID_JSON_ESCAPE.sub(r'\\\\', text)


def normalize_json_paste(text):
    """
    Clean common AI/chat paste artifacts so json.loads can succeed.

    Handles markdown fences, HTML entities (e.g. &#x20;), UTF-8 BOM,
    smart/curly quotes, and backslashes before line breaks (common in chat UIs).
    """
    if text is None:
        return ''
    text = str(text).strip().lstrip('\ufeff')
    text = html.unescape(text)
    text = _normalize_smart_quotes(text)
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```\s*$', '', text)
    text = re.sub(r'\\\s*\r?\n', '\n', text)
    # Chat tools often escape [ ] { } for markdown (e.g. "\["), which is invalid JSON.
    text = re.sub(r'\\([\[\]{}])', r'\1', text)
    text = _fix_invalid_json_escapes(text)
    return text.strip()


def parse_json_paste(text):
    """Return parsed object from pasted JSON text."""
    normalized = normalize_json_paste(text)
    return json.loads(normalized)
