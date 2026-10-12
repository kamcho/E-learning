import json
from urllib.parse import quote

from django.db.models import Avg, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.http import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.ratelimit import rate_limit

from .models import Quiz, Question
from .scoring import (
    build_quiz_peer_stats,
    clear_attempt_responses,
    finalize_attempt,
    get_answered_count,
    parse_selected_option_ids,
    question_has_multiple_correct_answers,
    question_max_marks,
    responses_to_answers_dict,
    sync_responses_from_answers,
    upsert_response,
)
from .timing import attempt_has_timed_out, attempt_seconds_remaining, quiz_time_limit_seconds
from subjects.models import GradeLevel


def landing_page(request):
    """Render the Soma Smart CBC landing page."""
    from subscriptions.models import SubscriptionPlan
    from subscriptions.services import get_active_subscription

    active_subscription = None
    if request.user.is_authenticated:
        active_subscription = get_active_subscription(request.user)

    return render(request, 'core/landing.html', {
        'subscription_plans': SubscriptionPlan.objects.filter(is_active=True),
        'active_subscription': active_subscription,
    })


def privacy_policy_view(request):
    """Public privacy policy page (required for Google Sign-In / OAuth)."""
    from django.conf import settings

    return render(request, 'core/privacy_policy.html', {
        'privacy_contact_email': getattr(
            settings,
            'PRIVACY_CONTACT_EMAIL',
            'privacy@somasmartassesments.com',
        ),
        'site_name': 'Soma Smart',
        'policy_effective_date': '22 July 2026',
    })


def _resolve_next_url(next_param):
    """Return a safe redirect target from ?next= or fall back to exams list."""
    if next_param and next_param.startswith('/'):
        return next_param
    if next_param:
        return next_param
    return reverse('core:exams_list')


def _staff_exams_browse(user, selected_student):
    """Teachers/admins browse exams by grade/subject without a learner context."""
    if selected_student:
        return False
    return user.is_admin_role or user.is_staff or user.is_teacher


def _exams_browse_flow_active(selected_student, learner_grade_missing, staff_exams_browse):
    return (selected_student and not learner_grade_missing) or staff_exams_browse


def _can_access_learner(user, student):
    """Guardians may only access linked learners; admins may access any."""
    if user.is_admin_role or user.is_staff:
        return True
    if user.is_guardian:
        return user.linked_students.filter(students=student).exists()
    return False


def _get_learner_or_redirect(request, student_uuid):
    from accounts.models import Student

    student = get_object_or_404(Student.objects.select_related('grade_level'), uuid=student_uuid)
    if not _can_access_learner(request.user, student):
        messages.error(request, "You don't have permission to manage exams for this learner.")
        return None
    return student


def _celebrate_new_achievements(request, student):
    from achievements.services import evaluate_student_achievements

    for achievement in evaluate_student_achievements(student):
        messages.success(
            request,
            f"Achievement unlocked: {achievement.icon} {achievement.title}!",
        )


@login_required(login_url='accounts:signin')
def test_info_view(request, quiz_uuid, student_uuid):
    """
    Test info / lobby for a learner about to take a quiz.
    Each retake creates a NEW UserAttempts row instead of overwriting the old one,
    so the full attempt history is preserved.
    """
    from core.models import UserAttempts

    student = _get_learner_or_redirect(request, student_uuid)
    if not student:
        return redirect('core:exams_list')

    quiz = get_object_or_404(
        Quiz.objects.select_related('subject', 'subject__grade_level'),
        uuid=quiz_uuid,
        is_active=True,
    )

    from django.conf import settings as django_settings
    from subscriptions.models import SubscriptionPlan
    from subscriptions.services import (
        consume_test_credit,
        get_active_subscription,
        user_can_start_exam,
    )

    subscription_required = (
        django_settings.SUBSCRIPTION_REQUIRED and request.user.is_guardian
    )
    active_subscription = None
    can_start_exam = True
    single_test_plan = None
    if subscription_required:
        active_subscription = get_active_subscription(request.user)
        can_start_exam = user_can_start_exam(request.user)
        single_test_plan = SubscriptionPlan.objects.filter(
            slug='single-test', is_active=True,
        ).first()

    next_param = request.GET.get('next', '').strip()
    cancel_url = _resolve_next_url(next_param)
    if f'student={student.uuid}' not in cancel_url:
        sep = '&' if '?' in cancel_url else '?'
        cancel_url = f"{cancel_url}{sep}student={student.uuid}"

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'start':
            # The active attempt is the most recent one that isn't complete yet.
            active_attempt = (
                UserAttempts.objects
                .filter(student=student, quiz=quiz, is_active=True, is_complete=False)
                .order_by('-created_at')
                .first()
            )
            all_count = UserAttempts.objects.filter(student=student, quiz=quiz).count()

            if active_attempt:
                # Continue an in-progress attempt (same session or resumed from DB).
                attempt = active_attempt
                if not attempt.started_at:
                    attempt.started_at = attempt.created_at or timezone.now()
                    attempt.save(update_fields=['started_at'])
                messages.info(request, f"Continuing for {student.first_name}: {quiz.title}")
            else:
                if subscription_required and not can_start_exam:
                    messages.warning(
                        request,
                        'You need a test credit to start. Pay KES 10 for one test or choose a pack.',
                    )
                    plans_url = reverse('subscriptions:plans')
                    return redirect(f'{plans_url}?next={quote(request.get_full_path(), safe="")}')

                # Fresh start or retake — always create a NEW row.
                attempt = UserAttempts.objects.create(
                    student=student,
                    quiz=quiz,
                    user=request.user,
                    attempt_number=all_count + 1,
                    started_at=timezone.now(),
                    is_active=True,
                    is_complete=False,
                )
                clear_attempt_answers(request, attempt.uuid)

                if subscription_required:
                    try:
                        consume_test_credit(request.user, attempt)
                    except ValueError:
                        attempt.delete()
                        messages.error(
                            request,
                            'Could not start the exam — no test credits remaining.',
                        )
                        return redirect('subscriptions:plans')

                if all_count == 0:
                    messages.success(request, f"Test started for {student.first_name}: {quiz.title}")
                else:
                    messages.info(request, f"Retake #{attempt.attempt_number} started for {student.first_name}.")

            return redirect('core:test_take', quiz_uuid=quiz.uuid, student_uuid=student.uuid)

        messages.error(request, "Invalid action.")
        return redirect('core:test_info', quiz_uuid=quiz.uuid, student_uuid=student.uuid)

    # GET — show the info page.
    # "existing_attempt" for the template = current active (in-progress or most recent completed).
    existing_attempt = (
        UserAttempts.objects
        .filter(student=student, quiz=quiz, is_active=True)
        .order_by('is_complete', '-created_at')   # False(0) < True(1) → in-progress first
        .first()
    )
    # All completed attempts for the history table (most recent first).
    past_attempts = list(
        UserAttempts.objects
        .filter(student=student, quiz=quiz, is_complete=True)
        .order_by('-created_at')
    )

    question_count = quiz.test_size or quiz.questions.filter(is_active=True).count()

    if existing_attempt and not existing_attempt.is_complete:
        attempt_status = 'in_progress'
        can_start_exam = True
    elif past_attempts:
        attempt_status = 'completed'
    else:
        attempt_status = 'ready'

    needs_credit = (
        subscription_required
        and attempt_status != 'in_progress'
        and not can_start_exam
    )

    return render(
        request,
        'core/test_info.html',
        {
            'quiz': quiz,
            'student': student,
            'cancel_url': cancel_url,
            'existing_attempt': existing_attempt,
            'past_attempts': past_attempts,
            'attempt_status': attempt_status,
            'question_count': question_count,
            'active_subscription': active_subscription,
            'can_start_exam': can_start_exam,
            'needs_credit': needs_credit,
            'single_test_plan': single_test_plan,
            'subscription_required': subscription_required,
        },
    )


def _answers_session_key(attempt_uuid):
    return f'attempt_answers_{attempt_uuid}'


def clear_attempt_answers(request, attempt_uuid):
    key = _answers_session_key(attempt_uuid)
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _get_attempt_answers(request, attempt_uuid):
    return request.session.get(_answers_session_key(attempt_uuid), {})


def _save_attempt_answer(request, attempt_uuid, question_uuid, answer):
    key = _answers_session_key(attempt_uuid)
    answers = dict(request.session.get(key, {}))
    answers[str(question_uuid)] = answer.strip()
    request.session[key] = answers
    request.session.modified = True


def _sync_attempt_answers(attempt, request):
    """Mirror in-progress answers from session onto the attempt record."""
    session_answers = _get_attempt_answers(request, attempt.uuid)
    if session_answers:
        attempt.answers = session_answers
    else:
        attempt.answers = responses_to_answers_dict(attempt)
    attempt.save(update_fields=['answers', 'updated_at'])


