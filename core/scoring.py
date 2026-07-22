"""Per-question scoring and AttemptResponse helpers."""

from core.models import AttemptResponse


def parse_selected_option_ids(answer_str):
    """Parse a stored answer into a set of option UUID strings."""
    if not answer_str:
        return set()
    return {part.strip() for part in str(answer_str).split(',') if part.strip()}


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

    if question.quiz_type == 'Multiple Choice' and question_has_multiple_correct_answers(question):
        selected_ids = parse_selected_option_ids(answer_str)
        marks_awarded, is_correct = _grade_multiple_choice(question, selected_ids)
        text_answer = ','.join(sorted(selected_ids))
    elif question.quiz_type in ('Multiple Choice', 'True or False'):
        selected_option = question.options.filter(uuid=answer_str, is_active=True).first()
        marks_awarded, is_correct = _grade_choice(question, selected_option)
    else:
        text_answer = answer_str
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
            'graded_by': 'auto',
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
    questions = list(
        attempt.quiz.questions.filter(is_active=True).order_by('created_at')
    )
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
