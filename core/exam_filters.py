"""Curriculum-scoped filter helpers for the exams list."""

from subjects.models import GradeLevel, Strand, Subject, SubStrand

from core.models import Quiz

DEFAULT_EXAMS_GRADE_SLUG = 'grade-6'


def active_quizzes_queryset():
    return (
        Quiz.objects
        .filter(is_active=True)
        .select_related('subject', 'subject__grade_level', 'strand', 'sub_strand')
    )


def subjects_for_wizard(quiz_qs, grade_level=None):
    """All active curriculum subjects for a grade (wizard — includes zero-quiz subjects)."""
    qs = Subject.objects.filter(is_active=True)
    if grade_level:
        qs = qs.filter(grade_level=grade_level)
    return qs.order_by('name')


def strands_for_wizard(quiz_qs, subject=None):
    """All active strands for a subject (wizard — includes zero-quiz strands)."""
    if not subject:
        return Strand.objects.none()
    return Strand.objects.filter(subject=subject, is_active=True).order_by('order', 'name')


def sub_strands_for_wizard(quiz_qs, strand=None):
    """All active sub-strands for a strand (wizard — includes zero-quiz sub-strands)."""
    if not strand:
        return SubStrand.objects.none()
    return SubStrand.objects.filter(strand=strand, is_active=True).order_by('order', 'name')


def subjects_for_quizzes(quiz_qs, grade_level=None):
    """Subjects that have at least one quiz in the queryset."""
    qs = quiz_qs.exclude(subject_id__isnull=True)
    if grade_level:
        qs = qs.filter(subject__grade_level=grade_level)
    subject_ids = qs.values_list('subject_id', flat=True).distinct()
    return Subject.objects.filter(pk__in=subject_ids, is_active=True).order_by('name')


def strands_for_quizzes(quiz_qs, subject=None):
    qs = quiz_qs.exclude(strand_id__isnull=True)
    if subject:
        qs = qs.filter(subject=subject)
    strand_ids = qs.values_list('strand_id', flat=True).distinct()
    return Strand.objects.filter(pk__in=strand_ids, is_active=True).order_by('order', 'name')


def sub_strands_for_quizzes(quiz_qs, strand=None, subject=None):
    qs = quiz_qs.exclude(sub_strand_id__isnull=True)
    if strand:
        qs = qs.filter(strand=strand)
    elif subject:
        qs = qs.filter(subject=subject)
    sub_ids = qs.values_list('sub_strand_id', flat=True).distinct()
    return SubStrand.objects.filter(pk__in=sub_ids, is_active=True).order_by('order', 'name')


def quiz_count_for_subject(quiz_qs, subject):
    return quiz_qs.filter(subject=subject).count()


def quizzes_for_subject_only(quiz_qs, subject=None):
    """Quizzes scoped to a subject with no strand or sub-strand."""
    qs = quiz_qs.filter(strand__isnull=True, sub_strand__isnull=True)
    if subject:
        qs = qs.filter(subject=subject)
    return qs


def quiz_count_for_subject_only(quiz_qs, subject):
    return quizzes_for_subject_only(quiz_qs, subject).count()


def quiz_count_for_strand(quiz_qs, strand):
    return quiz_qs.filter(strand=strand).count()


def quiz_count_for_sub_strand(quiz_qs, sub_strand):
    return quiz_qs.filter(sub_strand=sub_strand).count()


def grades_for_wizard(quiz_qs, filterable_grade_levels):
    """Grade options with exam counts for the exam finder wizard."""
    return [
        {
            'slug': gl.slug,
            'name': gl.name,
            'count': quiz_qs.filter(subject__grade_level=gl).count(),
        }
        for gl in filterable_grade_levels
    ]


def serialize_filter_options(quiz_qs, *, subject=None, strand=None):
    """Build JSON-serializable options for cascading exam filters."""
    subjects = [
        {
            'slug': s.slug,
            'name': s.name,
            'grade': s.grade_level.name if s.grade_level_id else '',
            'count': quiz_count_for_subject(quiz_qs, s),
        }
        for s in subjects_for_quizzes(quiz_qs)
    ]
    strands = []
    sub_strands = []

    if subject:
        strands = [
            {
                'slug': st.slug,
                'name': st.name,
                'count': quiz_count_for_strand(quiz_qs, st),
            }
            for st in strands_for_quizzes(quiz_qs, subject=subject)
        ]

    if strand:
        sub_strands = [
            {
                'slug': ss.slug,
                'name': ss.name,
                'count': quiz_count_for_sub_strand(quiz_qs, ss),
            }
            for ss in sub_strands_for_quizzes(quiz_qs, strand=strand)
        ]

    return {
        'subjects': subjects,
        'strands': strands,
        'sub_strands': sub_strands,
    }


def serialize_wizard_options(
    quiz_qs,
    filterable_grade_levels,
    *,
    subject=None,
    strand=None,
    grade_level=None,
    student=None,
    include_grades=False,
):
    """JSON payload for the interactive exam finder wizard."""
    subjects = [
        {
            'slug': s.slug,
            'name': s.name,
            'grade': s.grade_level.name if s.grade_level_id else '',
            'count': quiz_count_for_subject(quiz_qs, s),
            'custom_available': True,
        }
        for s in subjects_for_wizard(quiz_qs, grade_level=grade_level)
    ]
    strands = []
    sub_strands = []

    if subject:
        strands = [
            {
                'slug': st.slug,
                'name': st.name,
                'count': quiz_count_for_strand(quiz_qs, st),
                'custom_available': True,
            }
            for st in strands_for_wizard(quiz_qs, subject=subject)
        ]

    if strand:
        sub_strands = [
            {
                'slug': ss.slug,
                'name': ss.name,
                'count': quiz_count_for_sub_strand(quiz_qs, ss),
                'custom_available': True,
            }
            for ss in sub_strands_for_wizard(quiz_qs, strand=strand)
        ]

    payload = {
        'subjects': subjects,
        'strands': strands,
        'sub_strands': sub_strands,
        'total_exams': quiz_qs.count(),
    }
    if student:
        payload['student'] = {
            'uuid': str(student.uuid),
            'first_name': student.first_name,
            'grade_name': student.grade_level.name if student.grade_level_id else '',
        }
    if include_grades and filterable_grade_levels.exists():
        payload['grades'] = [
            {
                'slug': gl.slug,
                'name': gl.name,
                'count': quiz_qs.filter(subject__grade_level=gl).count(),
                'custom_available': True,
            }
            for gl in filterable_grade_levels
        ]
    else:
        payload['grades'] = []
    return payload


def resolve_grade_from_slug(slug, filterable_grade_levels):
    if not slug:
        return None
    gl = GradeLevel.objects.filter(slug=slug).first()
    if not gl:
        return None
    if filterable_grade_levels.exists() and not filterable_grade_levels.filter(pk=gl.pk).exists():
        return None
    return gl
