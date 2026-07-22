"""Date / period / status filters for the guardian learner dashboard."""

from calendar import monthrange
from datetime import date, datetime, timedelta

from django.db.models import Avg, Count, Max, Q
from django.utils import timezone


ACTIVITY_PERIOD_CHOICES = (
    ('week', 'This week'),
    ('2weeks', 'Last 2 weeks'),
    ('month', 'Last 30 days'),
)

PERFORMANCE_PERIOD_CHOICES = (
    ('week', 'This week'),
    ('month', 'Last 30 days'),
    ('6months', 'Last 6 months'),
    ('year', 'Last year'),
    ('all', 'All time'),
)

CHART_PERIOD_CHOICES = (
    ('week', 'Last 7 days'),
    ('month', 'Last 30 days'),
    ('3months', 'Last 3 months'),
    ('6months', 'Last 6 months'),
)

ANALYTICS_PERIOD_CHOICES = PERFORMANCE_PERIOD_CHOICES

STATUS_CHOICES = (
    ('all', 'All status'),
    ('completed', 'Completed'),
    ('ongoing', 'In progress'),
)

_PERIOD_DAYS = {
    'week': 7,
    '2weeks': 14,
    'month': 30,
    '3months': 90,
    '6months': 180,
    'year': 365,
    'all': None,
}


def _valid_choice(value, choices, default):
    allowed = {key for key, _ in choices}
    return value if value in allowed else default


def parse_dashboard_filters(request):
    """Read dashboard filter query params from the request."""
    performance_period = _valid_choice(
        request.GET.get('performance_period', '').strip(),
        PERFORMANCE_PERIOD_CHOICES,
        '6months',
    )
    return {
        'activity_period': _valid_choice(
            request.GET.get('activity_period', '').strip(),
            ACTIVITY_PERIOD_CHOICES,
            'week',
        ),
        'performance_period': performance_period,
        'chart_period': _valid_choice(
            request.GET.get('chart_period', '').strip(),
            CHART_PERIOD_CHOICES,
            'month',
        ),
        'analytics_period': _valid_choice(
            request.GET.get('analytics_period', '').strip() or performance_period,
            ANALYTICS_PERIOD_CHOICES,
            performance_period,
        ),
        'status': _valid_choice(
            request.GET.get('status', '').strip(),
            STATUS_CHOICES,
            'all',
        ),
        'month': _parse_month_param(request.GET.get('month', '').strip()),
        'grade': request.GET.get('grade', '').strip() or None,
    }


def _parse_month_param(raw):
    if not raw:
        return None
    try:
        datetime.strptime(raw, '%Y-%m')
    except ValueError:
        return None
    return raw


def month_date_range(month_str):
    """Inclusive calendar month range for YYYY-MM."""
    year, month = map(int, month_str.split('-'))
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def resolve_date_range(filters, period_key):
    """
    Return (start_date, end_date, label) for a period key.
    When filters['month'] is set, all sections use that calendar month.
    """
    if filters.get('month'):
        start, end = month_date_range(filters['month'])
        label = start.strftime('%B %Y')
        return start, end, label

    days = _PERIOD_DAYS.get(period_key)
    end = timezone.localdate()
    if days is None:
        return None, None, dict(PERFORMANCE_PERIOD_CHOICES).get(period_key, 'All time')

    start = end - timedelta(days=days - 1)
    label = dict(PERFORMANCE_PERIOD_CHOICES).get(
        period_key,
        dict(ACTIVITY_PERIOD_CHOICES).get(
            period_key,
            dict(CHART_PERIOD_CHOICES).get(period_key, ''),
        ),
    )
    return start, end, label


def filter_attempts_by_range(attempts_qs, start_date=None, end_date=None):
    if start_date:
        attempts_qs = attempts_qs.filter(created_at__date__gte=start_date)
    if end_date:
        attempts_qs = attempts_qs.filter(created_at__date__lte=end_date)
    return attempts_qs


def filter_attempts_by_status(attempts_qs, status):
    if status == 'completed':
        return attempts_qs.filter(is_complete=True)
    if status == 'ongoing':
        return attempts_qs.filter(is_complete=False)
    return attempts_qs


