"""Analytics and scope helpers for the teacher dashboard."""

from django.db.models import Avg, Count, Max, Q
from django.urls import reverse

from core.models import Question, Quiz, UserAttempts
from subjects.models import Subject, SubStrand, TeacherSubject


def teacher_can_access_subject(teacher, subject):
    """True if the teacher is assigned to or has created content in this subject."""
    if TeacherSubject.objects.filter(teacher=teacher, subject=subject).exists():
        return True
    if Question.objects.filter(
        created_by=teacher,
        sub_strand__strand__subject_id=subject.pk,
    ).exists():
        return True
    if Quiz.objects.filter(created_by=teacher, subject_id=subject.pk).exists():
        return True
    return False


def get_teacher_subjects(teacher):
    """Subjects the teacher is assigned to or has questions/quizzes in."""
    assigned_ids = TeacherSubject.objects.filter(teacher=teacher).values_list('subject_id', flat=True)
    question_subject_ids = (
        Question.objects
        .filter(created_by=teacher)
        .values_list('sub_strand__strand__subject_id', flat=True)
        .distinct()
    )
    quiz_subject_ids = (
        Quiz.objects
        .filter(created_by=teacher, subject_id__isnull=False)
        .values_list('subject_id', flat=True)
        .distinct()
    )
    subject_ids = set(assigned_ids) | set(question_subject_ids) | set(quiz_subject_ids)
    subject_ids.discard(None)
    return (
        Subject.objects
        .filter(pk__in=subject_ids, is_active=True)
        .select_related('grade_level', 'discipline')
        .order_by('grade_level__name', 'name')
    )


def _teacher_quizzes(teacher, subject=None):
    qs = Quiz.objects.filter(created_by=teacher, is_active=True)
    if subject is not None:
        qs = qs.filter(subject=subject)
    return qs


def _teacher_questions(teacher, subject=None):
    qs = Question.objects.filter(created_by=teacher)
    if subject is not None:
        qs = qs.filter(sub_strand__strand__subject=subject)
    return qs


def _attempts_for_teacher_quizzes(teacher, subject=None):
    quiz_ids = _teacher_quizzes(teacher, subject=subject).values_list('pk', flat=True)
    return UserAttempts.objects.filter(quiz_id__in=quiz_ids, is_active=True)


def build_teacher_summary(teacher):
    """Top-level metrics for the teacher dashboard."""
    questions = _teacher_questions(teacher)
    quizzes = _teacher_quizzes(teacher)
    attempts = _attempts_for_teacher_quizzes(teacher)

    attempt_summary = attempts.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        avg_score=Avg('score', filter=Q(is_complete=True)),
    )

    return {
        'subject_count': get_teacher_subjects(teacher).count(),
        'question_count': questions.count(),
        'active_questions': questions.filter(is_active=True).count(),
        'pending_questions': questions.filter(is_active=False).count(),
        'quiz_count': quizzes.count(),
        'attempt_count': attempt_summary['total'] or 0,
        'completed_attempts': attempt_summary['completed'] or 0,
        'avg_score': round(attempt_summary['avg_score'] or 0, 1),
    }


def build_teacher_subject_rows(teacher):
    """One summary row per subject the teacher teaches."""
    rows = []
    for subject in get_teacher_subjects(teacher):
        questions = _teacher_questions(teacher, subject=subject)
        quizzes = _teacher_quizzes(teacher, subject=subject)
        attempts = _attempts_for_teacher_quizzes(teacher, subject=subject)
        summary = attempts.aggregate(
            total=Count('uuid'),
            completed=Count('uuid', filter=Q(is_complete=True)),
            avg_score=Avg('score', filter=Q(is_complete=True)),
        )
        rows.append({
            'subject': subject,
            'question_count': questions.count(),
            'active_questions': questions.filter(is_active=True).count(),
            'quiz_count': quizzes.count(),
            'attempt_count': summary['total'] or 0,
            'avg_score': round(summary['avg_score'] or 0, 1),
            'detail_url': reverse('accounts:teacher_subject_detail', kwargs={'subject_id': subject.pk}),
        })
    return rows


