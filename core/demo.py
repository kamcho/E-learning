"""Session-based practice exam for anonymous visitors."""

import hashlib
import uuid as uuid_lib

from django.db.models import Count, Prefetch, Q
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from core.models import Option, Question
from core.scoring import _grade_choice, question_max_marks

DEMO_SESSION_KEY = 'practice_demo'
DEMO_QUESTION_COUNT_MIN = 1
DEMO_QUESTION_COUNT_MAX = 30
GUEST_FREE_QUESTION_COUNT = 4
PRACTICE_DEMO_PAYWALL_SESSION_KEY = 'practice_demo_paywall_reached'
PRACTICE_DEMO_FREE_ATTEMPT_CONSUMED_KEY = 'practice_demo_free_attempt_consumed'
PRACTICE_DEMO_RESUME_NOTICE_KEY = 'practice_demo_resume_notice'
# Backward-compatible label for templates that expect a single number (upper bound).
DEMO_QUESTION_COUNT = DEMO_QUESTION_COUNT_MAX
# Guest practice exam supports option-based items only (demo take UI).
DEMO_QUIZ_TYPES = ('Multiple Choice', 'True or False')


def get_demo_session(request):
    return request.session.get(DEMO_SESSION_KEY)


def save_demo_session(request, demo):
    previous = request.session.get(DEMO_SESSION_KEY)
    is_guest = not getattr(getattr(request, 'user', None), 'is_authenticated', False)
    if (
        previous
        and previous.get('demo_id') != demo.get('demo_id')
        and not previous.get('completed')
    ):
        persist_demo_attempt(previous, status='abandoned')
    request.session[DEMO_SESSION_KEY] = demo
    request.session.modified = True
    if is_guest:
        persist_demo_attempt(demo)


def clear_demo_session(request):
    demo = request.session.get(DEMO_SESSION_KEY)
    is_guest = not getattr(getattr(request, 'user', None), 'is_authenticated', False)
    if demo and is_guest:
        if not demo.get('completed'):
            persist_demo_attempt(demo, status='abandoned')
    if DEMO_SESSION_KEY in request.session:
        del request.session[DEMO_SESSION_KEY]
        request.session.modified = True
    clear_practice_demo_paywall(request)


def persist_demo_attempt(demo, *, status=None):
    """Copy guest progress from the active session into its durable audit row."""
    from core.models import GuestDemoAttempt

    demo_id = demo.get('demo_id')
    if not demo_id:
        return
    is_completed = bool(demo.get('completed'))
    started_at = parse_datetime(demo.get('started_at', '')) or timezone.now()
    defaults = {
        'grade_name': demo.get('grade_name', ''),
        'subject_name': demo.get('subject_name', ''),
        'scope_label': demo.get('scope_label', ''),
        'topic_label': demo.get('topic_label', ''),
        'question_ids': demo.get('question_ids', []),
        'answers': demo.get('answers', {}),
        'feedback': demo.get('feedback', {}),
        'question_count': len(demo.get('question_ids', [])),
        'correct_count': demo.get('correct_count', 0),
        'marks_earned': demo.get('marks_earned', 0),
        'marks_possible': demo.get('marks_possible', 0),
        'score': demo.get('score', 0),
        'status': status or (
            GuestDemoAttempt.Status.COMPLETED if is_completed
            else GuestDemoAttempt.Status.IN_PROGRESS
        ),
        'completed_at': timezone.now() if is_completed else None,
    }
    GuestDemoAttempt.objects.update_or_create(
        demo_id=demo_id,
        defaults={**defaults, 'started_at': started_at},
    )


def _demo_question_scope_q(*, subject, scope, strand=None, sub_strand=None):
    """Questions tied to the curriculum subject or present on active subject quizzes."""
    if scope == 'strand' and strand:
        return (
            Q(sub_strand__strand=strand)
            | Q(
                quizzes__is_active=True,
                quizzes__subject=subject,
                quizzes__strand=strand,
            )
        )
    if scope == 'sub_strand' and sub_strand:
        return (
            Q(sub_strand=sub_strand)
            | Q(
                quizzes__is_active=True,
                quizzes__subject=subject,
                quizzes__sub_strand=sub_strand,
            )
        )
    return (
        Q(sub_strand__strand__subject=subject)
        | Q(quizzes__is_active=True, quizzes__subject=subject)
    )


