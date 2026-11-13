"""Sanitize AI reformat output and deterministic fallback (no OpenAI)."""

from core.question_math_normalize import finalize_math_display_text


def sanitize_reformat_payload(*, quiz: str, options: list[dict]) -> dict:
    quiz_out = finalize_math_display_text(quiz)
    options_out = []
    for row in options:
        options_out.append({
            'uuid': str(row['uuid']),
            'option': finalize_math_display_text(row.get('option') or ''),
        })
    return {'quiz': quiz_out, 'options': options_out}


def deterministic_reformat(*, quiz: str, options: list[dict]) -> dict:
    """Local math cleanup when AI is unavailable or returns bad LaTeX."""
    return sanitize_reformat_payload(quiz=quiz, options=options)
