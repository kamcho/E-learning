"""Grade-level ordering and learner eligibility for exam filtering."""

from subjects.models import GradeLevel

# Canonical CBC progression (matches seed_kicd_curriculum.GRADE_LEVELS).
GRADE_SLUG_ORDER = [
    'pp1', 'pp2',
    'grade-1', 'grade-2', 'grade-3',
    'grade-4', 'grade-5', 'grade-6',
    'grade-7', 'grade-8', 'grade-9',
    'grade-10', 'grade-11', 'grade-12',
]

BAND_SLUGS = {
    'ecde': 'ECDE',
    'lower-primary': 'Lower Primary',
    'upper-primary': 'Upper Primary',
    'junior-secondary': 'Junior Secondary',
    'senior-secondary': 'Senior Secondary',
}


def grade_level_rank(grade_level):
    """Return 0-based rank for a grade level, or None if unknown."""
    if not grade_level:
        return None
    try:
        return GRADE_SLUG_ORDER.index(grade_level.slug)
    except ValueError:
        return None


def band_slug_for_level(level_name):
    """Map GradeLevel.level display value to a URL-friendly slug."""
    for slug, name in BAND_SLUGS.items():
        if name == level_name:
            return slug
    return None


def eligible_grade_levels_for_student(student):
    """
    Grades a learner may access: same CBC band as their enrollment,
    from the start of that band through their current grade (inclusive).
    """
    if not student or not student.grade_level_id:
        return GradeLevel.objects.none()

    gl = student.grade_level
    student_rank = grade_level_rank(gl)
    if student_rank is None:
        return GradeLevel.objects.filter(pk=gl.pk)

    eligible_slugs = GRADE_SLUG_ORDER[: student_rank + 1]
    return (
        GradeLevel.objects
        .filter(slug__in=eligible_slugs, level=gl.level)
        .order_by('name')
    )


def is_grade_eligible_for_student(student, grade_level):
    if not student or not grade_level:
        return False
    return eligible_grade_levels_for_student(student).filter(pk=grade_level.pk).exists()


def eligible_grade_level_ids_for_student(student):
    return list(eligible_grade_levels_for_student(student).values_list('pk', flat=True))
