"""Shared database storage for reusable AI answer explanations."""

import hashlib
import json

from django.conf import settings

from core.ai.text_sanitize import sanitize_tutor_plaintext
from core.models import AIExplanation


def _audio_url(audio_field):
    if not audio_field:
        return ''
    url = audio_field.url
    if not url.startswith(('/', 'http://', 'https://')):
        url = f'/{url.lstrip("/")}'
    return url


def explanation_context(question, choices, selected_answer, *, grade_level='', subject=''):
    """Build the stable question/answer context used to share explanations globally."""
    snapshot = {
        'question_id': str(question.uuid),
        'question': question.quiz or '',
        'choices': choices,
        'selected_answer': selected_answer or '',
        'grade_level': grade_level or '',
        'subject': subject or '',
    }
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest(), snapshot


def explanation_response(record):
    selected_answer = record.prompt_snapshot.get('selected_answer', record.selected_answer)
    if record.selected_option_id:
        learner_was_correct = record.selected_option.is_correct
    elif selected_answer:
        correct_choices = {
            choice.get('text', '')
            for choice in record.prompt_snapshot.get('choices', [])
            if choice.get('is_correct')
        }
        learner_was_correct = selected_answer in correct_choices
    else:
        learner_was_correct = None
    return {
        'task': 'explain_answer',
        'explanation': sanitize_tutor_plaintext(record.explanation or ''),
        'correct_answer': record.correct_answer,
        'learner_was_correct': learner_was_correct,
        'explanation_uuid': str(record.uuid),
        'audio_available': bool(record.tts_audio),
        'tts_audio_url': _audio_url(record.tts_audio),
        'from_database': True,
    }


def save_shared_explanation(
    *, question, lookup_key, snapshot, selected_answer, selected_option=None, result,
):
    """Store one explanation per context; concurrent duplicate requests converge."""
    record, created = AIExplanation.objects.get_or_create(
        lookup_key=lookup_key,
        defaults={
            'question': question,
            'selected_option': selected_option,
            'selected_answer': selected_answer or '',
            'explanation': result.get('explanation', ''),
            'correct_answer': result.get('correct_answer', ''),
            'prompt_snapshot': snapshot,
            'model': getattr(settings, 'OPENAI_MODEL', ''),
        },
    )
    response = result.copy() if created else explanation_response(record)
    response['explanation_uuid'] = str(record.uuid)
    response['audio_available'] = bool(record.tts_audio)
    response['tts_audio_url'] = _audio_url(record.tts_audio)
    return response
