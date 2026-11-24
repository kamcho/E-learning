"""Optional strict exam mode: tab-focus rules stored in the visitor session."""

from django.contrib import messages
from django.urls import reverse

EXAM_STRICT_MODE_KEY = 'exam_strict_mode'
EXAM_STRICT_SCOPE_KEY = 'exam_strict_scope'
EXAM_STRICT_MAX_TAB_LEAVES = 3
EXAM_STRICT_MAX_AWAY_MS = 10_000


def strict_mode_from_post(request) -> bool:
    return request.POST.get('exam_strict_mode') in ('1', 'on', 'true')


def activate_strict_mode(request, *, scope_type, scope_id, enabled: bool) -> None:
    request.session[EXAM_STRICT_MODE_KEY] = bool(enabled)
    if enabled:
        request.session[EXAM_STRICT_SCOPE_KEY] = {
            'type': scope_type,
            'id': str(scope_id),
        }
    else:
        request.session.pop(EXAM_STRICT_SCOPE_KEY, None)
    request.session.modified = True


def clear_strict_mode(request) -> None:
    request.session.pop(EXAM_STRICT_MODE_KEY, None)
    request.session.pop(EXAM_STRICT_SCOPE_KEY, None)
    request.session.modified = True


def strict_mode_active_for(request, *, scope_type, scope_id) -> bool:
    if not request.session.get(EXAM_STRICT_MODE_KEY):
        return False
    scope = request.session.get(EXAM_STRICT_SCOPE_KEY) or {}
    return scope.get('type') == scope_type and scope.get('id') == str(scope_id)


def strict_mode_template_context(request, *, scope_type, scope_id):
    active = strict_mode_active_for(request, scope_type=scope_type, scope_id=scope_id)
    ctx = {
        'exam_strict_mode': active,
        'exam_strict_max_tab_leaves': EXAM_STRICT_MAX_TAB_LEAVES,
        'exam_strict_max_away_seconds': EXAM_STRICT_MAX_AWAY_MS // 1000,
    }
    if active:
        ctx['exam_strict_reset_url'] = reverse('core:exam_strict_reset')
    return ctx


def _strict_reset_message(reason: str) -> str:
    if reason == 'away_too_long':
        return (
            'Strict mode: your exam was reset because you left this tab for more than '
            f'{EXAM_STRICT_MAX_AWAY_MS // 1000} seconds.'
        )
    return (
        'Strict mode: your exam was reset because you left this tab more than '
        f'{EXAM_STRICT_MAX_TAB_LEAVES} times.'
    )


def reset_practice_exam_strict(request, reason: str) -> str:
    from core.demo import clear_demo_session

    clear_demo_session(request)
    messages.error(request, _strict_reset_message(reason))
    return reverse('core:exam_wizard') + '?restart=1'


def _clear_attempt_answers_session(request, attempt_uuid) -> None:
    key = f'attempt_answers_{attempt_uuid}'
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def reset_attempt_exam_strict(request, attempt_uuid, reason: str) -> str:
    from core.models import UserAttempts
    from core.scoring import clear_attempt_responses

    attempt = (
        UserAttempts.objects.select_related('quiz', 'student')
        .filter(uuid=attempt_uuid)
        .first()
    )
    if not attempt:
        messages.error(request, _strict_reset_message(reason))
        return reverse('core:exams_list')

    if not attempt.is_complete:
        clear_attempt_responses(attempt)
        attempt.is_active = False
        attempt.is_complete = True
        attempt.score = 0
        attempt.marks_earned = 0
        attempt.marks_possible = attempt.marks_possible or 0
        attempt.save(
            update_fields=[
                'is_active', 'is_complete', 'score',
                'marks_earned', 'marks_possible', 'updated_at',
            ],
        )
    _clear_attempt_answers_session(request, attempt_uuid)
    messages.error(request, _strict_reset_message(reason))
    return reverse(
        'core:test_info',
        kwargs={'quiz_uuid': attempt.quiz.uuid, 'student_uuid': attempt.student.uuid},
    )