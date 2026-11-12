"""Month calendar highlighting days the learner took exams."""

from calendar import monthcalendar, month_name
from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone


def parse_calendar_month(raw):
    """Parse YYYY-MM; default to current local month."""
    today = timezone.localdate()
    if not raw or not isinstance(raw, str):
        return today.year, today.month
    raw = raw.strip()
    if len(raw) != 7 or raw[4] != '-':
        return today.year, today.month
    try:
        year = int(raw[:4])
        month = int(raw[5:7])
        if month < 1 or month > 12:
            raise ValueError
        return year, month
    except ValueError:
        return today.year, today.month


def build_exam_activity_calendar(student, year, month):
    from core.models import UserAttempts

    today = timezone.localdate()

    attempt_counts = {
        row['day']: row['count']
        for row in (
            UserAttempts.objects.filter(
                student=student,
                is_active=True,
                created_at__year=year,
                created_at__month=month,
            )
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('uuid'))
        )
    }

    weeks = []
    for week in monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append({
                    'day': None,
                    'in_month': False,
                    'has_exam': False,
                    'is_today': False,
                    'count': 0,
                })
                continue
            cell_date = date(year, month, day)
            count = attempt_counts.get(cell_date, 0)
            row.append({
                'day': day,
                'in_month': True,
                'has_exam': count > 0,
                'is_today': cell_date == today,
                'count': count,
            })
        weeks.append(row)

    prev_anchor = date(year, month, 1) - timedelta(days=1)
    if month == 12:
        next_anchor = date(year + 1, 1, 1)
    else:
        next_anchor = date(year, month + 1, 1)

    return {
        'year': year,
        'month': month,
        'month_label': f'{month_name[month]} {year}',
        'weeks': weeks,
        'exam_days_count': len(attempt_counts),
        'prev_month': f'{prev_anchor.year}-{prev_anchor.month:02d}',
        'next_month': f'{next_anchor.year}-{next_anchor.month:02d}',
        'cal_month': f'{year}-{month:02d}',
    }