def _load_attempt_answers(request, attempt):
    """
    Load in-progress answers for the current session.

    Always merges the authoritative DB state (AttemptResponse rows) on top of
    whatever is in the session so that a stale session from Device A correctly
    picks up answers that were submitted from Device B.
    """
    session_answers = _get_attempt_answers(request, attempt.uuid)

    if attempt.responses.exists():
        # DB responses are the ground truth — they were written on every POST.
        db_answers = responses_to_answers_dict(attempt)
        # Merge: session extras (typed but not yet saved) + DB (authoritative).
        # DB wins on overlap so cross-device progress is never lost.
        merged = {**session_answers, **db_answers}
        if merged != session_answers:
            request.session[_answers_session_key(attempt.uuid)] = merged
            request.session.modified = True
        return merged

    if session_answers:
        return session_answers

    # Last-resort fallback: legacy answers JSON field.
    if attempt.answers:
        request.session[_answers_session_key(attempt.uuid)] = dict(attempt.answers)
        request.session.modified = True
        return attempt.answers

    return {}


def _complete_attempt(request, attempt, student, quiz, saved_answers, take_url_kwargs, *, timed_out=False):
    score, marks_earned, marks_possible, correct, total = finalize_attempt(attempt)
    attempt.answers = saved_answers or responses_to_answers_dict(attempt)
    attempt.score = score
    attempt.marks_earned = marks_earned
    attempt.marks_possible = marks_possible
    attempt.is_complete = True
    attempt.save(update_fields=[
        'answers', 'score', 'marks_earned', 'marks_possible',
        'is_complete', 'updated_at',
    ])
    clear_attempt_answers(request, attempt.uuid)
    if timed_out:
        messages.warning(
            request,
            f"Time's up! {student.first_name}'s exam was submitted automatically "
            f"with a score of {score}% ({marks_earned}/{marks_possible} marks).",
        )
    else:
        messages.success(
            request,
            f"{student.first_name} scored {score}% "
            f"({marks_earned}/{marks_possible} marks, {correct}/{total} correct).",
        )
    _celebrate_new_achievements(request, student)
    return redirect('core:attempt_detail', **take_url_kwargs)


def _can_view_attempt(user, attempt):
    if user.is_admin_role or user.is_staff:
        return True
    if attempt.student_id:
        return _can_access_learner(user, attempt.student)
    return False


def _build_attempt_breakdown(attempt):
    """Build per-question rows for attempt detail."""
    responses = {
        str(r.question_id): r
        for r in attempt.responses.select_related('selected_option').order_by('answered_at')
    }
    questions = list(
        attempt.quiz.questions.filter(is_active=True).prefetch_related('options').order_by('created_at')
    )
    rows = []
    for index, question in enumerate(questions, start=1):
        response = responses.get(str(question.uuid))
        selected_ids = set()
        if response:
            if response.selected_option_id:
                selected_ids = {str(response.selected_option_id)}
            elif response.text_answer:
                if question.quiz_type == 'Multiple Choice':
                    selected_ids = parse_selected_option_ids(response.text_answer)
                else:
                    selected_ids = {response.text_answer}

        options_list = []
        for opt in question.options.filter(is_active=True).order_by('created_at'):
            options_list.append({
                'uuid': str(opt.uuid),
                'option': opt.option,
                'option_image_url': opt.option_image.url if opt.option_image else '',
                'is_correct': opt.is_correct,
                'is_selected': str(opt.uuid) in selected_ids,
            })

        row = {
            'number': index,
            'question': question,
            'question_uuid': str(question.uuid),
            'question_text': question.quiz,
            'answer_text': '—',
            'is_correct': response.is_correct if response else None,
            'answered': bool(response),
            'marks_awarded': response.marks_awarded if response else 0,
            'max_marks': response.max_marks if response else question_max_marks(question),
            'options': options_list,
            'quiz_type': question.quiz_type,
        }
        if question.quiz_type in ('Multiple Choice', 'True or False'):
            if selected_ids:
                selected_labels = [
                    opt.option
                    for opt in question.options.filter(uuid__in=selected_ids, is_active=True)
                ]
                row['answer_text'] = ', '.join(selected_labels) if selected_labels else '—'
            else:
                row['answer_text'] = '—'
        elif response and response.text_answer:
            row['answer_text'] = response.text_answer
        rows.append(row)

    correct_count = sum(1 for row in rows if row['is_correct'] is True)
    return rows, correct_count, len(questions)


@login_required(login_url='accounts:signin')
def test_take_view(request, quiz_uuid, student_uuid):
    """Learner takes a quiz one question at a time."""
    from core.models import UserAttempts

    student = _get_learner_or_redirect(request, student_uuid)
    if not student:
        return redirect('core:exams_list')

    quiz = get_object_or_404(
        Quiz.objects.select_related('subject', 'subject__grade_level'),
        uuid=quiz_uuid,
        is_active=True,
    )

    attempt = (
        UserAttempts.objects
        .filter(student=student, quiz=quiz, is_active=True, is_complete=False)
        .select_related('student', 'user')
        .order_by('-created_at')
        .first()
    )

    if not attempt:
        messages.info(request, "Start the exam before answering questions.")
        return redirect('core:test_info', quiz_uuid=quiz.uuid, student_uuid=student.uuid)

    if not _can_view_attempt(request.user, attempt):
        messages.error(request, "You don't have permission to take this exam.")
        return redirect('core:exams_list')

    questions = list(
        quiz.questions.filter(is_active=True).prefetch_related('options').order_by('created_at')
    )
    question_count = len(questions)

    if attempt.is_complete:
        clear_attempt_answers(request, attempt.uuid)
        return redirect(
            'core:attempt_detail',
            quiz_uuid=quiz.uuid,
            student_uuid=student.uuid,
        )

    saved_answers = _load_attempt_answers(request, attempt)
    sync_responses_from_answers(attempt, saved_answers, questions)
    current_index = get_answered_count(attempt)

    take_url_kwargs = {'quiz_uuid': quiz.uuid, 'student_uuid': student.uuid}
    time_remaining_seconds = attempt_seconds_remaining(attempt, quiz)
    has_time_limit = quiz_time_limit_seconds(quiz) > 0

    if attempt_has_timed_out(attempt, quiz):
        return _complete_attempt(
            request, attempt, student, quiz, saved_answers, take_url_kwargs, timed_out=True,
        )

    if request.method == 'POST':
        if request.POST.get('action') == 'time_up':
            return _complete_attempt(
                request, attempt, student, quiz, saved_answers, take_url_kwargs, timed_out=True,
            )

        if current_index >= question_count:
            return redirect('core:test_take', **take_url_kwargs)

        question = questions[current_index]
        if question_has_multiple_correct_answers(question):
            selected_answers = [
                value.strip()
                for value in request.POST.getlist('answer')
                if value.strip()
            ]
            if not selected_answers:
                messages.error(request, "Please select at least one answer.")
                return redirect('core:test_take', **take_url_kwargs)
            answer = ','.join(sorted(set(selected_answers)))
        else:
            answer = request.POST.get('answer', '').strip()
            if not answer:
                messages.error(request, "Please select or enter an answer.")
                return redirect('core:test_take', **take_url_kwargs)

        _save_attempt_answer(request, attempt.uuid, question.uuid, answer)
        upsert_response(attempt, question, answer)
        saved_answers = _get_attempt_answers(request, attempt.uuid)
        _sync_attempt_answers(attempt, request)

        if get_answered_count(attempt) >= question_count:
            return _complete_attempt(
                request, attempt, student, quiz, saved_answers, take_url_kwargs,
            )

        return redirect('core:test_take', **take_url_kwargs)

    if not questions:
        return render(
            request,
            'core/test_take.html',
            {
                'attempt': attempt,
                'quiz': quiz,
                'student': student,
                'question_count': 0,
                'no_questions': True,
            },
        )

    if current_index >= question_count:
        return _complete_attempt(
            request, attempt, student, quiz, saved_answers, take_url_kwargs,
        )

    current_question = questions[current_index]
    saved_answer = saved_answers.get(str(current_question.uuid), '')
    allows_multiple_answers = question_has_multiple_correct_answers(current_question)
    saved_answer_ids = (
        parse_selected_option_ids(saved_answer)
        if allows_multiple_answers else set()
    )
    progress_pct = int(((current_index + 1) / question_count) * 100)

    return render(
        request,
        'core/test_take.html',
        {
            'attempt': attempt,
            'quiz': quiz,
            'student': student,
            'question': current_question,
            'question_number': current_index + 1,
            'question_count': question_count,
            'saved_answer': saved_answer,
            'saved_answer_ids': saved_answer_ids,
            'allows_multiple_answers': allows_multiple_answers,
            'progress_pct': progress_pct,
            'is_last_question': current_index + 1 == question_count,
            'has_time_limit': has_time_limit,
            'time_remaining_seconds': time_remaining_seconds,
            'time_limit_minutes': quiz.time_limit_minutes,
        },
    )


