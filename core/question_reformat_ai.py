"""Run AI reformat with deterministic fallback when the model fails."""

from core.ai import REFORMAT_QUESTION_MATH_TASK, ai_service
from core.ai.exceptions import AIServiceError
from core.question_reformat_sanitize import deterministic_reformat, sanitize_reformat_payload


def reformat_question_math_with_fallback(
    *,
    quiz: str,
    quiz_type: str,
    options: list[dict],
    grade_level: str = '',
    subject: str = '',
) -> dict:
    """
    Try OpenAI reformat; on failure use local fraction/LaTeX cleanup.
    Always sanitizes output (fixes \\f → form feed + rac bugs).
    """
    option_rows = [
        {
            'uuid': str(row['uuid']),
            'option': (row.get('option') or '').strip(),
            'is_correct': bool(row.get('is_correct', False)),
        }
        for row in options
    ]

    try:
        result = ai_service.run(
            REFORMAT_QUESTION_MATH_TASK,
            quiz=quiz,
            quiz_type=quiz_type,
            options=option_rows,
            grade_level=grade_level,
            subject=subject,
        )
        return {
            'quiz': result['quiz'],
            'options': result['options'],
            'used_ai': True,
            'used_fallback': False,
        }
    except (AIServiceError, ValueError):
        fallback = deterministic_reformat(quiz=quiz, options=option_rows)
        return {
            'quiz': fallback['quiz'],
            'options': fallback['options'],
            'used_ai': False,
            'used_fallback': True,
        }


def build_original_payload(quiz: str, options: list[dict]) -> dict:
    rows = []
    for row in options:
        rows.append({
            'uuid': str(row['uuid']),
            'option': (row.get('option') or '').strip(),
        })
    return {
        'quiz': quiz,
        'options': rows,
    }


def sanitize_manual_apply(*, quiz: str, options: list[dict]) -> dict:
    """When user saves from modal, re-sanitize in case of bad paste."""
    rows = [{'uuid': str(o['uuid']), 'option': o.get('option') or ''} for o in options]
    return sanitize_reformat_payload(quiz=quiz, options=rows)
