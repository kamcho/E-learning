"""Soft delete, restore, and permanent removal for users and learners."""

from django.db import transaction
from django.utils import timezone

from accounts.audit import log_user_action
from accounts.models import MyUser, Student


class MemberLifecycleError(ValueError):
    """Blocked or invalid delete/restore request."""


def _assert_platform_actor(actor):
    if not actor or not actor.is_authenticated:
        raise MemberLifecycleError('Not signed in.')
    if not actor.is_platform_admin:
        raise MemberLifecycleError('Admin permission required.')


def _assert_not_self(actor, target_user):
    if target_user.pk == actor.pk:
        raise MemberLifecycleError('You cannot delete or restore your own account from here.')


def _assert_can_touch_superuser(actor, target_user):
    if target_user.is_superuser and not actor.is_superuser:
        raise MemberLifecycleError('Only a superuser can change superuser accounts.')


def _remaining_superusers_qs():
    return MyUser.objects.filter(is_superuser=True, is_active=True)


def soft_delete_user(*, user, actor):
    _assert_platform_actor(actor)
    _assert_not_self(actor, user)
    _assert_can_touch_superuser(actor, user)
    if not user.is_active:
        return user
    user.is_active = False
    user.deleted_at = timezone.now()
    user.deleted_by = actor
    user.save(update_fields=['is_active', 'deleted_at', 'deleted_by', 'updated_at'])
    log_user_action(
        action='accounts:User.soft_delete',
        verb='delete',
        user=actor,
        obj=user,
        metadata={'hard': False},
    )
    return user


def restore_user(*, user, actor):
    _assert_platform_actor(actor)
    _assert_can_touch_superuser(actor, user)
    if user.is_active and not user.deleted_at:
        return user
    user.is_active = True
    user.deleted_at = None
    user.deleted_by = None
    user.save(update_fields=['is_active', 'deleted_at', 'deleted_by', 'updated_at'])
    log_user_action(
        action='accounts:User.restore',
        verb='update',
        user=actor,
        obj=user,
        metadata={'restored': True},
    )
    return user


@transaction.atomic
def hard_delete_user(*, user, actor):
    _assert_platform_actor(actor)
    _assert_not_self(actor, user)
    _assert_can_touch_superuser(actor, user)
    if user.is_superuser and _remaining_superusers_qs().count() <= 1:
        raise MemberLifecycleError('Cannot permanently delete the last active superuser.')

    label = str(user)[:200]
    pk = user.pk
    log_user_action(
        action='accounts:User.hard_delete',
        verb='delete',
        user=actor,
        object_type='accounts.MyUser',
        object_id=str(pk),
        object_repr=label,
        metadata={'hard': True},
    )
    user.delete()
    return pk


def soft_delete_student(*, student, actor):
    _assert_platform_actor(actor)
    if not student.is_active:
        return student
    student.is_active = False
    student.deleted_at = timezone.now()
    student.deleted_by = actor
    student.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])
    log_user_action(
        action='accounts:Student.soft_delete',
        verb='delete',
        user=actor,
        obj=student,
        metadata={'hard': False},
    )
    return student


def restore_student(*, student, actor):
    _assert_platform_actor(actor)
    if student.is_active and not student.deleted_at:
        return student
    student.is_active = True
    student.deleted_at = None
    student.deleted_by = None
    student.save(update_fields=['is_active', 'deleted_at', 'deleted_by'])
    log_user_action(
        action='accounts:Student.restore',
        verb='update',
        user=actor,
        obj=student,
        metadata={'restored': True},
    )
    return student


@transaction.atomic
def hard_delete_student(*, student, actor):
    _assert_platform_actor(actor)
    label = str(student)[:200]
    pk = str(student.pk)
    log_user_action(
        action='accounts:Student.hard_delete',
        verb='delete',
        user=actor,
        object_type='accounts.Student',
        object_id=pk,
        object_repr=label,
        metadata={'hard': True},
    )
    student.delete()
    return pk


def active_students_qs():
    return Student.objects.filter(is_active=True)


def students_for_directory_qs(*, status='active'):
    qs = Student.objects.select_related('grade_level')
    if status == 'active':
        return qs.filter(is_active=True)
    if status == 'inactive':
        return qs.filter(is_active=False)
    return qs


def users_for_directory_qs(*, status='all'):
    qs = MyUser.objects.order_by('-date_joined')
    if status == 'active':
        return qs.filter(is_active=True)
    if status == 'inactive':
        return qs.filter(is_active=False)
    return qs


def student_visible_to_user(user, student):
    """Guardians only see active learners linked to their account."""
    if not user.is_authenticated or student is None:
        return False
    if user.is_platform_admin:
        return True
    if not student.is_active:
        return False
    return user.linked_students.filter(students=student).exists()