def select_demo_questions(
    *,
    subject,
    scope,
    strand=None,
    sub_strand=None,
    min_count=DEMO_QUESTION_COUNT_MIN,
    max_count=DEMO_QUESTION_COUNT_MAX,
):
    """Pick up to max_count gradable option questions, or all when fewer are available."""
    qs = (
        Question.objects.filter(
            is_active=True,
            quiz_type__in=DEMO_QUIZ_TYPES,
        )
        .filter(_demo_question_scope_q(
            subject=subject,
            scope=scope,
            strand=strand,
            sub_strand=sub_strand,
        ))
        .distinct()
        .select_related(
            'sub_strand',
            'sub_strand__strand',
            'sub_strand__strand__subject',
            'sub_strand__strand__subject__grade_level',
        )
        .annotate(
            active_option_count=Count(
                'options', filter=Q(options__is_active=True), distinct=True,
            ),
            correct_option_count=Count(
                'options',
                filter=Q(options__is_active=True, options__is_correct=True),
                distinct=True,
            ),
        )
        .filter(active_option_count__gte=2, correct_option_count__gte=1)
    )

    pool_count = qs.count()
    if pool_count < min_count:
        return []

    sample_size = min(max_count, pool_count)
    return list(
        qs.order_by('?')[:sample_size].prefetch_related(Prefetch(
            'options',
            queryset=Option.objects.filter(is_active=True).order_by('created_at'),
            to_attr='active_options',
        ))
    )


def guest_demo_requires_payment(demo, *, answered_count=None):
    """Require payment only to continue beyond the free question allowance."""
    total_questions = len(demo.get('question_ids') or [])
    if answered_count is None:
        answered_count = len(demo.get('answers') or {})
    return (
        total_questions > GUEST_FREE_QUESTION_COUNT
        and answered_count >= GUEST_FREE_QUESTION_COUNT
    )


def start_demo_session(
    *,
    grade,
    subject,
    scope,
    strand=None,
    sub_strand=None,
    questions,
):
    from core.presentation import demo_questions_presentation_order

    demo_id = str(uuid_lib.uuid4())
    questions = demo_questions_presentation_order(demo_id, list(questions))
    question_ids = [str(question.uuid) for question in questions]
    scope_label = {
        'general': 'Whole subject',
        'strand': 'Strand focus',
        'sub_strand': 'Sub-strand focus',
    }.get(scope, scope)

    return {
        'demo_id': demo_id,
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
        .select_related('sub_strand__strand__subject__grade_level')
        .prefetch_related(Prefetch(
            'options',
            queryset=Option.objects.filter(is_active=True).order_by('created_at'),
            to_attr='active_options',
        ))
    )
    order = {qid: index for index, qid in enumerate(ids)}
    questions.sort(key=lambda q: order.get(str(q.uuid), 999))
    return questions


def grade_demo_answer(question, option_uuid):
    from core.presentation import active_options_for_question

    options = active_options_for_question(question)
    selected = next((option for option in options if str(option.uuid) == str(option_uuid)), None)
    marks_awarded, is_correct = _grade_choice(question, selected)
    max_marks = question_max_marks(question)
    correct_option = next((option for option in options if option.is_correct), None)
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
        from core.presentation import options_for_demo

        for opt in options_for_demo(demo.get('demo_id', ''), question):
            options_list.append({
                'uuid': str(opt.uuid),
                'option': opt.option,
                'is_correct': opt.is_correct,
                'is_selected': str(opt.uuid) == answer_uuid,
            })
        explanation_audio_url = ''
        if question.explanation_audio:
            explanation_audio_url = question.explanation_audio.url

        rows.append({
            'number': index,
            'question': question,
            'question_uuid': qid,
            'question_text': question.quiz,
            'explanation_audio_url': explanation_audio_url,
            'options': options_list,
            'is_correct': fb.get('is_correct'),
            'answered': bool(answer_uuid),
            'marks_awarded': fb.get('marks_awarded', 0),
            'max_marks': fb.get('max_marks', question_max_marks(question)),
            'selected_text': fb.get('selected_text', '—'),
            'correct_text': fb.get('correct_text', ''),
        })
    return rows


def guest_demo_payment_succeeded(request, demo):
    from subscriptions.models import GuestDemoPayment

    token = request.session.get('guest_demo_payment_token')
    if not token or not demo:
        return False

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return GuestDemoPayment.objects.filter(
        session_token_hash=token_hash,
        demo_id=demo.get('demo_id', ''),
        status=GuestDemoPayment.Status.SUCCESS,
    ).exists()


