"""Analytics builders for exam performance dashboards."""

from datetime import timedelta

from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone


PASS_SCORE = 70


def get_quiz_attempts_queryset(user, quiz):
    """Return attempts visible to this user for a given quiz."""
    from core.models import UserAttempts

    qs = (
        UserAttempts.objects
        .filter(quiz=quiz, is_active=True)
        .select_related('student', 'user')
    )

    if user.is_admin_role or user.is_staff:
        return qs
    if user.is_teacher and quiz.created_by_id == user.id:
        return qs
    if user.is_guardian:
        student_ids = []
        for link in user.linked_students.prefetch_related('students'):
            student_ids.extend(s.pk for s in link.students.all())
        return qs.filter(student_id__in=student_ids)
    return qs.none()


def can_view_exam_analytics(user, quiz):
    if user.is_admin_role or user.is_staff:
        return True
    if user.is_teacher and quiz.created_by_id == user.id:
        return True
    if user.is_guardian:
        return True
    return get_quiz_attempts_queryset(user, quiz).exists()


def build_exam_analytics(quiz, attempts_qs, days=14):
    """Build chart-ready analytics context for one exam."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)

    summary = attempts_qs.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        in_progress=Count('uuid', filter=Q(is_complete=False)),
        avg_score=Avg('score', filter=Q(is_complete=True)),
        best_score=Max('score', filter=Q(is_complete=True)),
    )

    total = summary['total'] or 0
    completed = summary['completed'] or 0
    in_progress = summary['in_progress'] or 0
    avg_score = round(summary['avg_score'] or 0, 1)
    best_score = summary['best_score'] or 0

    completed_qs = attempts_qs.filter(is_complete=True)
    passed = completed_qs.filter(score__gte=PASS_SCORE).count()
    pass_rate = round((passed / completed) * 100) if completed else 0
    completion_rate = round((completed / total) * 100) if total else 0

    current_avg = completed_qs.filter(updated_at__date__gte=start).aggregate(v=Avg('score'))['v'] or 0
    prev_avg = completed_qs.filter(
        updated_at__date__gte=prev_start,
        updated_at__date__lt=start,
    ).aggregate(v=Avg('score'))['v'] or 0

    if prev_avg:
        trend_pct = round(((current_avg - prev_avg) / prev_avg) * 100, 1)
    elif current_avg:
        trend_pct = 100.0
    else:
        trend_pct = 0.0

    daily_stats = {
        row['day']: row
        for row in (
            attempts_qs
            .filter(created_at__date__gte=start)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(
                avg_score=Avg('score', filter=Q(is_complete=True)),
                count=Count('uuid'),
                completed_count=Count('uuid', filter=Q(is_complete=True)),
            )
        )
    }

    trend_labels, trend_avg, trend_counts = [], [], []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        trend_labels.append(d.strftime('%d %b'))
        row = daily_stats.get(d)
        if row:
            trend_avg.append(round(row['avg_score'] or 0, 1))
            trend_counts.append(row['count'])
        else:
            trend_avg.append(0)
            trend_counts.append(0)

    distribution = {
        'below': completed_qs.filter(score__lt=40).count(),
        'developing': completed_qs.filter(score__gte=40, score__lt=PASS_SCORE).count(),
        'passed': completed_qs.filter(score__gte=PASS_SCORE).count(),
    }

    score_buckets = [
        {'label': '0–39%', 'count': completed_qs.filter(score__lt=40).count(), 'color': '#C1272D'},
        {'label': '40–69%', 'count': completed_qs.filter(score__gte=40, score__lt=PASS_SCORE).count(), 'color': '#D4A017'},
        {'label': '70–89%', 'count': completed_qs.filter(score__gte=70, score__lt=90).count(), 'color': '#0D8A4E'},
        {'label': '90–100%', 'count': completed_qs.filter(score__gte=90).count(), 'color': '#0a6b3f'},
    ]

    question_stats = _build_question_stats(quiz, completed_qs)

    recent_attempts = list(
        attempts_qs
        .select_related('quiz', 'student', 'user')
        .order_by('-updated_at')[:10]
    )

    top_attempts = list(
        completed_qs
        .select_related('student', 'user')
        .order_by('-score', '-updated_at')[:5]
    )

    return {
        'days': days,
        'period_label': f'{start.strftime("%b %d")} – {today.strftime("%b %d")}',
        'summary': {
            'total_attempts': total,
            'completed': completed,
            'in_progress': in_progress,
            'avg_score': avg_score,
            'best_score': best_score,
            'pass_rate': pass_rate,
            'completion_rate': completion_rate,
            'passed': passed,
        },
        'trend': {
            'labels': trend_labels,
            'avg_scores': trend_avg,
            'counts': trend_counts,
            'trend_pct': abs(trend_pct),
            'trend_up': trend_pct >= 0,
        },
        'distribution': distribution,
        'score_buckets': score_buckets,
        'question_stats': question_stats,
        'recent_attempts': recent_attempts,
        'top_attempts': top_attempts,
    }


def _build_question_stats(quiz, completed_qs):
    questions = list(
        quiz.questions.filter(is_active=True).prefetch_related('options').order_by('created_at')
    )
    if not questions:
        return []

    attempt_ids = list(completed_qs.values_list('pk', flat=True))
    from core.models import AttemptResponse
    stats = []
    for index, question in enumerate(questions, start=1):
        responses = AttemptResponse.objects.filter(
            attempt_id__in=attempt_ids,
            question=question,
        )
        answered = responses.count()
        correct = responses.filter(is_correct=True).count()

        pct = round((correct / answered) * 100) if answered else 0
        stats.append({
            'number': index,
            'label': (question.quiz or '')[:80],
            'pct': pct,
            'answered': answered,
            'correct': correct,
        })
    return stats
