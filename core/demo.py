"""Session-based practice demo for unregistered users (7 MC questions)."""

import random
import uuid as uuid_lib

from django.utils import timezone

from core.models import Question
from core.scoring import _grade_choice, question_max_marks

DEMO_SESSION_KEY = 'practice_demo'
DEMO_QUESTION_COUNT = 7


def get_demo_session(request):
    return request.session.get(DEMO_SESSION_KEY)


def save_demo_session(request, demo):
    request.session[DEMO_SESSION_KEY] = demo
    request.session.modified = True


def clear_demo_session(request):
    if DEMO_SESSION_KEY in request.session:
        del request.session[DEMO_SESSION_KEY]
        request.session.modified = True


def _valid_mc_question(question):
    options = list(question.options.filter(is_active=True))
    if len(options) < 2:
        return False
    return any(opt.is_correct for opt in options)


def select_demo_questions(*, subject, scope, strand=None, sub_strand=None, count=DEMO_QUESTION_COUNT):
    """Pick random multiple-choice questions for the demo test."""
    qs = (
        Question.objects.filter(
            is_active=True,
            quiz_type='Multiple Choice',
            sub_strand__strand__subject=subject,
        )
        .select_related(
            'sub_strand',
            'sub_strand__strand',
            'sub_strand__strand__subject',
            'sub_strand__strand__subject__grade_level',
        )
        .prefetch_related('options')
        .order_by('?')
    )

    if scope == 'strand' and strand:
        qs = qs.filter(sub_strand__strand=strand)
    elif scope == 'sub_strand' and sub_strand:
        qs = qs.filter(sub_strand=sub_strand)

    pool = [question for question in qs if _valid_mc_question(question)]
    if not pool:
        return []

    sample_size = min(count, len(pool))
    return random.sample(pool, sample_size)


def start_demo_session(
    *,
    grade,
    subject,
    scope,
    strand=None,
    sub_strand=None,
    questions,
):
    question_ids = [str(question.uuid) for question in questions]
    scope_label = {
        'general': 'Whole subject',
        'strand': 'Strand focus',
        'sub_strand': 'Sub-strand focus',
    }.get(scope, scope)

    return {
        'demo_id': str(uuid_lib.uuid4()),
        'started_at': timezone.now().isoformat(),
        'grade_slug': grade.slug,
        'grade_name': grade.name,
        'subject_slug': subject.slug,
        'subject_name': subject.name,
        'scope': scope,
        'scope_label': scope_label,
        'strand_slug': strand.slug if strand else '',
        'strand_name': strand.name if strand else '',
        'sub_strand_slug': sub_strand.slug if sub_strand else '',
        'sub_strand_name': sub_strand.name if sub_strand else '',
        'topic_label': (
            sub_strand.name if sub_strand
            else strand.name if strand
            else subject.name
        ),
        'question_ids': question_ids,
        'answers': {},
        'feedback': {},
        'feedback_index': None,
        'completed': False,
        'score': 0,
        'marks_earned': 0,
        'marks_possible': 0,
        'correct_count': 0,
    }


def load_demo_questions(demo):
    if not demo or not demo.get('question_ids'):
        return []
    ids = demo['question_ids']
    questions = list(
        Question.objects.filter(uuid__in=ids, is_active=True)
        .prefetch_related('options')
    )
    order = {qid: index for index, qid in enumerate(ids)}
    questions.sort(key=lambda q: order.get(str(q.uuid), 999))
    return questions


def grade_demo_answer(question, option_uuid):
    selected = question.options.filter(uuid=option_uuid, is_active=True).first()
    marks_awarded, is_correct = _grade_choice(question, selected)
    max_marks = question_max_marks(question)
    correct_option = question.options.filter(is_active=True, is_correct=True).first()
    return {
        'selected_option_uuid': str(option_uuid) if selected else '',
        'selected_text': selected.option if selected else '',
        'correct_text': correct_option.option if correct_option else '',
        'is_correct': is_correct,
        'marks_awarded': marks_awarded,
        'max_marks': max_marks,
    }


def finalize_demo(demo, questions):
    marks_earned = 0
    marks_possible = 0
    correct_count = 0
    for question in questions:
        max_marks = question_max_marks(question)
        marks_possible += max_marks
        fb = demo.get('feedback', {}).get(str(question.uuid))
        if fb:
            marks_earned += fb.get('marks_awarded', 0)
            if fb.get('is_correct'):
                correct_count += 1

    score = round((marks_earned / marks_possible) * 100) if marks_possible else 0
    demo['marks_earned'] = marks_earned
    demo['marks_possible'] = marks_possible
    demo['correct_count'] = correct_count
    demo['score'] = score
    demo['completed'] = True
    demo['feedback_index'] = None
    return demo


def build_demo_breakdown(demo, questions):
    rows = []
    for index, question in enumerate(questions, start=1):
        qid = str(question.uuid)
        fb = demo.get('feedback', {}).get(qid, {})
        answer_uuid = demo.get('answers', {}).get(qid, '')
        options_list = []
        for opt in question.options.filter(is_active=True).order_by('created_at'):
            options_list.append({
                'uuid': str(opt.uuid),
                'option': opt.option,
                'is_correct': opt.is_correct,
                'is_selected': str(opt.uuid) == answer_uuid,
            })
        rows.append({
            'number': index,
            'question': question,
            'question_uuid': qid,
            'question_text': question.quiz,
            'options': options_list,
            'is_correct': fb.get('is_correct'),
            'answered': bool(answer_uuid),
            'marks_awarded': fb.get('marks_awarded', 0),
            'max_marks': fb.get('max_marks', question_max_marks(question)),
            'selected_text': fb.get('selected_text', '—'),
            'correct_text': fb.get('correct_text', ''),
        })
    return rows
