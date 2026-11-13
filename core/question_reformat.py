"""Apply AI math reformatting to stored questions."""

from django.db import transaction

from core.models import Option, Question


def question_option_payload(question):
    return [
        {
            'uuid': opt.uuid,
            'option': opt.option or '',
            'is_correct': opt.is_correct,
        }
        for opt in question.options.filter(is_active=True).order_by('created_at')
    ]


@transaction.atomic
def apply_question_math_reformat(question, *, quiz: str, options: list[dict]):
    """Persist reformatted stem and choice text; does not alter correctness flags."""
    quiz = (quiz or '').strip()
    if not quiz:
        raise ValueError('Question stem cannot be empty.')

    active = {
        str(opt.uuid): opt
        for opt in question.options.filter(is_active=True).order_by('created_at')
    }
    if set(active.keys()) != {str(item['uuid']) for item in options}:
        raise ValueError('Options do not match this question.')

    question.quiz = quiz
    question.save(update_fields=['quiz', 'updated_at'])

    for item in options:
        uid = str(item['uuid'])
        text = (item.get('option') or '').strip()
        opt = active[uid]
        if opt.option != text:
            opt.option = text
            opt.save(update_fields=['option', 'updated_at'])