def build_activity_chart(attempts_qs, filters):
    """Bar chart data for the learning-activity card."""
    start, end, period_label = resolve_date_range(filters, filters['activity_period'])
    scoped = filter_attempts_by_range(attempts_qs, start, end)
    period_total = scoped.count()

    if not start or not end:
        start = timezone.localdate() - timedelta(days=6)
        end = timezone.localdate()

    span_days = (end - start).days + 1
    bars = []

    if span_days <= 14:
        for offset in range(span_days):
            day = start + timedelta(days=offset)
            count = scoped.filter(created_at__date=day).count()
            bars.append({
                'label': day.strftime('%a'),
                'value': count,
                'title': day.strftime('%b %d'),
            })
    else:
        cursor = start
        while cursor <= end:
            bucket_end = min(cursor + timedelta(days=6), end)
            count = scoped.filter(
                created_at__date__gte=cursor,
                created_at__date__lte=bucket_end,
            ).count()
            bars.append({
                'label': cursor.strftime('%d %b'),
                'value': count,
                'title': f'{cursor.strftime("%b %d")} – {bucket_end.strftime("%b %d")}',
            })
            cursor = bucket_end + timedelta(days=1)

    max_bar = max((bar['value'] for bar in bars), default=1) or 1

    subject_activity = list(
        scoped
        .filter(quiz__subject__isnull=False)
        .values('quiz__subject__name')
        .annotate(sessions=Count('uuid'))
        .order_by('-sessions')[:3]
    )

    return {
        'weekly_bars': bars,
        'max_bar': max_bar,
        'week_total': period_total,
        'subject_activity': subject_activity,
        'period_label': period_label,
    }


def build_performance_summary(attempts_qs, filters):
    """Gauge + breakdown for the performance card."""
    start, end, period_label = resolve_date_range(filters, filters['performance_period'])
    scoped = filter_attempts_by_range(attempts_qs, start, end)

    summary = scoped.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        avg_score=Avg('score'),
    )
    total = summary['total'] or 0
    completed = summary['completed'] or 0
    in_progress = total - completed
    avg_score = round(summary['avg_score']) if summary['avg_score'] is not None else 0

    completion_rate = round((completed / total) * 100) if total else 0
    in_progress_rate = round((in_progress / total) * 100) if total else 0
    participation = 100 if total else 0

    return {
        'avg_score': avg_score,
        'period_label': period_label,
        'performance_breakdown': [
            {'label': 'Participation', 'pct': participation, 'color': '#9B8FD9'},
            {'label': 'Completed', 'pct': completion_rate, 'color': '#6C9EFF'},
            {'label': 'In Progress', 'pct': in_progress_rate, 'color': '#F5C542'},
            {'label': 'Remaining', 'pct': max(0, 100 - completion_rate - in_progress_rate), 'color': '#E8E4F8'},
        ],
    }


def build_analytics_summary(attempts_qs, filters):
    """Summary metrics for metric cards and analytics sections."""
    start, end, period_label = resolve_date_range(filters, filters['analytics_period'])
    scoped = filter_attempts_by_range(attempts_qs, start, end)

    summary = scoped.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        avg_score=Avg('score'),
        best_score=Max('score'),
    )
    total = summary['total'] or 0
    completed = summary['completed'] or 0
    completion_rate = round((completed / total) * 100) if total else 0

    return {
        'total_attempts': total,
        'completed': completed,
        'completion_rate': completion_rate,
        'avg_score': round(summary['avg_score'], 1) if summary['avg_score'] is not None else 0,
        'best_score': summary['best_score'] or 0,
        'period_label': period_label,
        'attempts_qs': scoped,
    }


def chart_days_for_filters(filters):
    if filters.get('month'):
        start, end = month_date_range(filters['month'])
        return (end - start).days + 1
    return _PERIOD_DAYS.get(filters['chart_period'], 30) or 30


def build_dashboard_query_params(filters, student_uuid=None, **extra):
    """Build query params to preserve across filter forms and pagination."""
    params = {}
    if student_uuid:
        params['student'] = str(student_uuid)
    for key in (
        'grade', 'month', 'activity_period', 'performance_period',
        'chart_period', 'analytics_period', 'status',
    ):
        val = filters.get(key)
        if val:
            params[key] = val
    params.update(extra)
    return params