def user_has_paid_practice_demo_access(request, demo=None):
    """Unlimited practice for this session (subscription or successful M-Pesa for this demo)."""
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        from subscriptions.services import user_can_start_exam

        if user_can_start_exam(user):
            return True
    demo = demo or get_demo_session(request)
    if demo:
        return guest_demo_payment_succeeded(request, demo)
    return False


def practice_demo_needs_payment(request, demo, *, answered_count=None):
    if user_has_paid_practice_demo_access(request, demo):
        return False
    return guest_demo_requires_payment(demo, answered_count=answered_count)


def mark_free_practice_attempt_used(request):
    """One free practice test per browser session without a subscription."""
    if user_has_paid_practice_demo_access(request):
        return
    request.session[PRACTICE_DEMO_FREE_ATTEMPT_CONSUMED_KEY] = True
    request.session.modified = True


def free_practice_attempt_consumed(request):
    if user_has_paid_practice_demo_access(request):
        return False
    return bool(request.session.get(PRACTICE_DEMO_FREE_ATTEMPT_CONSUMED_KEY))


def mark_practice_demo_paywall(request):
    request.session[PRACTICE_DEMO_PAYWALL_SESSION_KEY] = True
    request.session.modified = True
    mark_free_practice_attempt_used(request)


def practice_demo_paywall_reached(request):
    return bool(request.session.get(PRACTICE_DEMO_PAYWALL_SESSION_KEY))


def clear_practice_demo_paywall(request):
    if PRACTICE_DEMO_PAYWALL_SESSION_KEY in request.session:
        del request.session[PRACTICE_DEMO_PAYWALL_SESSION_KEY]
        request.session.modified = True


def describe_practice_exam(demo):
    """Human label for an in-progress practice session."""
    subject = (demo.get('subject_name') or '').strip() or 'Practice exam'
    topic = (demo.get('topic_label') or demo.get('scope_label') or '').strip()
    if topic:
        return f'{subject} ({topic})'
    return subject


def pop_practice_resume_notice(request):
    notice = request.session.pop(PRACTICE_DEMO_RESUME_NOTICE_KEY, None)
    if notice is not None:
        request.session.modified = True
    return notice


def redirect_if_blocked_practice_demo_start(request):
    """Return redirect if a new practice exam must not be started; else None."""
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse

    if user_has_paid_practice_demo_access(request):
        return None

    existing = get_demo_session(request)
    if existing and not existing.get('completed'):
        in_progress_label = describe_practice_exam(existing)
        requested_subject = ''
        subject_slug = (request.POST.get('subject') or '').strip()
        if subject_slug:
            from subjects.models import Subject

            requested_subject = (
                Subject.objects.filter(slug=subject_slug)
                .values_list('name', flat=True)
                .first()
                or subject_slug.replace('-', ' ').title()
            )
        existing_subject = (existing.get('subject_name') or '').strip()
        if (
            requested_subject
            and existing_subject
            and requested_subject.lower() != existing_subject.lower()
        ):
            messages.warning(
                request,
                f'You still have «{in_progress_label}» in progress. '
                f'We opened that exam instead of starting {requested_subject}. '
                f'Use «Start over» on the practice wizard when you want a fresh test.',
            )
        else:
            messages.warning(
                request,
                f'You still have «{in_progress_label}» in progress. '
                f'Continue where you left off, or use «Start over» on the practice wizard.',
            )
        request.session[PRACTICE_DEMO_RESUME_NOTICE_KEY] = {
            'in_progress_label': in_progress_label,
            'requested_subject': requested_subject,
            'wizard_restart_url': reverse('core:exam_wizard') + '?restart=1',
        }
        request.session.modified = True
        return redirect('core:exam_take')

    if practice_demo_paywall_reached(request):
        messages.warning(
            request,
            'You’ve used the free practice questions for this browser session. '
            'Pay for daily access to continue.',
        )
        if get_demo_session(request):
            return redirect('subscriptions:guest_demo_checkout')
        return redirect('core:exam_wizard')

    if free_practice_attempt_consumed(request):
        messages.warning(
            request,
            f'You’ve already taken your free practice test (up to {GUEST_FREE_QUESTION_COUNT} questions). '
            'Subscribe for unlimited retakes and full exams.',
        )
        return redirect('subscriptions:plans')

    existing = get_demo_session(request)
    if existing and existing.get('completed'):
        messages.warning(
            request,
            'Your free practice test is complete. Subscribe to take more exams and retakes.',
        )
        return redirect('subscriptions:plans')

    return None
