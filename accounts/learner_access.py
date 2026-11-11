"""Who may view or manage a specific learner (Student)."""


def user_is_linked_to_learner(user, student):
    if not user.is_authenticated or student is None:
        return False
    return user.linked_students.filter(students=student).exists()


def user_can_view_learner(user, student):
    """
    Superusers may view any learner; everyone else only learners linked to their account.
    """
    if not user.is_authenticated or student is None:
        return False
    if user.is_superuser:
        return True
    return user_is_linked_to_learner(user, student)
