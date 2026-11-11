"""Aggregate learner performance into KICD-style discipline group cards."""

from django.db.models import Avg, Count, Q

from subjects.models import Subject

CLUSTER_SPECS = (
    {
        'key': 'math-sciences',
        'eyebrow': 'Mathematics & Science',
        'title': 'Math & Sciences',
        'theme': 'teal',
        'icon': '🔬',
        'discipline_slugs': frozenset({'mathematics-science'}),
    },
    {
        'key': 'technical-applied',
        'eyebrow': 'Technical & Applied',
        'title': 'Technical & Applied',
        'theme': 'purple',
        'icon': '🛠️',
        'discipline_slugs': frozenset({'technical-applied'}),
    },
    {
        'key': 'others',
        'eyebrow': 'Languages, arts & more',
        'title': 'Others',
        'theme': 'amber',
        'icon': '📚',
        'discipline_slugs': None,
    },
)

_PRIMARY_SLUGS = frozenset({'mathematics-science', 'technical-applied'})


def _subjects_for_cluster(grade_level, spec):
    qs = Subject.objects.filter(grade_level=grade_level, is_active=True).select_related('discipline')
    slugs = spec['discipline_slugs']
    if slugs is None:
        return qs.exclude(discipline__slug__in=_PRIMARY_SLUGS)
    return qs.filter(discipline__slug__in=slugs)


def build_discipline_cluster_cards(attempts_qs, grade_level):
    """Three summary cards: Math & Sciences, Technical & Applied, Others."""
    if not grade_level:
        return []

    cards = []
    for spec in CLUSTER_SPECS:
        subjects = list(_subjects_for_cluster(grade_level, spec))
        subject_ids = [s.pk for s in subjects]
        total_subjects = len(subjects)

        default_headlines = {
            'math-sciences': 'Numbers, inquiry & experiments',
            'technical-applied': 'Hands-on skills & applied work',
            'others': 'Languages, arts & citizenship',
        }

        if not subject_ids:
            cards.append({
                **{k: spec[k] for k in ('key', 'eyebrow', 'title', 'theme', 'icon')},
                'headline': default_headlines.get(spec['key'], spec['title']),
                'badge_pct': 0,
                'badge_label': '—',
                'avg_score': 0,
                'attempts': 0,
                'subjects_touched': 0,
                'subject_total': 0,
                'progress_pct': 0,
                'has_data': False,
            })
            continue

        grade_attempts = attempts_qs.filter(
            quiz__subject_id__in=subject_ids,
            quiz__subject__grade_level_id=grade_level.pk,
        )
        agg = grade_attempts.aggregate(
            attempts=Count('uuid'),
            completed=Count('uuid', filter=Q(is_complete=True)),
            avg_score=Avg('score', filter=Q(is_complete=True)),
        )
        touched_ids = set(
            grade_attempts.values_list('quiz__subject_id', flat=True).distinct()
        )
        subjects_touched = len(touched_ids)
        avg = agg['avg_score']
        avg_rounded = round(avg) if avg is not None else 0
        progress_pct = (
            round((subjects_touched / total_subjects) * 100)
            if total_subjects else 0
        )

        per_subject = (
            grade_attempts.filter(is_complete=True)
            .values('quiz__subject__name')
            .annotate(avg=Avg('score'), n=Count('uuid'))
            .order_by('-avg', '-n')
        )
        top_row = per_subject.first()
        if top_row and top_row['quiz__subject__name']:
            headline = top_row['quiz__subject__name']
        elif subjects_touched:
            headline = default_headlines.get(spec['key'], spec['title'])
        else:
            headline = 'Ready to start practising'

        has_completed = bool(agg['completed'])
        badge_pct = avg_rounded if has_completed else progress_pct
        badge_label = f'{badge_pct}%' if (has_completed or subjects_touched) else '—'

        cards.append({
            **{k: spec[k] for k in ('key', 'eyebrow', 'title', 'theme', 'icon')},
            'headline': headline,
            'badge_pct': badge_pct,
            'badge_label': badge_label,
            'avg_score': avg_rounded,
            'attempts': agg['attempts'] or 0,
            'subjects_touched': subjects_touched,
            'subject_total': total_subjects,
            'progress_pct': progress_pct,
            'has_data': bool(agg['attempts']),
        })

    return cards
