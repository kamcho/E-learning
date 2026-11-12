"""Model and auth signal handlers for user action audit logs."""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from accounts.audit import get_current_request, log_user_action


def _audited_model_registry():
    from accounts.models import MyUser, Student
    from core.models import AttemptResponse, Option, Question, Quiz, UserAttempts
    from subjects.models import Discipline, GradeLevel, Strand, Subject, SubStrand
    from subscriptions.models import Payment, Subscription

    return {
        MyUser,
        Student,
        Question,
        Option,
        Quiz,
        UserAttempts,
        AttemptResponse,
        Subject,
        Strand,
        SubStrand,
        GradeLevel,
        Discipline,
        Subscription,
        Payment,
    }


AUDITED_MODELS = None


def audited_models():
    global AUDITED_MODELS
    if AUDITED_MODELS is None:
        AUDITED_MODELS = _audited_model_registry()
    return AUDITED_MODELS


def _resolve_actor(instance):
    request = get_current_request()
    if request and request.user.is_authenticated:
        return request.user
    if hasattr(instance, 'created_by_id') and instance.created_by_id:
        return instance.created_by
    if hasattr(instance, 'user_id') and instance.user_id:
        from accounts.models import MyUser
        return MyUser.objects.filter(pk=instance.user_id).first()
    return None


def _skip_user_save(instance, kwargs):
    from accounts.models import MyUser

    if not isinstance(instance, MyUser):
        return False
    update_fields = kwargs.get('update_fields')
    if not update_fields:
        return False
    allowed = {'last_login', 'updated_at', 'date_joined'}
    return set(update_fields) <= allowed


def _model_action_code(instance, verb):
    label = f'{instance._meta.app_label}.{instance.__class__.__name__}'
    return f'{label}.{verb}'


@receiver(post_save)
def audit_model_save(sender, instance, created, **kwargs):
    from accounts.models import UserActionLog

    if sender is UserActionLog:
        return
    if sender not in audited_models():
        return
    if _skip_user_save(instance, kwargs):
        return

    verb = 'create' if created else 'update'
    log_user_action(
        action=_model_action_code(instance, verb),
        verb=verb,
        user=_resolve_actor(instance),
        obj=instance,
        metadata={'source': 'model_signal'},
    )


@receiver(post_delete)
def audit_model_delete(sender, instance, **kwargs):
    from accounts.models import UserActionLog

    if sender is UserActionLog:
        return
    if sender not in audited_models():
        return

    log_user_action(
        action=_model_action_code(instance, 'delete'),
        verb='delete',
        user=_resolve_actor(instance),
        obj=instance,
        metadata={'source': 'model_signal'},
    )


def _register_m2m_audit():
    from accounts.models import LinkedStudents

    @receiver(m2m_changed, sender=LinkedStudents.students.through)
    def audit_linked_students_m2m(sender, instance, action, pk_set, **kwargs):
        if action not in ('post_add', 'post_remove', 'post_clear'):
            return

        log_user_action(
            action='accounts.LinkedStudents.m2m_change',
            verb='update',
            user=_resolve_actor(instance) or instance.user,
            obj=instance,
            metadata={
                'source': 'model_signal',
                'm2m_action': action,
                'student_ids': sorted(str(pk) for pk in (pk_set or [])),
            },
        )


_register_m2m_audit()


@receiver(user_logged_in)
def audit_user_logged_in(sender, request, user, **kwargs):
    log_user_action(
        action='auth.login',
        verb='login',
        user=user,
        obj=user,
        request=request,
        metadata={'source': 'auth_signal'},
    )


@receiver(user_logged_out)
def audit_user_logged_out(sender, request, user, **kwargs):
    log_user_action(
        action='auth.logout',
        verb='logout',
        user=user,
        obj=user,
        request=request,
        metadata={'source': 'auth_signal'},
    )
