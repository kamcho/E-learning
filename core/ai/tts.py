"""OpenAI text-to-speech (streaming to memory only — not saved)."""

from __future__ import annotations

from django.conf import settings

from .exceptions import AIConfigurationError, AITaskError
from .tts_text import prepare_text_for_tts

OPENAI_TTS_VOICES = (
    'alloy',
    'ash',
    'coral',
    'echo',
    'fable',
    'marin',
    'nova',
    'onyx',
    'sage',
    'shimmer',
)


def default_tts_voice() -> str:
    voice = (getattr(settings, 'OPENAI_TTS_VOICE', '') or 'nova').strip().lower()
    return voice if voice in OPENAI_TTS_VOICES else 'nova'


def default_tts_model() -> str:
    return getattr(settings, 'OPENAI_TTS_MODEL', 'tts-1') or 'tts-1'


def synthesize_speech(text: str, *, voice: str | None = None) -> bytes:
    """Return MP3 bytes for the given text."""
    prepared = prepare_text_for_tts(text)
    if not prepared:
        raise AITaskError('Nothing to read aloud.')

    api_key = getattr(settings, 'OPENAI_API_KEY', '')
    if not api_key:
        raise AIConfigurationError(
            'OpenAI is not configured. Set the OPENAI_API_KEY environment variable.'
        )

    voice_name = (voice or default_tts_voice()).strip().lower()
    if voice_name not in OPENAI_TTS_VOICES:
        voice_name = default_tts_voice()
    model_name = default_tts_model()
    # `marin` is supported by gpt-4o-mini-tts, not legacy tts-1 models.
    if voice_name == 'marin' and model_name in ('tts-1', 'tts-1-hd'):
        model_name = 'gpt-4o-mini-tts'

    try:
        from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
    except ImportError as exc:
        raise AIConfigurationError(
            'The openai package is not installed. Run: pip install openai'
        ) from exc

    client = OpenAI(
        api_key=api_key,
        timeout=float(getattr(settings, 'OPENAI_TIMEOUT', 60)),
    )

    try:
        response = client.audio.speech.create(
            model=model_name,
            voice=voice_name,
            input=prepared,
            response_format='mp3',
        )
        return response.content
    except APITimeoutError as exc:
        raise AITaskError('Read-aloud took too long. Please try again.') from exc
    except APIConnectionError as exc:
        raise AITaskError('Could not reach OpenAI for read-aloud.') from exc
    except RateLimitError as exc:
        raise AITaskError('Read-aloud is busy. Please wait a moment.') from exc
    except Exception as exc:
        raise AITaskError(f'Read-aloud failed: {exc}') from exc
