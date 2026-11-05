from subjects.grade_utils import GRADE_SLUG_ORDER

from .models import SubscriptionPlan


_PLAY_GROUP_TO_GRADE_3 = {'play-group', 'pp1', 'pp2', 'grade-1', 'grade-2', 'grade-3'}
_GRADE_4_TO_6 = {'grade-4', 'grade-5', 'grade-6'}
_GRADE_7_TO_12 = set(GRADE_SLUG_ORDER) - _PLAY_GROUP_TO_GRADE_3 - _GRADE_4_TO_6


def grade_band_for_student(student):
    if not student or not student.grade_level_id:
        return ''

    slug = student.grade_level.slug
    if slug in _PLAY_GROUP_TO_GRADE_3:
        return SubscriptionPlan.GradeBand.PLAY_GROUP_TO_GRADE_3
    if slug in _GRADE_4_TO_6:
        return SubscriptionPlan.GradeBand.GRADE_4_TO_6
    if slug in _GRADE_7_TO_12:
        return SubscriptionPlan.GradeBand.GRADE_7_TO_12
    return ''