@login_required(login_url='accounts:signin')
def attempt_detail_view(request, quiz_uuid, student_uuid):
    """
    View the most recent completed attempt for a student+quiz pair.
    For historical attempts use attempt_by_uuid_view.
    """
    from core.models import UserAttempts

    student = _get_learner_or_redirect(request, student_uuid)
    if not student:
        return redirect('core:exams_list')

    quiz = get_object_or_404(
        Quiz.objects.select_related('subject', 'subject__grade_level'),
        uuid=quiz_uuid,
        is_active=True,
    )

    # Most recent completed attempt for this student+quiz.
    attempt = (
        UserAttempts.objects
        .filter(student=student, quiz=quiz, is_active=True, is_complete=True)
        .select_related('student', 'user')
        .order_by('-created_at')
        .first()
    )
    if not attempt:
        messages.info(request, "No completed attempt found for this exam.")
        return redirect('core:test_info', quiz_uuid=quiz_uuid, student_uuid=student_uuid)

    if not _can_view_attempt(request.user, attempt):
        messages.error(request, "You don't have permission to view this attempt.")
        return redirect('core:exams_list')

    breakdown, correct_count, question_count = _build_attempt_breakdown(attempt)
    answered_count = sum(1 for row in breakdown if row['answered'])
    peer_stats = build_quiz_peer_stats(quiz, attempt)

    all_attempts = list(
        UserAttempts.objects
        .filter(student=student, quiz=quiz, is_complete=True)
        .order_by('-created_at')
    )

    return render(
        request,
        'core/attempt_detail.html',
        {
            'attempt': attempt,
            'quiz': quiz,
            'student': student,
            'breakdown': breakdown,
            'correct_count': correct_count,
            'question_count': question_count,
            'answered_count': answered_count,
            'peer_stats': peer_stats,
            'all_attempts': all_attempts,
        },
    )


@login_required(login_url='accounts:signin')
def attempt_by_uuid_view(request, attempt_uuid):
    """
    View any historical attempt directly by its UUID.
    Linked from the attempt history on the test_info page.
    """
    from core.models import UserAttempts

    attempt = get_object_or_404(
        UserAttempts.objects.select_related(
            'student', 'user', 'quiz', 'quiz__subject', 'quiz__subject__grade_level',
        ),
        uuid=attempt_uuid,
    )

    if not _can_view_attempt(request.user, attempt):
        messages.error(request, "You don't have permission to view this attempt.")
        return redirect('core:exams_list')

    quiz = attempt.quiz
    student = attempt.student

    breakdown, correct_count, question_count = _build_attempt_breakdown(attempt)
    answered_count = sum(1 for row in breakdown if row['answered'])
    peer_stats = build_quiz_peer_stats(quiz, attempt)

    all_attempts = list(
        UserAttempts.objects
        .filter(student=student, quiz=quiz, is_complete=True)
        .order_by('-created_at')
    )

    return render(
        request,
        'core/attempt_detail.html',
        {
            'attempt': attempt,
            'quiz': quiz,
            'student': student,
            'breakdown': breakdown,
            'correct_count': correct_count,
            'question_count': question_count,
            'answered_count': answered_count,
            'peer_stats': peer_stats,
            'all_attempts': all_attempts,
        },
    )


@login_required(login_url='accounts:signin')
@require_POST
@rate_limit(
    key='ai_explain_burst',
    limit=5,
    window=60,
    by='user',
    methods=['POST'],
    json_error='Too many AI requests. Please wait a minute and try again.',
)
@rate_limit(
    key='ai_explain_hour',
    limit=30,
    window=3600,
    by='user',
    methods=['POST'],
    json_error='AI explain limit reached for this hour. Please try again later.',
)
def ai_explain_answer_view(request):
    """AI task: explain why the correct answer to a question is correct."""
    from core.ai import EXPLAIN_ANSWER_TASK, ai_service
    from core.ai.exceptions import AIServiceError
    from core.models import UserAttempts

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    attempt_uuid = str(payload.get('attempt_uuid', '')).strip()
    question_uuid = str(payload.get('question_uuid', '')).strip()
    if not attempt_uuid or not question_uuid:
        return JsonResponse({'error': 'attempt_uuid and question_uuid are required.'}, status=400)

    attempt = get_object_or_404(
        UserAttempts.objects.select_related(
            'quiz', 'quiz__subject', 'quiz__subject__grade_level',
        ),
        uuid=attempt_uuid,
        is_active=True,
    )
    if not _can_view_attempt(request.user, attempt):
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    question = get_object_or_404(
        Question.objects.prefetch_related('options'),
        uuid=question_uuid,
        is_active=True,
        quizzes=attempt.quiz,
    )

    response = attempt.responses.filter(question=question).select_related('selected_option').first()
    if response and response.selected_option_id:
        selected_opt = response.selected_option
    else:
        answers = attempt.answers or {}
        selected_uuid = str(answers.get(str(question.uuid), '')).strip()
        selected_opt = question.options.filter(uuid=selected_uuid).first() if selected_uuid else None
    selected_choice = selected_opt.option if selected_opt else ''

    choices = [
        {'text': opt.option, 'is_correct': opt.is_correct}
        for opt in question.options.filter(is_active=True).order_by('created_at')
    ]
    if not choices:
        return JsonResponse({'error': 'This question has no choices to explain.'}, status=400)

    grade_level = ''
    subject = ''
    if attempt.quiz.subject:
        subject = attempt.quiz.subject.name
        if attempt.quiz.subject.grade_level:
            grade_level = attempt.quiz.subject.grade_level.name

    try:
        result = ai_service.run(
            EXPLAIN_ANSWER_TASK,
            question=question.quiz,
            choices=choices,
            selected_choice=selected_choice,
            grade_level=grade_level,
            subject=subject,
        )
    except AIServiceError as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse(result)


@login_required(login_url='accounts:signin')
def exam_analytics_view(request, quiz_uuid):
    """Analytics dashboard for a single exam."""
    from core.analytics import build_exam_analytics, can_view_exam_analytics, get_quiz_attempts_queryset

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            'subject', 'subject__grade_level', 'strand', 'sub_strand', 'created_by',
        ),
        uuid=quiz_uuid,
        is_active=True,
    )

    if not can_view_exam_analytics(request.user, quiz):
        messages.error(request, "You don't have permission to view analytics for this exam.")
        return redirect('core:exams_list')

    try:
        days = int(request.GET.get('days', '14'))
    except ValueError:
        days = 14
    days = max(7, min(days, 90))

    attempts_qs = get_quiz_attempts_queryset(request.user, quiz)
    analytics = build_exam_analytics(quiz, attempts_qs, days=days)

    return render(
        request,
        'core/exam_analytics.html',
        {
            'quiz': quiz,
            'analytics': analytics,
            'days': days,
            'can_manage': (
                request.user.is_admin_role
                or request.user.is_staff
                or (request.user.is_teacher and quiz.created_by_id == request.user.id)
            ),
        },
    )


def _is_quiz_builder_allowed(user):
    """Teachers, admins, and staff can access the quiz builder."""
    return user.is_admin_role or user.is_staff or user.is_teacher


