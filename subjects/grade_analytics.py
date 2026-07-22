"""Analytics helpers for grade level list and detail pages."""

from django.db.models import Avg, Count, Max, Q
from django.urls import reverse

from accounts.models import Student
from core.models import Question, Quiz, UserAttempts
from subjects.grade_utils import GRADE_SLUG_ORDER
from subjects.models import GradeLevel, Strand, Subject


def sort_grade_levels(grade_levels):
    """Order grade levels in CBC progression."""

    def sort_key(grade):
        try:
            return GRADE_SLUG_ORDER.index(grade.slug)
        except ValueError:
            return 999

    return sorted(grade_levels, key=sort_key)


def _attempts_for_grade(grade_level):
    return UserAttempts.objects.filter(
        is_active=True,
        quiz__subject__grade_level_id=grade_level.pk,
    )


def build_grade_level_cards(grade_levels):
    """Summary metrics for each grade on the list page."""
    grade_levels = sort_grade_levels(grade_levels)
    if not grade_levels:
        return []

    grade_ids = [grade.pk for grade in grade_levels]

    subject_counts = {
        row['grade_level_id']: row['total']
        for row in (
            Subject.objects
            .filter(grade_level_id__in=grade_ids, is_active=True)
            .values('grade_level_id')
            .annotate(total=Count('pk'))
        )
    }
    student_counts = {
        row['grade_level_id']: row['total']
        for row in (
            Student.objects
            .filter(grade_level_id__in=grade_ids)
            .values('grade_level_id')
            .annotate(total=Count('pk'))
        )
    }
    quiz_counts = {
        row['subject__grade_level_id']: row['total']
        for row in (
            Quiz.objects
            .filter(subject__grade_level_id__in=grade_ids, is_active=True)
            .values('subject__grade_level_id')
            .annotate(total=Count('pk'))
        )
    }

    attempt_stats = {
        row['quiz__subject__grade_level_id']: row
        for row in (
            UserAttempts.objects
            .filter(
                is_active=True,
                quiz__subject__grade_level_id__in=grade_ids,
            )
            .values('quiz__subject__grade_level_id')
            .annotate(
                total=Count('uuid'),
                completed=Count('uuid', filter=Q(is_complete=True)),
                avg_score=Avg('score', filter=Q(is_complete=True)),
            )
        )
    }

    cards = []
    for grade in grade_levels:
        attempts = attempt_stats.get(grade.pk, {})
        cards.append({
            'grade': grade,
            'subject_count': subject_counts.get(grade.pk, 0),
            'student_count': student_counts.get(grade.pk, 0),
            'quiz_count': quiz_counts.get(grade.pk, 0),
            'attempt_count': attempts.get('total', 0),
            'completed_attempts': attempts.get('completed', 0),
            'avg_score': round(attempts.get('avg_score') or 0, 1),
            'detail_url': reverse('subjects:grade_level_detail', kwargs={'slug': grade.slug}),
        })
    return cards


def build_grade_detail_summary(grade_level):
    """Top-level metrics for a single grade."""
    subjects = Subject.objects.filter(grade_level=grade_level, is_active=True)
    attempts = _attempts_for_grade(grade_level)
    summary = attempts.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        avg_score=Avg('score', filter=Q(is_complete=True)),
        best_score=Max('score', filter=Q(is_complete=True)),
        learners=Count('student', distinct=True),
    )
    return {
        'subject_count': subjects.count(),
        'student_count': Student.objects.filter(grade_level=grade_level).count(),
        'quiz_count': Quiz.objects.filter(subject__grade_level=grade_level, is_active=True).count(),
        'strand_count': Strand.objects.filter(subject__grade_level=grade_level, is_active=True).count(),
        'question_count': Question.objects.filter(
            sub_strand__strand__subject__grade_level=grade_level,
            is_active=True,
        ).count(),
        'attempt_count': summary['total'] or 0,
        'completed_attempts': summary['completed'] or 0,
        'active_learners': summary['learners'] or 0,
        'avg_score': round(summary['avg_score'] or 0, 1),
        'best_score': summary['best_score'] or 0,
    }


def build_subject_analytics_rows(grade_level):
    """Per-subject analytics for the grade detail page."""
    subjects = (
        Subject.objects
        .filter(grade_level=grade_level, is_active=True)
        .select_related('discipline')
        .order_by('name')
    )

    subject_ids = [subject.pk for subject in subjects]
    if not subject_ids:
        return []

    quiz_counts = {
        row['subject_id']: row['total']
        for row in (
            Quiz.objects
            .filter(subject_id__in=subject_ids, is_active=True)
            .values('subject_id')
            .annotate(total=Count('pk'))
        )
    }
    strand_counts = {
        row['subject_id']: row['total']
        for row in (
            Strand.objects
            .filter(subject_id__in=subject_ids, is_active=True)
            .values('subject_id')
            .annotate(total=Count('pk'))
        )
    }
    question_counts = {
        row['sub_strand__strand__subject_id']: row['total']
        for row in (
            Question.objects
            .filter(
                sub_strand__strand__subject_id__in=subject_ids,
                is_active=True,
            )
            .values('sub_strand__strand__subject_id')
            .annotate(total=Count('pk'))
        )
    }
    attempt_stats = {
        row['quiz__subject_id']: row
        for row in (
            UserAttempts.objects
            .filter(is_active=True, quiz__subject_id__in=subject_ids)
            .values('quiz__subject_id')
            .annotate(
                attempts=Count('uuid'),
                completed=Count('uuid', filter=Q(is_complete=True)),
                avg_score=Avg('score', filter=Q(is_complete=True)),
                best_score=Max('score', filter=Q(is_complete=True)),
                learners=Count('student', distinct=True),
            )
        )
    }

    rows = []
    for subject in subjects:
        stats = attempt_stats.get(subject.pk, {})
        rows.append({
            'subject': subject,
            'discipline': subject.discipline.name,
            'strand_count': strand_counts.get(subject.pk, 0),
            'quiz_count': quiz_counts.get(subject.pk, 0),
            'question_count': question_counts.get(subject.pk, 0),
            'attempt_count': stats.get('attempts', 0),
            'completed_attempts': stats.get('completed', 0),
            'learner_count': stats.get('learners', 0),
            'avg_score': round(stats.get('avg_score') or 0, 1),
            'best_score': stats.get('best_score') or 0,
            'detail_url': reverse('subjects:subject_detail', kwargs={'slug': subject.slug}),
        })

    rows.sort(key=lambda row: (-row['attempt_count'], row['subject'].name))
    return rows