def build_teacher_subject_detail(teacher, subject):
    """Detailed analytics for one subject."""
    questions = (
        _teacher_questions(teacher, subject=subject)
        .select_related('sub_strand', 'sub_strand__strand')
        .order_by('-created_at')
    )
    quizzes = (
        _teacher_quizzes(teacher, subject=subject)
        .select_related('strand', 'sub_strand')
        .annotate(
            attempt_count=Count('attempts', filter=Q(attempts__is_active=True)),
            completed_count=Count(
                'attempts',
                filter=Q(attempts__is_active=True, attempts__is_complete=True),
            ),
            avg_score=Avg('score', filter=Q(attempts__is_active=True, attempts__is_complete=True)),
        )
        .order_by('-created_at')
    )
    attempts = _attempts_for_teacher_quizzes(teacher, subject=subject)
    summary = attempts.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        avg_score=Avg('score', filter=Q(is_complete=True)),
        best_score=Max('score', filter=Q(is_complete=True)),
    )

    sub_strand_rows = []
    sub_strands = (
        SubStrand.objects
        .filter(strand__subject=subject, is_active=True)
        .select_related('strand')
        .annotate(
            question_count=Count(
                'questions',
                filter=Q(questions__created_by=teacher),
            ),
        )
        .filter(question_count__gt=0)
        .order_by('strand__order', 'order', 'name')
    )
    for sub_strand in sub_strands:
        sub_strand_rows.append({
            'name': sub_strand.name,
            'strand': sub_strand.strand.name,
            'question_count': sub_strand.question_count,
        })

    quiz_rows = []
    for quiz in quizzes:
        quiz_rows.append({
            'uuid': quiz.uuid,
            'title': quiz.title,
            'difficulty': quiz.difficulty,
            'strand': quiz.strand.name if quiz.strand_id else '—',
            'sub_strand': quiz.sub_strand.name if quiz.sub_strand_id else '—',
            'attempt_count': quiz.attempt_count or 0,
            'completed_count': quiz.completed_count or 0,
            'avg_score': round(quiz.avg_score or 0, 1),
            'analytics_url': reverse('core:exam_analytics', kwargs={'quiz_uuid': quiz.uuid}),
        })

    question_rows = []
    for question in questions[:50]:
        question_rows.append(_serialize_question_row(question))

    return {
        'subject': subject,
        'summary': {
            'question_count': questions.count(),
            'active_questions': questions.filter(is_active=True).count(),
            'pending_questions': questions.filter(is_active=False).count(),
            'quiz_count': quizzes.count(),
            'attempt_count': summary['total'] or 0,
            'completed_attempts': summary['completed'] or 0,
            'avg_score': round(summary['avg_score'] or 0, 1),
            'best_score': summary['best_score'] or 0,
        },
        'sub_strand_rows': sub_strand_rows,
        'quiz_rows': quiz_rows,
        'question_rows': question_rows,
    }


def build_teacher_question_rows(teacher, limit=25):
    """Recent questions for the dashboard list."""
    questions = (
        _teacher_questions(teacher)
        .select_related(
            'sub_strand',
            'sub_strand__strand',
            'sub_strand__strand__subject',
            'sub_strand__strand__subject__grade_level',
        )
        .order_by('-created_at')[:limit]
    )
    return [_serialize_question_row(question) for question in questions]


def _serialize_question_row(question):
    subject = question.sub_strand.strand.subject
    return {
        'uuid': question.uuid,
        'quiz': question.quiz,
        'quiz_preview': (question.quiz or '')[:120],
        'subject': subject.name,
        'grade': subject.grade_level.name if subject.grade_level_id else '—',
        'strand': question.sub_strand.strand.name,
        'sub_strand': question.sub_strand.name,
        'difficulty': question.difficulty,
        'quiz_type': question.quiz_type,
        'is_active': question.is_active,
        'status_label': 'Active' if question.is_active else 'Pending review',
        'created_at': question.created_at,
        'detail_url': reverse('accounts:teacher_question_detail', kwargs={'question_uuid': question.uuid}),
        'subject_detail_url': reverse(
            'accounts:teacher_subject_detail',
            kwargs={'subject_id': subject.pk},
        ),
    }


def build_teacher_question_detail(teacher, question):
    """Full detail for one question owned by the teacher."""
    subject = question.sub_strand.strand.subject
    options = list(
        question.options.filter(is_active=True).order_by('created_at').values(
            'uuid', 'option', 'is_correct', 'created_at',
        )
    )
    return {
        'question': question,
        'subject': subject,
        'strand': question.sub_strand.strand,
        'sub_strand': question.sub_strand,
        'options': options,
        'status_label': 'Active' if question.is_active else 'Pending review',
        'subject_detail_url': reverse(
            'accounts:teacher_subject_detail',
            kwargs={'subject_id': subject.pk},
        ),
    }