def _parse_int_id(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _questions_queryset_for_scope(subject_id=None, strand_id=None, sub_strand_id=None):
    """
    Filter questions by curriculum scope (narrowest wins):
    subject only → all questions in subject;
    + strand → all questions under that strand;
    + sub-strand → questions in that sub-strand.
    """
    from subjects.models import Strand, SubStrand

    if not subject_id:
        return Question.objects.none()

    base_qs = (
        Question.objects
        .filter(is_active=True)
        .select_related('sub_strand', 'sub_strand__strand', 'sub_strand__strand__subject')
        .prefetch_related('options')
        .order_by('sub_strand__strand__name', 'sub_strand__name', 'quiz')
    )

    if sub_strand_id:
        sub_strand = SubStrand.objects.filter(
            pk=sub_strand_id,
            strand__subject_id=subject_id,
        ).select_related('strand', 'strand__subject').first()
        if not sub_strand:
            return Question.objects.none()
        if strand_id and sub_strand.strand_id != strand_id:
            return Question.objects.none()
        return base_qs.filter(sub_strand_id=sub_strand.pk)

    if strand_id:
        strand = Strand.objects.filter(pk=strand_id, subject_id=subject_id).first()
        if not strand:
            return Question.objects.none()
        return base_qs.filter(sub_strand__strand_id=strand.pk)

    return base_qs.filter(sub_strand__strand__subject_id=subject_id)


def _quiz_scope_label(subject_id=None, strand_id=None, sub_strand_id=None):
    from subjects.models import Strand, Subject, SubStrand

    subject = Subject.objects.filter(pk=subject_id).select_related('grade_level').first()
    if not subject:
        return ''

    if sub_strand_id:
        sub_strand = SubStrand.objects.filter(
            pk=sub_strand_id,
            strand__subject_id=subject_id,
        ).select_related('strand').first()
        if sub_strand:
            return f'{subject.name} → {sub_strand.strand.name} → {sub_strand.name}'

    if strand_id:
        strand = Strand.objects.filter(pk=strand_id, subject_id=subject_id).first()
        if strand:
            return f'{subject.name} → {strand.name} (all sub-strands)'

    return f'{subject.name} (all strands)'


def _serialize_questions_for_picker(questions_qs):
    data = []
    for question in questions_qs:
        correct_labels = [
            opt.option
            for opt in question.options.filter(is_correct=True, is_active=True)
        ]
        data.append({
            'uuid': str(question.uuid),
            'text': question.quiz,
            'difficulty': question.difficulty,
            'quiz_type': question.quiz_type,
            'score': question.score,
            'correct_answers': correct_labels,
            'option_count': question.options.filter(is_active=True).count(),
            'has_image': bool(question.prompt_image),
            'has_audio': bool(question.prompt_audio),
            'sub_strand_name': question.sub_strand.name if question.sub_strand_id else '',
        })
    return data


def _quiz_scope_from_request(request, quiz=None):
    if request.method == 'POST':
        subject_id = _parse_int_id(request.POST.get('subject'))
        strand_id = _parse_int_id(request.POST.get('strand'))
        sub_strand_id = _parse_int_id(request.POST.get('sub_strand'))
    else:
        subject_id = _parse_int_id(request.GET.get('subject'))
        strand_id = _parse_int_id(request.GET.get('strand'))
        sub_strand_id = _parse_int_id(request.GET.get('sub_strand'))
        if quiz and not subject_id:
            subject_id = quiz.subject_id
            strand_id = quiz.strand_id
            sub_strand_id = quiz.sub_strand_id
    return subject_id, strand_id, sub_strand_id


@login_required(login_url='accounts:signin')
def quiz_builder_list_view(request):
    """List quizzes for teachers/admin to manage."""
    if not _is_quiz_builder_allowed(request.user):
        messages.error(request, "You don't have permission to access the Quiz Builder.")
        return redirect('core:exams_list')

    quizzes = (
        Quiz.objects
        .select_related('subject', 'subject__grade_level', 'strand', 'sub_strand', 'created_by')
        .prefetch_related('questions')
        .annotate(attempt_count=Count('attempts'), question_count=Count('questions'))
    )

    if request.user.is_teacher and not (request.user.is_admin_role or request.user.is_staff):
        quizzes = quizzes.filter(created_by=request.user)

    search = request.GET.get('q', '').strip()
    if search:
        quizzes = quizzes.filter(title__icontains=search)

    status_filter = request.GET.get('status', '').strip()
    if status_filter == 'active':
        quizzes = quizzes.filter(is_active=True)
    elif status_filter == 'inactive':
        quizzes = quizzes.filter(is_active=False)

    quizzes = list(quizzes.order_by('-created_at'))

    return render(request, 'core/quiz_builder_list.html', {
        'quizzes': quizzes,
        'search': search,
        'status_filter': status_filter,
    })


@login_required(login_url='accounts:signin')
def quiz_create_view(request):
    """Create a new quiz and add questions to it."""
    from core.forms import QuizForm
    from subjects.models import Subject, Strand, SubStrand

    if not _is_quiz_builder_allowed(request.user):
        messages.error(request, "You don't have permission to create quizzes.")
        return redirect('core:exams_list')

    if request.method == 'POST':
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.created_by = request.user
            quiz.save()
            question_ids = request.POST.getlist('questions')
            if question_ids:
                selected_questions = Question.objects.filter(uuid__in=question_ids, is_active=True)
                quiz.questions.set(selected_questions)
            messages.success(request, f'Quiz "{quiz.title}" created. You can now add more questions.')
            return redirect('core:quiz_edit', quiz_uuid=quiz.uuid)
    else:
        form = QuizForm()

    subjects = list(Subject.objects.filter(is_active=True).select_related('grade_level').order_by('grade_level__name', 'name'))
    strands = list(Strand.objects.all().select_related('subject').order_by('subject__name', 'name'))
    sub_strands = list(SubStrand.objects.all().select_related('strand__subject').order_by('name'))

    subject_id, strand_id, sub_strand_id = _quiz_scope_from_request(request)
    available_questions = list(_questions_queryset_for_scope(subject_id, strand_id, sub_strand_id))
    scope_label = _quiz_scope_label(subject_id, strand_id, sub_strand_id)

    selected_question_ids = set(request.POST.getlist('questions')) if request.method == 'POST' else set()

    return render(request, 'core/quiz_builder_form.html', {
        'form': form,
        'action': 'Create',
        'quiz': None,
        'subjects': subjects,
        'strands': strands,
        'sub_strands': sub_strands,
        'available_questions': available_questions,
        'scope_label': scope_label,
        'selected_question_ids': selected_question_ids,
        'quiz_edit_mode': False,
    })


@login_required(login_url='accounts:signin')
def quiz_edit_view(request, quiz_uuid):
    """Edit an existing quiz's details and question set."""
    from core.forms import QuizEditForm

    if not _is_quiz_builder_allowed(request.user):
        messages.error(request, "You don't have permission to edit quizzes.")
        return redirect('core:exams_list')

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            'subject', 'subject__grade_level', 'strand', 'sub_strand', 'created_by',
        ),
        uuid=quiz_uuid,
    )

    if request.user.is_teacher and not (request.user.is_admin_role or request.user.is_staff):
        if quiz.created_by_id != request.user.id:
            messages.error(request, "You can only edit quizzes you created.")
            return redirect('core:quiz_builder_list')

    if request.method == 'POST':
        form = QuizEditForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            question_ids = request.POST.getlist('questions')
            if question_ids:
                selected_questions = Question.objects.filter(uuid__in=question_ids, is_active=True)
                quiz.questions.set(selected_questions)
            else:
                quiz.questions.clear()
            messages.success(request, f'Quiz "{quiz.title}" updated successfully.')
            return redirect('core:quiz_edit', quiz_uuid=quiz.uuid)
    else:
        form = QuizEditForm(instance=quiz)

    subject_id = quiz.subject_id
    strand_id = quiz.strand_id
    sub_strand_id = quiz.sub_strand_id
    available_questions = list(_questions_queryset_for_scope(subject_id, strand_id, sub_strand_id))
    scope_label = _quiz_scope_label(subject_id, strand_id, sub_strand_id)

    if request.method == 'POST':
        selected_question_ids = set(request.POST.getlist('questions'))
    else:
        selected_question_ids = set(str(q.uuid) for q in quiz.questions.all())

    return render(request, 'core/quiz_builder_form.html', {
        'form': form,
        'action': 'Update',
        'quiz': quiz,
        'subjects': [],
        'strands': [],
        'sub_strands': [],
        'available_questions': available_questions,
        'scope_label': scope_label,
        'selected_question_ids': selected_question_ids,
        'quiz_edit_mode': True,
    })


@login_required(login_url='accounts:signin')
@require_POST
def quiz_delete_view(request, quiz_uuid):
    """Delete a quiz (admin/creator only)."""
    if not _is_quiz_builder_allowed(request.user):
        messages.error(request, "You don't have permission to delete quizzes.")
        return redirect('core:exams_list')

    quiz = get_object_or_404(Quiz, uuid=quiz_uuid)

    if request.user.is_teacher and not (request.user.is_admin_role or request.user.is_staff):
        if quiz.created_by_id != request.user.id:
            messages.error(request, "You can only delete quizzes you created.")
            return redirect('core:quiz_builder_list')

    title = quiz.title
    quiz.delete()
    messages.success(request, f'Quiz "{title}" deleted.')
    return redirect('core:quiz_builder_list')


@login_required(login_url='accounts:signin')
def bulk_question_import_view(request):
    """UI for pasting JSON and bulk-creating questions."""
    if not _is_quiz_builder_allowed(request.user):
        messages.error(request, "You don't have permission to bulk-import questions.")
        return redirect('core:exams_list')

    example_payload = {
        'questions': [
            {
                'quiz': 'What is the value of $2 + 3$?',
                'sub_strand_slug': 'addition-g4',
                'difficulty': 'Easy',
                'quiz_type': 'Multiple Choice',
                'score': 1,
                'choices': [
                    {'option': '4', 'is_correct': False},
                    {'option': '5', 'is_correct': True},
                    {'option': '6', 'is_correct': False},
                ],
            },
        ],
    }

    return render(request, 'core/bulk_question_import.html', {
        'example_payload': example_payload,
        'example_json': json.dumps(example_payload, indent=2),
        'api_url': reverse('core:bulk_create_questions_api'),
    })


