"""Question bank list: scope, filters, and row helpers."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from core.models import Question
from subjects.models import GradeLevel, Strand, SubStrand, Subject


def base_questions_queryset(user):
    """Questions the user may browse in the bank."""
    qs = (
        Question.objects
        .select_related(
            'created_by',
            'sub_strand',
            'sub_strand__strand',
            'sub_strand__strand__subject',
            'sub_strand__strand__subject__grade_level',
        )
        .order_by('-created_at', 'uuid')
    )
    if user.is_admin_role or user.is_staff:
        return qs
    if user.is_teacher:
        from accounts.teacher_analytics import get_teacher_subjects

        subject_ids = list(get_teacher_subjects(user).values_list('pk', flat=True))
        if not subject_ids:
            return Question.objects.none()
        return qs.filter(sub_strand__strand__subject_id__in=subject_ids)
    return Question.objects.none()


def _grade_options_for_user(user):
    if user.is_admin_role or user.is_staff:
        return GradeLevel.objects.all().order_by('name')
    from accounts.teacher_analytics import get_teacher_subjects

    grade_ids = (
        get_teacher_subjects(user)
        .exclude(grade_level_id=None)
        .values_list('grade_level_id', flat=True)
        .distinct()
    )
    return GradeLevel.objects.filter(pk__in=grade_ids).order_by('name')


def resolve_bank_filters(user, *, grade_slug='', subject_slug='', strand_slug='', sub_strand_slug=''):
    """Resolve slugs to model instances within the user's visible curriculum."""
    grade = None
    subject = None
    strand = None
    sub_strand = None

    grade_options = list(_grade_options_for_user(user))

    if grade_slug:
        grade = next((g for g in grade_options if g.slug == grade_slug), None)

    subject_options = []
    if grade:
        subject_options = list(
            Subject.objects.filter(grade_level=grade, is_active=True).order_by('name')
        )
        if not (user.is_admin_role or user.is_staff):
            from accounts.teacher_analytics import get_teacher_subjects

            allowed_ids = set(get_teacher_subjects(user).values_list('pk', flat=True))
            subject_options = [s for s in subject_options if s.pk in allowed_ids]

    if subject_slug and subject_options:
        subject = next((s for s in subject_options if s.slug == subject_slug), None)

    strand_options = []
    if subject:
        strand_options = list(
            Strand.objects.filter(subject=subject, is_active=True).order_by('name')
        )

    if strand_slug and strand_options:
        strand = next((st for st in strand_options if st.slug == strand_slug), None)

    sub_strand_options = []
    if strand:
        sub_strand_options = list(
            SubStrand.objects.filter(strand=strand, is_active=True).order_by('name')
        )
    elif subject:
        sub_strand_options = list(
            SubStrand.objects.filter(strand__subject=subject, is_active=True)
            .select_related('strand')
            .order_by('strand__name', 'name')
        )

    if sub_strand_slug and sub_strand_options:
        sub_strand = next((ss for ss in sub_strand_options if ss.slug == sub_strand_slug), None)

    return {
        'grade': grade,
        'subject': subject,
        'strand': strand,
        'sub_strand': sub_strand,
        'grade_options': grade_options,
        'subject_options': subject_options,
        'strand_options': strand_options,
        'sub_strand_options': sub_strand_options,
    }


def apply_question_bank_filters(
    qs,
    *,
    grade=None,
    subject=None,
    strand=None,
    sub_strand=None,
    difficulty='',
    quiz_type='',
    status='',
    search='',
):
    if grade:
        qs = qs.filter(sub_strand__strand__subject__grade_level=grade)
    if subject:
        qs = qs.filter(sub_strand__strand__subject=subject)
    if strand:
        qs = qs.filter(sub_strand__strand=strand)
    if sub_strand:
        qs = qs.filter(sub_strand=sub_strand)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    if quiz_type:
        qs = qs.filter(quiz_type=quiz_type)
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    if search:
        qs = qs.filter(
            Q(quiz__icontains=search)
            | Q(sub_strand__name__icontains=search)
            | Q(sub_strand__strand__name__icontains=search)
            | Q(sub_strand__strand__subject__name__icontains=search)
        )
    return qs


def serialize_question_bank_row(question, user):
    subject = question.sub_strand.strand.subject
    grade = subject.grade_level
    preview = (question.quiz or '').strip()
    if len(preview) > 140:
        preview = preview[:140] + '…'

    detail_url = reverse('subjects:sub_strand_detail', kwargs={'slug': question.sub_strand.slug})
    if user.is_teacher and question.created_by_id == user.pk:
        detail_url = reverse(
            'accounts:teacher_question_detail',
            kwargs={'question_uuid': question.uuid},
        )

    from subjects.views import _user_can_toggle_question

    return {
        'uuid': question.uuid,
        'quiz_preview': preview,
        'grade': grade.name if grade else '—',
        'subject': subject.name,
        'strand': question.sub_strand.strand.name,
        'sub_strand': question.sub_strand.name,
        'difficulty': question.difficulty,
        'quiz_type': question.quiz_type,
        'is_active': question.is_active,
        'created_at': question.created_at,
        'created_by': question.created_by,
        'detail_url': detail_url,
        'sub_strand_url': reverse('subjects:sub_strand_detail', kwargs={'slug': question.sub_strand.slug}),
        'can_toggle': _user_can_toggle_question(user, question),
    }


def paginate_question_bank(queryset, page_number, per_page=30):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page_number)
