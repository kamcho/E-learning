"""Per-question scoring and AttemptResponse helpers."""

import logging
import re
import uuid
from fractions import Fraction

from core.models import AttemptResponse

logger = logging.getLogger(__name__)

TEXT_QUIZ_TYPES = frozenset({'OpenEnded', 'Fill in the Blank', 'Matching'})


def parse_selected_option_ids(answer_str):
    """Parse a stored answer into a set of option UUID strings."""
    if not answer_str:
        return set()
    return {part.strip() for part in str(answer_str).split(',') if part.strip()}


def parse_option_uuid(answer_str):
    """Return a UUID when answer_str is a single option id, else None."""
    if not answer_str:
        return None
    try:
        return uuid.UUID(str(answer_str).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def question_has_multiple_correct_answers(question):
    """True when a multiple-choice question expects more than one selection."""
    if question.quiz_type != 'Multiple Choice':
        return False
    return question.options.filter(is_active=True, is_correct=True).count() > 1


def question_max_marks(question):
    """Return the marks available for a question (defaults to 1)."""
    return question.score if question.score > 0 else 1


def _grade_choice(question, selected_option):
    max_marks = question_max_marks(question)
    if not selected_option:
        return 0, False
    if selected_option.is_correct:
        return max_marks, True
    return 0, False


def _normalize_answer_text(text):
    """Lowercase, collapse whitespace, strip punctuation for loose matching."""
    raw = (text or '').strip().lower()
    raw = re.sub(r'[^\w\s./-]', '', raw)
    return ' '.join(raw.split())


def _question_context(question):
    grade_level = ''
    subject = ''
    try:
        subject_obj = question.sub_strand.strand.subject
        subject = subject_obj.name or ''
        if subject_obj.grade_level_id:
            grade_level = subject_obj.grade_level.name or ''
    except Exception:
        pass
    return grade_level, subject


def _reference_answers(question):
    return [
        str(text).strip()
        for text in question.options.filter(is_active=True, is_correct=True).values_list('option', flat=True)
        if text and str(text).strip()
    ]


_FRACTION_RE = re.compile(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)')
_DECIMAL_RE = re.compile(r'(?<!\d)(\d+\.\d+)(?!\d)')
_LATEX_FRAC_RE = re.compile(
    r'\\frac\s*\{\s*(\d+)\s*\}\s*\{\s*(\d+)\s*\}',
    re.IGNORECASE,
)


def _numeric_values_in_text(text):
    """Collect rational values mentioned in free text (fractions, decimals, whole numbers)."""
    values = set()
    blob = text or ''
    for pattern in (_FRACTION_RE, _LATEX_FRAC_RE):
        for match in pattern.finditer(blob):
            try:
                values.add(Fraction(int(match.group(1)), int(match.group(2))))
            except (ValueError, ZeroDivisionError):
                continue
    for match in _DECIMAL_RE.finditer(blob):
        try:
            values.add(Fraction(match.group(1)).limit_denominator(10_000))
        except ValueError:
            continue
    stripped = blob.strip()
    if re.fullmatch(r'\d+', stripped):
        values.add(Fraction(int(stripped), 1))
    return values


def _grade_fill_in_blank_exact(question, answer_str, max_marks):
    normalized = _normalize_answer_text(answer_str)
    if not normalized:
        return 0, False
    for ref in _reference_answers(question):
        ref_norm = _normalize_answer_text(ref)
        if ref_norm and ref_norm == normalized:
            return max_marks, True
    return None


def _grade_against_reference_answers(question, answer_str, max_marks):
    """
    Match learner text to model answers: exact text, or same numeric value (e.g. 3/4).
    """
    refs = _reference_answers(question)
    if not refs:
        return None

    normalized = _normalize_answer_text(answer_str)
    if not normalized:
        return 0, False

    learner_values = _numeric_values_in_text(answer_str)
    for ref in refs:
        ref_norm = _normalize_answer_text(ref)
        if ref_norm and ref_norm == normalized:
            return max_marks, True
        ref_values = _numeric_values_in_text(ref)
        if learner_values and ref_values and learner_values.intersection(ref_values):
            return max_marks, True

    return None


def _grade_with_ai(question, answer_str, max_marks):
    from core.ai import ai_service
    from core.ai.exceptions import AIConfigurationError, AIServiceError
    from core.ai.tasks.grade_open_answer import GRADE_OPEN_ANSWER_TASK

    if not ai_service.client.is_configured():
        raise AIConfigurationError('OpenAI is not configured.')

    grade_level, subject = _question_context(question)
    result = ai_service.run(
        GRADE_OPEN_ANSWER_TASK,
        question=question.quiz or '',
        learner_answer=answer_str,
        reference_answers=_reference_answers(question),
        max_marks=max_marks,
        grade_level=grade_level,
        subject=subject,
    )
    is_correct = bool(result.get('is_correct'))
    marks_awarded = max_marks if is_correct else 0
    return marks_awarded, is_correct, 'ai'


def _grade_matching_submission(question, answer_str, max_marks):
    from core.matching import parse_matching_pairs, parse_matching_submission

    correct_pairs = parse_matching_pairs(question)
    if len(correct_pairs) < 1:
        return None
    correct_map = {p['left']: p['right'] for p in correct_pairs}
    learner_map = parse_matching_submission(answer_str)
    if not learner_map:
        return None
    if set(learner_map.keys()) != set(correct_map.keys()):
        return 0, False, 'auto'
    for left, expected_right in correct_map.items():
        given = learner_map.get(left, '')
        if _normalize_answer_text(given) != _normalize_answer_text(expected_right):
            return 0, False, 'auto'
    return max_marks, True, 'auto'


def grade_text_question(question, answer_str):
    """
    Grade free-text answers (OpenEnded, Fill in the Blank, Matching).
    Returns (marks_awarded, is_correct, graded_by).
    """
    max_marks = question_max_marks(question)
    answer_str = (answer_str or '').strip()
    if not answer_str:
        return 0, False, 'auto'

    if question.quiz_type == 'Matching':
        structured = _grade_matching_submission(question, answer_str, max_marks)
        if structured is not None:
            return structured

    ref_match = _grade_against_reference_answers(question, answer_str, max_marks)
    if ref_match is not None:
        return ref_match[0], ref_match[1], 'auto'

    if question.quiz_type == 'Fill in the Blank':
        exact = _grade_fill_in_blank_exact(question, answer_str, max_marks)
        if exact is not None:
            return exact[0], exact[1], 'auto'

    try:
        return _grade_with_ai(question, answer_str, max_marks)
    except (AIConfigurationError, AIServiceError) as exc:
        logger.warning('AI text grading unavailable: %s', exc)
    except Exception:
        logger.exception('AI text grading failed for question %s', question.pk)

    fallback = _grade_fill_in_blank_exact(question, answer_str, max_marks)
    if fallback is not None:
        return fallback[0], fallback[1], 'auto'

    return 0, None, 'auto'


def ensure_text_responses_graded(attempt):
    """Re-grade any text responses that are still unmarked before finalizing."""
    updated = False
    for resp in attempt.responses.select_related('question').filter(text_answer__gt=''):
        question = resp.question
        if question.quiz_type not in TEXT_QUIZ_TYPES:
            continue
        if resp.is_correct is not None:
            continue
        marks_awarded, is_correct, graded_by = grade_text_question(question, resp.text_answer)
        if is_correct is None:
            continue
        resp.marks_awarded = marks_awarded
        resp.is_correct = is_correct
        resp.graded_by = graded_by
        resp.save(update_fields=['marks_awarded', 'is_correct', 'graded_by', 'updated_at'])
        updated = True
    return updated


def _grade_multiple_choice(question, selected_ids):
    """Grade select-all-that-apply questions with exact-set matching."""
    max_marks = question_max_marks(question)
    correct_ids = {
        str(option_id)
        for option_id in question.options.filter(
            is_active=True,
            is_correct=True,
        ).values_list('uuid', flat=True)
    }
    if not selected_ids or not correct_ids:
        return 0, False
    if selected_ids == correct_ids:
        return max_marks, True
    return 0, False


def upsert_response(attempt, question, answer_str):
    """Create or update the learner's response for one question."""
    answer_str = (answer_str or '').strip()
    max_marks = question_max_marks(question)
    selected_option = None
    text_answer = ''
    marks_awarded = 0
    is_correct = None
    graded_by = 'auto'

    if question.quiz_type == 'Multiple Choice' and question_has_multiple_correct_answers(question):
        selected_ids = parse_selected_option_ids(answer_str)
        marks_awarded, is_correct = _grade_multiple_choice(question, selected_ids)
        text_answer = ','.join(sorted(selected_ids))
    elif question.quiz_type in ('Multiple Choice', 'True or False'):
        option_uuid = parse_option_uuid(answer_str)
        if option_uuid is not None:
            selected_option = question.options.filter(uuid=option_uuid, is_active=True).first()
        marks_awarded, is_correct = _grade_choice(question, selected_option)
    elif question.quiz_type == 'Matching':
        option_uuid = parse_option_uuid(answer_str)
        if option_uuid is not None:
            selected_option = question.options.filter(uuid=option_uuid, is_active=True).first()
            if selected_option:
                marks_awarded, is_correct = _grade_choice(question, selected_option)
            else:
                text_answer = answer_str
                marks_awarded, is_correct, graded_by = grade_text_question(question, answer_str)
        else:
            text_answer = answer_str
            marks_awarded, is_correct, graded_by = grade_text_question(question, answer_str)
    else:
        text_answer = answer_str
        if question.quiz_type in TEXT_QUIZ_TYPES:
            marks_awarded, is_correct, graded_by = grade_text_question(question, answer_str)
        else:
            marks_awarded = 0
            is_correct = None

    response, _created = AttemptResponse.objects.update_or_create(
        attempt=attempt,
        question=question,
        defaults={
            'selected_option': selected_option,
            'text_answer': text_answer,
            'max_marks': max_marks,
            'marks_awarded': marks_awarded,
            'is_correct': is_correct,
            'graded_by': graded_by,
        },
    )
    return response


def responses_to_answers_dict(attempt):
    """Build the legacy answers JSON shape from stored responses."""
    answers = {}
    for resp in attempt.responses.select_related('selected_option').order_by('answered_at'):
        if resp.selected_option_id:
            answers[str(resp.question_id)] = str(resp.selected_option_id)
        elif resp.text_answer:
            answers[str(resp.question_id)] = resp.text_answer
    return answers


def clear_attempt_responses(attempt):
    """Remove all per-question responses for an attempt."""
    attempt.responses.all().delete()


def finalize_attempt(attempt):
    """
    Sum marks from responses and return score percentage plus summary counts.

    Unanswered questions count toward marks_possible with 0 marks earned.
    """
    from core.presentation import questions_for_attempt

    questions = questions_for_attempt(attempt, attempt.quiz)
    if not questions:
        return 0, 0, 0, 0, 0

    responses = {
        r.question_id: r
        for r in attempt.responses.select_related('selected_option', 'question')
    }

    marks_earned = 0
    marks_possible = 0
    correct_count = 0

    for question in questions:
        max_marks = question_max_marks(question)
        marks_possible += max_marks
        resp = responses.get(question.uuid)
        if resp:
            marks_earned += resp.marks_awarded or 0
            if resp.is_correct:
                correct_count += 1

    score = round((marks_earned / marks_possible) * 100) if marks_possible else 0
    return score, marks_earned, marks_possible, correct_count, len(questions)


def get_answered_count(attempt):
    return attempt.responses.count()


def build_quiz_peer_stats(quiz, attempt):
    """
    Compare a learner's completed attempt to other students on the same quiz.

    Returns peer average (excluding this learner) and percentile rank among all
    completed attempts using the standard (below + 0.5 * equal) / n formula.
    """
    from django.db.models import Avg

    from core.models import UserAttempts

    completed_qs = UserAttempts.objects.filter(
        quiz=quiz,
        is_active=True,
        is_complete=True,
    )
    peer_qs = completed_qs.exclude(student=attempt.student)

    peer_summary = peer_qs.aggregate(avg_score=Avg('score'))
    peer_avg = peer_summary['avg_score']
    peer_count = peer_qs.count()
    total_completed = completed_qs.count()

    percentile = None
    if attempt.is_complete and total_completed >= 2:
        scores = list(completed_qs.values_list('score', flat=True))
        below = sum(1 for score in scores if score < attempt.score)
        equal = sum(1 for score in scores if score == attempt.score)
        percentile = round((below + 0.5 * equal) / total_completed * 100, 1)

    return {
        'peer_avg_score': round(peer_avg, 1) if peer_avg is not None else None,
        'peer_count': peer_count,
        'total_completed': total_completed,
        'percentile': percentile,
    }


def sync_responses_from_answers(attempt, answers, questions):
    """Backfill AttemptResponse rows from legacy session/JSON answers."""
    if not answers:
        return
    for question in questions:
        answer = str(answers.get(str(question.uuid), '')).strip()
        if answer and not attempt.responses.filter(question=question).exists():
            upsert_response(attempt, question, answer)