@login_required(login_url='accounts:signin')
@require_POST
def bulk_create_questions_api_view(request):
    """Bulk-create questions (+ choices) from JSON. New questions are inactive pending review."""
    if not _is_quiz_builder_allowed(request.user):
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    from core.question_import import bulk_create_questions

    try:
        result = bulk_create_questions(payload, created_by=request.user)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    status = 201 if result['failed'] == 0 else 200
    return JsonResponse(result, status=status)


@login_required(login_url='accounts:signin')
def quiz_questions_api_view(request):
    """AJAX: Return questions filtered by subject and optional strand/sub-strand."""
    if not _is_quiz_builder_allowed(request.user):
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    subject_id = _parse_int_id(request.GET.get('subject_id'))
    strand_id = _parse_int_id(request.GET.get('strand_id'))
    sub_strand_id = _parse_int_id(request.GET.get('sub_strand_id'))

    if not subject_id:
        return JsonResponse({'questions': [], 'scope_label': ''})

    questions_qs = _questions_queryset_for_scope(subject_id, strand_id, sub_strand_id)
    return JsonResponse({
        'questions': _serialize_questions_for_picker(questions_qs),
        'scope_label': _quiz_scope_label(subject_id, strand_id, sub_strand_id),
    })


def _exam_question_count(quiz):
    if quiz.test_size:
        return quiz.test_size
    return sum(1 for question in quiz.questions.all() if question.is_active)


def _should_auto_create_custom_exam(
    *,
    wizard_phase,
    exam_entries,
    active_subject,
    selected_student,
    learner_grade_missing,
    require_learner_selection,
    show_subject_browser,
    show_scope_browser,
    show_strand_browser,
    show_sub_strand_browser,
):
    if wizard_phase != 'tests':
        return False
    if exam_entries:
        return False
    if not active_subject:
        return False
    if require_learner_selection or learner_grade_missing:
        return False
    if not selected_student:
        return False
    if any([
        show_subject_browser,
        show_scope_browser,
        show_strand_browser,
        show_sub_strand_browser,
    ]):
        return False
    return True


def _maybe_auto_create_custom_exam(
    request,
    *,
    wizard_phase,
    exam_entries,
    active_subject,
    active_strand,
    active_sub_strand,
    scope,
    difficulty,
    selected_student,
    learner_grade_missing,
    require_learner_selection,
    show_subject_browser,
    show_scope_browser,
    show_strand_browser,
    show_sub_strand_browser,
):
    if not _should_auto_create_custom_exam(
        wizard_phase=wizard_phase,
        exam_entries=exam_entries,
        active_subject=active_subject,
        selected_student=selected_student,
        learner_grade_missing=learner_grade_missing,
        require_learner_selection=require_learner_selection,
        show_subject_browser=show_subject_browser,
        show_scope_browser=show_scope_browser,
        show_strand_browser=show_strand_browser,
        show_sub_strand_browser=show_sub_strand_browser,
    ):
        return None

    from core.custom_quiz import find_or_create_custom_quiz, resolve_custom_quiz_scope

    strand, sub_strand = resolve_custom_quiz_scope(
        scope=scope,
        active_strand=active_strand,
        active_sub_strand=active_sub_strand,
    )
    quiz = find_or_create_custom_quiz(
        user=request.user,
        subject=active_subject,
        strand=strand,
        sub_strand=sub_strand,
        difficulty=difficulty,
    )
    if not quiz:
        messages.warning(
            request,
            f'No questions are available yet for {active_subject.name}. '
            'Try another subject or topic.',
        )
        return None

    messages.info(
        request,
        f'Created a custom test for {selected_student.first_name}: {quiz.title}.',
    )
    return redirect(
        'core:test_info',
        quiz_uuid=quiz.uuid,
        student_uuid=selected_student.uuid,
    )


