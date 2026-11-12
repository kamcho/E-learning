"""Card-ready performance breakdown: one subject, gauge + top strand bars."""

from collections import defaultdict

from django.db.models import Avg, Count

from subjects.models import Strand

STRAND_BAR_COLORS = (
    '#3b82f6',
    '#8b5cf6',
    '#ec4899',
    '#22c55e',
    '#f59e0b',
    '#06b6d4',
)

MAX_STRANDS_ON_CARD = 4


def build_subject_performance_cards(attempts_qs, subject_breakdown):
    """
    Enrich grade subject breakdown rows for the analytics card grid.

    Each card shows overall average score and up to four strand score bars.
    """
    if not subject_breakdown:
        return []

    subject_ids = [row['subject_id'] for row in subject_breakdown]

    strand_stats = {
        (row['quiz__subject_id'], row['quiz__strand_id']): row
        for row in (
            attempts_qs.filter(
                quiz__subject_id__in=subject_ids,
                quiz__strand__isnull=False,
                is_complete=True,
            )
            .values('quiz__subject_id', 'quiz__strand_id')
            .annotate(avg_score=Avg('score'), attempts=Count('uuid'))
        )
    }

    strands_by_subject = defaultdict(list)
    for strand in (
        Strand.objects.filter(subject_id__in=subject_ids, is_active=True)
        .order_by('subject_id', 'order', 'name')
        .values('pk', 'subject_id', 'name')
    ):
        stats = strand_stats.get((strand['subject_id'], strand['pk']))
        avg = stats['avg_score'] if stats and stats['avg_score'] is not None else None
        attempts = stats['attempts'] if stats else 0
        strands_by_subject[strand['subject_id']].append({
            'name': strand['name'],
            'pct': int(round(avg)) if avg is not None else 0,
            'attempts': attempts,
            'has_score': avg is not None,
        })

    cards = []
    for row in subject_breakdown:
        subject_id = row['subject_id']
        strands = list(strands_by_subject.get(subject_id, []))
        top_strands = strands[:MAX_STRANDS_ON_CARD]
        for index, strand_row in enumerate(top_strands):
            strand_row['color'] = STRAND_BAR_COLORS[index % len(STRAND_BAR_COLORS)]

        overall = row['avg_score'] if row['attempts'] and row['avg_score'] is not None else 0
        cards.append({
            **row,
            'overall_pct': int(round(overall)),
            'strands': top_strands,
            'strand_total': len(strands),
        })

    return cards
