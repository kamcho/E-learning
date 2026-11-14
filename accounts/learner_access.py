"""Who may view or manage a specific learner (Student)."""

from accounts.member_lifecycle import student_visible_to_user


def user_is_linked_to_learner(user, student):
    if not user.is_authenticated or student is None:
        return False
    if not student.is_active:
        return False
    return user.linked_students.filter(students=student).exists()


def user_can_view_learner(user, student):
    """
    Platform admins may view any learner (including soft-deleted).
    Guardians only see active learners linked to their account.
    """
    return student_visible_to_user(user, student)