def _exams_list_return_query(request, student=None):
    params = {}
    grade = request.GET.get('grade', '').strip()
    subject = request.GET.get('subject', '').strip()
    strand = request.GET.get('strand', '').strip()
    sub_strand = request.GET.get('sub_strand', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    search = request.GET.get('q', '').strip()
    if grade:
        params['grade'] = grade
    if subject:
        params['subject'] = subject
    if strand:
        params['strand'] = strand
    if sub_strand:
        params['sub_strand'] = sub_strand
    if difficulty:
        params['difficulty'] = difficulty
    if search:
        params['q'] = search
    if student is not None:
        params['student'] = str(student.uuid)
    return urlencode(params)


def _build_exam_card_stat(attempt, quiz, student, question_count, return_query):
    return_path = reverse('core:exams_list')
    if return_query:
        return_path = f'{return_path}?{return_query}'
    test_info_url = (
        f"{reverse('core:test_info', kwargs={'quiz_uuid': quiz.uuid, 'student_uuid': student.uuid})}"
        f"?next={quote(return_path, safe='')}"
    )

    if not attempt:
        return {
            'score_display': '—',
            'status_label': 'Not started',
            'status_key': 'not_started',
            'progress': 0,
            'action_label': f'Start for {student.first_name}',
            'action_url': test_info_url,
            'action_variant': 'primary',
        }

    answered_count = attempt.response_count
    if attempt.is_complete:
        if attempt.marks_possible:
            score_display = f'{attempt.marks_earned}/{attempt.marks_possible} ({attempt.score}%)'
        else:
            score_display = f'{attempt.score}%'
        return {
            'score_display': score_display,
            'status_label': 'Completed',
            'status_key': 'completed',
            'progress': 100,
            'action_label': 'View result',
            'action_url': reverse(
                'core:attempt_detail',
                kwargs={'quiz_uuid': quiz.uuid, 'student_uuid': student.uuid},
            ),
            'action_variant': 'primary',
        }

    progress = 0
    if question_count and answered_count:
        progress = min(99, round((answered_count / question_count) * 100))
    return {
        'score_display': '—',
        'status_label': 'In progress',
        'status_key': 'ongoing',
        'progress': progress,
        'action_label': 'Continue exam',
        'action_url': reverse(
            'core:test_take',
            kwargs={'quiz_uuid': quiz.uuid, 'student_uuid': student.uuid},
        ),
        'action_variant': 'primary',
    }


def _build_exam_card_stats_map(quizzes, linked_students, request):
    """Per-quiz, per-learner stats for exam cards (guardian exams list)."""
    from core.models import UserAttempts

    if not linked_students:
        return {}

    quiz_ids = [quiz.uuid for quiz in quizzes]
    student_ids = [student.uuid for student in linked_students]
    # Order so in-progress (is_complete=False) rows sort before completed ones;
    # then most-recent first. The first row we encounter per (quiz, student) pair wins.
    attempts = (
        UserAttempts.objects
        .filter(quiz_id__in=quiz_ids, student_id__in=student_ids, is_active=True)
        .annotate(response_count=Count('responses'))
        .order_by('is_complete', '-created_at')
    )
    attempt_map = {}
    for att in attempts:
        key = (att.quiz_id, att.student_id)
        if key not in attempt_map:
            attempt_map[key] = att

    stats_map = {}
    for quiz in quizzes:
        question_count = _exam_question_count(quiz)
        quiz_key = str(quiz.uuid)
        stats_map[quiz_key] = {}
        for student in linked_students:
            return_query = _exams_list_return_query(request, student=student)
            attempt = attempt_map.get((quiz.uuid, student.uuid))
            stats_map[quiz_key][str(student.uuid)] = _build_exam_card_stat(
                attempt,
                quiz,
                student,
                question_count,
                return_query,
            )
    return stats_map


def _group_exam_entries_by_grade(exam_entries):
    """Group exam card entries under grade level headings (preserves sort order)."""
    groups = []
    index_by_grade = {}
    for entry in exam_entries:
        quiz = entry['quiz']
        grade_level = quiz.subject.grade_level if quiz.subject_id else None
        grade_key = grade_level.pk if grade_level else 0
        if grade_key not in index_by_grade:
            index_by_grade[grade_key] = len(groups)
            groups.append({
                'grade_level': grade_level,
                'grade_name': grade_level.name if grade_level else 'Other',
                'entries': [],
            })
        groups[index_by_grade[grade_key]]['entries'].append(entry)
    return groups


def _enrich_browse_subject_item(item, student, base_quizzes):
    """Add performance and availability stats for subject course cards."""
    from core.models import UserAttempts

    subject = item['subject']
    subject_quizzes = list(base_quizzes.filter(subject=subject))
    quiz_ids = [quiz.uuid for quiz in subject_quizzes]

    question_count = 0
    duration_minutes = 0
    for quiz in subject_quizzes:
        qc = quiz.test_size or quiz.questions.filter(is_active=True).count()
        question_count += qc
        if quiz.time_limit_minutes:
            duration_minutes = max(duration_minutes, quiz.time_limit_minutes)

    if not duration_minutes and question_count:
        duration_minutes = min(60, max(15, round(question_count * 0.6)))

    item['question_count'] = question_count
    item['duration_minutes'] = duration_minutes
    item['avg_score'] = 0
    item['completed_count'] = 0
    item['status_label'] = 'Not started'
    item['status_key'] = 'not_started'

    if not student or not quiz_ids:
        return item

    attempts = UserAttempts.objects.filter(
        student=student,
        quiz_id__in=quiz_ids,
        is_active=True,
    )
    completed_qs = attempts.filter(is_complete=True)
    item['completed_count'] = completed_qs.count()
    avg = completed_qs.aggregate(v=Avg('score'))['v']
    item['avg_score'] = round(avg) if avg is not None else 0

    if attempts.filter(is_complete=False).exists():
        item['status_label'] = 'In progress'
        item['status_key'] = 'ongoing'
    elif item['completed_count']:
        item['status_label'] = 'Completed'
        item['status_key'] = 'completed'

    return item


def _exams_wizard_phase(
    show_subject_browser,
    show_scope_browser,
    show_strand_browser,
    show_sub_strand_browser,
    require_learner_selection,
):
    if require_learner_selection:
        return None
    if show_subject_browser:
        return 'subject'
    if show_scope_browser:
        return 'scope'
    if show_strand_browser:
        return 'strand'
    if show_sub_strand_browser:
        return 'sub_strand'
    return 'tests'


def _build_exams_wizard_trail(
    *,
    phase,
    prefix,
    exams_nav_grade,
    browse_all_grades,
    active_grade,
    active_subject,
    active_scope,
    active_strand,
    active_sub_strand,
    filterable_grade_levels,
    staff_exams_browse,
):
    """Build vertical wizard steps with progress for the exams browse flow."""
    scope_labels = {
        'general': 'Whole subject',
        'strand': 'Strand focus',
        'sub_strand': 'Sub-strand focus',
    }
    phase_labels = {
        'subject': ('Choose subject', 'Pick a subject to explore tests and practice areas.'),
        'scope': ('Test focus', 'Choose whether to test the whole subject or a specific topic.'),
        'strand': ('Choose strand', 'Select the CBE strand to practise.'),
        'sub_strand': ('Choose sub-strand', 'Narrow down to a specific sub-strand.'),
        'tests': ('Choose test', 'Pick an exam to start or continue.'),
    }

    grade_qs = filterable_grade_levels
    show_grade_step = staff_exams_browse or grade_qs.count() > 1 or browse_all_grades

    if browse_all_grades:
        grade_value = 'All grades'
        grade_edit_url = reverse('core:exams_list') + '?' + prefix + 'grade=all'
    elif active_grade:
        grade_value = active_grade.name
        grade_edit_url = reverse('core:exams_list') + '?' + prefix + f'grade={active_grade.slug}'
    else:
        grade_value = None
        grade_edit_url = reverse('core:exams_list') + ('?' + prefix.rstrip('&') if prefix else '')

    subject_edit_url = grade_edit_url
    if active_subject:
        subject_edit_url = (
            reverse('core:exams_list') + '?' + prefix + f'subject={active_subject.slug}'
            + (f'&{exams_nav_grade}' if exams_nav_grade else '')
        )

    focus_edit_url = None
    focus_value = None
    if active_subject:
        focus_edit_url = (
            reverse('core:exams_list') + '?' + prefix
            + f'subject={active_subject.slug}'
            + (f'&{exams_nav_grade}' if exams_nav_grade else '')
        )
        if active_scope:
            focus_value = scope_labels.get(active_scope, active_scope.replace('_', ' ').title())

    topic_edit_url = None
    topic_value = None
    show_topic_step = active_scope in ('strand', 'sub_strand') or phase in ('strand', 'sub_strand')
    if show_topic_step and active_subject:
        if active_scope == 'sub_strand':
            topic_edit_url = (
                reverse('core:exams_list') + '?' + prefix
                + f'subject={active_subject.slug}&scope=sub_strand'
                + (f'&{exams_nav_grade}' if exams_nav_grade else '')
            )
        elif active_scope == 'strand' or active_strand:
            topic_edit_url = (
                reverse('core:exams_list') + '?' + prefix
                + f'subject={active_subject.slug}&scope=strand'
                + (f'&{exams_nav_grade}' if exams_nav_grade else '')
            )
        if active_sub_strand:
            topic_value = active_sub_strand.name
        elif active_strand:
            topic_value = active_strand.name

    step_defs = []
    rank = 0
    if show_grade_step:
        step_defs.append({
            'key': 'grade',
            'label': 'Grade level',
            'icon': '🏫',
            'value': grade_value,
            'edit_url': grade_edit_url if grade_value else None,
            'rank': rank,
        })
        rank += 1
    step_defs.append({
        'key': 'subject',
        'label': 'Subject',
        'icon': '📚',
        'value': active_subject.name if active_subject else None,
        'edit_url': subject_edit_url if active_subject else None,
        'rank': rank,
    })
    rank += 1
    if active_subject or phase in ('scope', 'strand', 'sub_strand', 'tests'):
        step_defs.append({
            'key': 'focus',
            'label': 'Test focus',
            'icon': '🎯',
            'value': focus_value,
            'edit_url': focus_edit_url if focus_value else None,
            'rank': rank,
        })
        rank += 1
    if show_topic_step:
        step_defs.append({
            'key': 'topic',
            'label': 'Topic',
            'icon': '🧵',
            'value': topic_value,
            'edit_url': topic_edit_url if topic_value else None,
            'rank': rank,
        })
        rank += 1
    step_defs.append({
        'key': 'tests',
        'label': 'Tests',
        'icon': '✅',
        'value': None,
        'edit_url': None,
        'rank': rank,
    })

    phase_to_step_key = {
        'subject': 'subject',
        'scope': 'focus',
        'strand': 'topic',
        'sub_strand': 'topic',
        'tests': 'tests',
    }
    current_step_key = phase_to_step_key.get(phase, 'subject')
    current_rank = next(
        (item['rank'] for item in step_defs if item['key'] == current_step_key),
        0,
    )

    def _is_complete(defn):
        key = defn['key']
        if key == 'grade':
            return bool(grade_value)
        if key == 'subject':
            return bool(active_subject)
        if key == 'focus':
            return bool(focus_value)
        if key == 'topic':
            return bool(topic_value)
        return False

    steps = []
    for index, definition in enumerate(step_defs, start=1):
        if definition['key'] == current_step_key:
            state = 'current'
        elif definition['rank'] < current_rank and _is_complete(definition):
            state = 'complete'
        elif definition['rank'] < current_rank and definition['key'] == 'grade' and grade_value:
            state = 'complete'
        elif definition['rank'] > current_rank:
            continue
        else:
            continue

        steps.append({
            'number': index,
            'key': definition['key'],
            'label': definition['label'],
            'icon': definition['icon'],
            'value': definition['value'],
            'edit_url': definition['edit_url'],
            'state': state,
        })

    total = len(step_defs)
    completed = sum(1 for step in steps if step['state'] == 'complete')
    current = sum(1 for step in steps if step['state'] == 'current')
    progress_pct = round(((completed + 0.35 * current) / total) * 100) if total else 0
    progress_pct = max(8, min(progress_pct, 100))

    current_label, current_hint = phase_labels.get(phase, ('Continue', ''))
    current_step_number = next(
        (step['number'] for step in steps if step['state'] == 'current'),
        len(steps) or 1,
    )

    return {
        'steps': steps,
        'progress_pct': progress_pct,
        'current_phase': phase,
        'current_label': current_label,
        'current_hint': current_hint,
        'current_step_number': current_step_number,
        'total_steps': total,
    }


def _group_browse_subjects_by_grade(browse_subjects):
    """Group subject browser cards under grade level headings."""
    groups = []
    index_by_grade = {}
    for item in browse_subjects:
        grade_level = item['subject'].grade_level
        grade_key = grade_level.pk
        if grade_key not in index_by_grade:
            index_by_grade[grade_key] = len(groups)
            groups.append({
                'grade_level': grade_level,
                'subjects': [],
            })
        groups[index_by_grade[grade_key]]['subjects'].append(item)
    return groups


@login_required(login_url='accounts:signin')
def exam_filter_options_api_view(request):
    """AJAX: cascading subject / strand / sub-strand options for the exams filter bar."""
    from accounts.models import Student
    from subjects.models import Strand, Subject
    from subjects.grade_utils import eligible_grade_levels_for_student
    from core.exam_filters import (
        active_quizzes_queryset,
        resolve_grade_from_slug,
        serialize_wizard_options,
    )

    student_uuid = request.GET.get('student', '').strip()
    grade_slug = request.GET.get('grade', '').strip()
    subject_slug = request.GET.get('subject', '').strip()
    strand_slug = request.GET.get('strand', '').strip()

    filterable_grade_levels = GradeLevel.objects.none()
    selected_student = None
    if student_uuid:
        candidate = Student.objects.filter(uuid=student_uuid).select_related('grade_level').first()
        if candidate and _can_access_learner(request.user, candidate):
            selected_student = candidate
            if candidate.grade_level_id:
                filterable_grade_levels = eligible_grade_levels_for_student(candidate)

    quizzes = active_quizzes_queryset()
    active_grade = None

    if selected_student and selected_student.grade_level_id:
        eligible_ids = list(filterable_grade_levels.values_list('pk', flat=True))
        if eligible_ids:
            quizzes = quizzes.filter(subject__grade_level_id__in=eligible_ids)
        else:
            quizzes = quizzes.none()
        if grade_slug:
            active_grade = resolve_grade_from_slug(grade_slug, filterable_grade_levels)
            if active_grade:
                quizzes = quizzes.filter(subject__grade_level=active_grade)
    elif grade_slug:
        active_grade = resolve_grade_from_slug(grade_slug, filterable_grade_levels)
        if active_grade:
            quizzes = quizzes.filter(subject__grade_level=active_grade)

    subject = None
    if subject_slug:
        subject = Subject.objects.filter(slug=subject_slug, is_active=True).first()
        if subject and quizzes.filter(subject=subject).exists():
            quizzes = quizzes.filter(subject=subject)
        else:
            subject = None

    strand = None
    if strand_slug and subject:
        strand = Strand.objects.filter(slug=strand_slug, subject=subject, is_active=True).first()
        if strand and quizzes.filter(strand=strand).exists():
            quizzes = quizzes.filter(strand=strand)
        else:
            strand = None

    include_grades = request.GET.get('include_grades', '').strip() in ('1', 'true', 'yes')

    return JsonResponse(serialize_wizard_options(
        quizzes,
        filterable_grade_levels,
        subject=subject,
        strand=strand,
        grade_level=active_grade,
        student=selected_student,
        include_grades=include_grades,
    ))


@login_required(login_url='accounts:signin')
def exams_list_view(request):
    """
    Exams page. Lists all active quizzes.

    Guardian flow (?student=): learner grade band, subject → test type → exams.
    Teacher/admin flow (/exams/): defaults to Grade 6, same browse steps without a learner.
    """
    from accounts.models import Student
    from subjects.grade_utils import (
        band_slug_for_level,
        eligible_grade_levels_for_student,
    )

    all_grade_levels = GradeLevel.objects.all().order_by('name')

    # Determine which grade levels the guardian's students sit in
    student_grade_levels = GradeLevel.objects.none()
    linked_students = []
    if request.user.is_guardian:
        for link in request.user.linked_students.prefetch_related('students__grade_level'):
            linked_students.extend(link.students.all())
        gl_ids = {
            s.grade_level_id for s in linked_students if s.grade_level_id
        }
        student_grade_levels = GradeLevel.objects.filter(pk__in=gl_ids)

    # --- Filters from GET params ---
    grade_slug      = request.GET.get('grade', '').strip()
    band_slug       = request.GET.get('band', '').strip()
    subject_slug    = request.GET.get('subject', '').strip()
    scope           = request.GET.get('scope', '').strip()
    strand_slug     = request.GET.get('strand', '').strip()
    sub_strand_slug = request.GET.get('sub_strand', '').strip()
    difficulty      = request.GET.get('difficulty', '').strip()
    search          = request.GET.get('q', '').strip()
    student_uuid    = request.GET.get('student', '').strip()

    selected_student = None
    if student_uuid:
        candidate = Student.objects.filter(uuid=student_uuid).select_related('grade_level').first()
        if candidate and _can_access_learner(request.user, candidate):
            selected_student = candidate

    require_learner_selection = (
        request.user.is_guardian
        and bool(linked_students)
        and selected_student is None
    )

    if (
        require_learner_selection
        and len(linked_students) == 1
        and not any([
            subject_slug, scope, strand_slug, sub_strand_slug, difficulty, search,
        ])
    ):
        return redirect(
            reverse('core:exams_list') + '?' + urlencode({'student': str(linked_students[0].uuid)})
        )

    staff_exams_browse = _staff_exams_browse(request.user, selected_student)

    filterable_grade_levels = GradeLevel.objects.none()
    student_grade_band = None
    student_band_slug = None
    learner_grade_missing = False

    if selected_student:
        if selected_student.grade_level_id:
            filterable_grade_levels = eligible_grade_levels_for_student(selected_student)
            student_grade_band = selected_student.grade_level.level
            student_band_slug = band_slug_for_level(student_grade_band)
        else:
            learner_grade_missing = True
    elif staff_exams_browse:
        filterable_grade_levels = all_grade_levels

    exams_browse_active = _exams_browse_flow_active(
        selected_student, learner_grade_missing, staff_exams_browse,
    )

    active_grade = None
    active_band = None
    active_subject = None
    active_strand = None
    active_sub_strand = None

    from subjects.models import Strand, Subject, SubStrand
    from core.exam_filters import (
        DEFAULT_EXAMS_GRADE_SLUG,
        active_quizzes_queryset,
        quiz_count_for_strand,
        quiz_count_for_subject,
        quiz_count_for_subject_only,
        quiz_count_for_sub_strand,
        resolve_grade_from_slug,
        strands_for_wizard,
        sub_strands_for_wizard,
        subjects_for_quizzes,
        strands_for_quizzes,
        sub_strands_for_quizzes,
    )

    quizzes = active_quizzes_queryset()
    browse_all_grades = False

    if selected_student:
        if selected_student.grade_level_id:
            eligible_ids = list(filterable_grade_levels.values_list('pk', flat=True))
            if eligible_ids:
                quizzes = quizzes.filter(subject__grade_level_id__in=eligible_ids)
            else:
                quizzes = quizzes.none()

            browse_all_grades = grade_slug == 'all'
            if grade_slug and not browse_all_grades:
                active_grade = resolve_grade_from_slug(grade_slug, filterable_grade_levels)
                if active_grade:
                    quizzes = quizzes.filter(subject__grade_level=active_grade)
                elif GradeLevel.objects.filter(slug=grade_slug).exists():
                    messages.warning(
                        request,
                        f'Exams above {selected_student.grade_level.name} are not shown for this learner.',
                    )
            elif not browse_all_grades:
                active_grade = selected_student.grade_level
                quizzes = quizzes.filter(subject__grade_level=active_grade)

            if band_slug and student_band_slug and band_slug == student_band_slug:
                active_band = student_grade_band
            elif band_slug:
                messages.warning(request, 'That school band is not available for this learner.')
        else:
            quizzes = quizzes.none()
    elif staff_exams_browse:
        browse_all_grades = grade_slug == 'all'
        if grade_slug and not browse_all_grades:
            active_grade = resolve_grade_from_slug(grade_slug, filterable_grade_levels)
            if active_grade:
                quizzes = quizzes.filter(subject__grade_level=active_grade)
        elif not browse_all_grades:
            active_grade = GradeLevel.objects.filter(slug=DEFAULT_EXAMS_GRADE_SLUG).first()
            if active_grade:
                quizzes = quizzes.filter(subject__grade_level=active_grade)
    elif grade_slug:
        if not filterable_grade_levels.exists():
            filterable_grade_levels = all_grade_levels
        active_grade = resolve_grade_from_slug(grade_slug, filterable_grade_levels)
        if active_grade:
            quizzes = quizzes.filter(subject__grade_level=active_grade)

    if request.user.is_guardian and not selected_student:
        quizzes = quizzes.none()

    base_quizzes = quizzes
    filter_subjects = subjects_for_quizzes(base_quizzes, grade_level=active_grade)

    show_subject_browser = (
        exams_browse_active
        and not subject_slug
        and not strand_slug
        and not sub_strand_slug
        and not difficulty
        and not search
    )

    browse_subjects = []
    if exams_browse_active:
        grades_for_browse = filterable_grade_levels
        if active_grade:
            grades_for_browse = GradeLevel.objects.filter(pk=active_grade.pk)
        for s in Subject.objects.filter(
            is_active=True,
            grade_level__in=grades_for_browse,
        ).select_related('grade_level').order_by('grade_level__name', 'name'):
            browse_subjects.append({
                'subject': s,
                'count': quiz_count_for_subject(base_quizzes, s),
            })
        for item in browse_subjects:
            _enrich_browse_subject_item(item, selected_student, base_quizzes)

    if subject_slug:
        active_subject = Subject.objects.filter(
            slug=subject_slug, is_active=True,
        ).select_related('grade_level').first()
        if active_subject:
            if selected_student and filterable_grade_levels.exists():
                if filterable_grade_levels.filter(pk=active_subject.grade_level_id).exists():
                    quizzes = quizzes.filter(subject=active_subject)
                else:
                    active_subject = None
                    messages.warning(
                        request,
                        'That subject is not available for this learner.',
                    )
            else:
                quizzes = quizzes.filter(subject=active_subject)

    if active_subject:
        filter_strands = strands_for_quizzes(
            base_quizzes.filter(subject=active_subject),
            subject=active_subject,
        )
        subject_quizzes = base_quizzes.filter(subject=active_subject)
        general_test_count = quiz_count_for_subject_only(subject_quizzes, active_subject)
        browse_strands = [
            {
                'strand': st,
                'count': quiz_count_for_strand(subject_quizzes, st),
            }
            for st in strands_for_wizard(subject_quizzes, subject=active_subject)
        ]
        browse_sub_strands = []
        for st in strands_for_wizard(subject_quizzes, subject=active_subject):
            for ss in sub_strands_for_wizard(subject_quizzes, strand=st):
                browse_sub_strands.append({
                    'sub_strand': ss,
                    'strand': st,
                    'count': quiz_count_for_sub_strand(subject_quizzes, ss),
                })
    else:
        filter_strands = Strand.objects.none()
        subject_quizzes = base_quizzes.none()
        general_test_count = 0
        browse_strands = []
        browse_sub_strands = []

    show_scope_browser = (
        exams_browse_active
        and active_subject
        and not scope
        and not strand_slug
        and not sub_strand_slug
        and not difficulty
        and not search
    )
    show_strand_browser = (
        exams_browse_active
        and active_subject
        and scope == 'strand'
        and not strand_slug
        and not sub_strand_slug
        and not difficulty
        and not search
    )
    show_sub_strand_browser = (
        exams_browse_active
        and active_subject
        and scope == 'sub_strand'
        and not sub_strand_slug
        and not difficulty
        and not search
    )
    show_test_type_browser = (
        show_scope_browser or show_strand_browser or show_sub_strand_browser
    )

    if scope != 'general' and strand_slug and active_subject:
        active_strand = Strand.objects.filter(
            slug=strand_slug, subject=active_subject, is_active=True,
        ).first()
        if active_strand:
            quizzes = quizzes.filter(strand=active_strand)
        else:
            active_strand = None

    if active_strand and scope != 'general':
        filter_sub_strands = sub_strands_for_quizzes(
            base_quizzes.filter(subject=active_subject, strand=active_strand),
            strand=active_strand,
        )
    else:
        filter_sub_strands = SubStrand.objects.none()

    if scope != 'general' and sub_strand_slug and active_subject:
        active_sub_strand = SubStrand.objects.filter(
            slug=sub_strand_slug,
            strand__subject=active_subject,
            is_active=True,
        ).select_related('strand').first()
        if active_sub_strand:
            active_strand = active_sub_strand.strand
            quizzes = quizzes.filter(sub_strand=active_sub_strand)
        else:
            active_sub_strand = None

    if scope == 'general' and active_subject:
        active_strand = None
        active_sub_strand = None
        quizzes = quizzes.filter(strand__isnull=True, sub_strand__isnull=True)

    if difficulty:
        quizzes = quizzes.filter(difficulty=difficulty)

    if search:
        quizzes = quizzes.filter(title__icontains=search)

    quizzes = list(quizzes.order_by('subject__grade_level__name', 'subject__name', 'title'))

    general_exam_entries = []
    if show_scope_browser and active_subject:
        general_qs = list(
            subject_quizzes.filter(
                strand__isnull=True,
                sub_strand__isnull=True,
            ).order_by('title')
        )
        general_stats = (
            _build_exam_card_stats_map(general_qs, linked_students, request)
            if general_qs and linked_students else {}
        )
        for quiz in general_qs:
            question_count = _exam_question_count(quiz)
            initial_stat = None
            if selected_student:
                initial_stat = general_stats.get(str(quiz.uuid), {}).get(str(selected_student.uuid))
            general_exam_entries.append({
                'quiz': quiz,
                'question_count': question_count,
                'initial_stat': initial_stat,
            })

    if show_subject_browser or show_test_type_browser or require_learner_selection:
        quizzes = []
        exam_entries = []
        exam_card_stats = {}
    else:
        exam_card_stats = _build_exam_card_stats_map(quizzes, linked_students, request)
        exam_entries = []
        for quiz in quizzes:
            question_count = _exam_question_count(quiz)
            initial_stat = None
            if selected_student:
                initial_stat = exam_card_stats.get(str(quiz.uuid), {}).get(str(selected_student.uuid))
            exam_entries.append({
                'quiz': quiz,
                'question_count': question_count,
                'initial_stat': initial_stat,
            })

    exam_entries_by_grade = _group_exam_entries_by_grade(exam_entries)
    browse_subjects_by_grade = _group_browse_subjects_by_grade(browse_subjects)

    wizard_phase = _exams_wizard_phase(
        show_subject_browser,
        show_scope_browser,
        show_strand_browser,
        show_sub_strand_browser,
        require_learner_selection,
    )
    exams_wizard = None
    if exams_browse_active and wizard_phase:
        exams_wizard = _build_exams_wizard_trail(
            phase=wizard_phase,
            prefix=(
                f'student={selected_student.uuid}&' if selected_student else ''
            ),
            exams_nav_grade=(
                'grade=all' if browse_all_grades
                else f'grade={active_grade.slug}' if active_grade else ''
            ),
            browse_all_grades=browse_all_grades,
            active_grade=active_grade,
            active_subject=active_subject,
            active_scope=scope,
            active_strand=active_strand,
            active_sub_strand=active_sub_strand,
            filterable_grade_levels=filterable_grade_levels,
            staff_exams_browse=staff_exams_browse,
        )

    auto_create_response = _maybe_auto_create_custom_exam(
        request,
        wizard_phase=wizard_phase,
        exam_entries=exam_entries,
        active_subject=active_subject,
        active_strand=active_strand,
        active_sub_strand=active_sub_strand,
        scope=scope,
        difficulty=difficulty,
        selected_student=selected_student,
        learner_grade_missing=learner_grade_missing,
        require_learner_selection=require_learner_selection,
        show_subject_browser=show_subject_browser,
        show_scope_browser=show_scope_browser,
        show_strand_browser=show_strand_browser,
        show_sub_strand_browser=show_sub_strand_browser,
    )
    if auto_create_response:
        return auto_create_response

    context = {
        'quizzes': quizzes,
        'exam_entries': exam_entries,
        'exam_entries_by_grade': exam_entries_by_grade,
        'exam_card_stats': exam_card_stats,
        'all_grade_levels': all_grade_levels,
        'filterable_grade_levels': filterable_grade_levels,
        'student_grade_band': student_grade_band,
        'student_band_slug': student_band_slug,
        'active_band': active_band,
        'learner_grade_missing': learner_grade_missing,
        'student_grade_levels': student_grade_levels,
        'linked_students': linked_students,
        'selected_student': selected_student,
        'require_learner_selection': require_learner_selection,
        'active_grade': active_grade,
        'active_subject': active_subject,
        'active_strand': active_strand,
        'active_sub_strand': active_sub_strand,
        'filter_subjects': filter_subjects,
        'filter_strands': filter_strands,
        'filter_sub_strands': filter_sub_strands,
        'subject_options': [
            (s, quiz_count_for_subject(base_quizzes, s)) for s in filter_subjects
        ],
        'strand_options': [
            (st, quiz_count_for_strand(base_quizzes.filter(subject=active_subject), st))
            for st in filter_strands
        ] if active_subject else [],
        'sub_strand_options': [
            (ss, quiz_count_for_sub_strand(
                base_quizzes.filter(subject=active_subject, strand=active_strand), ss,
            ))
            for ss in filter_sub_strands
        ] if active_strand else [],
        'active_difficulty': difficulty,
        'search': search,
        'difficulty_choices': Quiz.difficulty_choice,
        'staff_exams_browse': staff_exams_browse,
        'exams_nav_student_prefix': (
            f'student={selected_student.uuid}&' if selected_student else ''
        ),
        'show_subject_browser': show_subject_browser,
        'show_scope_browser': show_scope_browser,
        'show_strand_browser': show_strand_browser,
        'show_sub_strand_browser': show_sub_strand_browser,
        'show_test_type_browser': show_test_type_browser,
        'browse_subjects': browse_subjects,
        'browse_subjects_by_grade': browse_subjects_by_grade,
        'browse_strands': browse_strands,
        'browse_sub_strands': browse_sub_strands,
        'general_test_count': general_test_count,
        'general_exam_entries': general_exam_entries,
        'active_scope': scope,
        'browse_all_grades': browse_all_grades,
        'exams_nav_grade': (
            'grade=all' if browse_all_grades
            else f'grade={active_grade.slug}' if active_grade else ''
        ),
        'has_finder_selection': any([
            grade_slug, subject_slug, scope, strand_slug, sub_strand_slug, difficulty,
        ]),
        'open_exam_wizard': (
            request.GET.get('guide') == '1'
            and bool(selected_student)
            and not learner_grade_missing
            and not require_learner_selection
        ),
        'exams_wizard': exams_wizard,
    }
    return render(request, 'core/exams_list.html', context)
