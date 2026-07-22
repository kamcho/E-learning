"""Strand / sub-strand test progress for a learner within a subject."""

from django.db.models import Count, Prefetch

from subjects.models import Strand, SubStrand


def build_subject_strand_progress(student, subject):
    """
    Build strand rows with sub-strand completion from completed quiz attempts.

    A sub-strand is complete when completed tests in that sub-strand are
  >= sub_strand.test_count (default 2).
    """
    from core.models import UserAttempts

    attempt_counts = {
        row['quiz__sub_strand_id']: row['completed_tests']
        for row in UserAttempts.objects.filter(
            student=student,
            is_active=True,
            is_complete=True,
            quiz__subject_id=subject.pk,
            quiz__sub_strand__isnull=False,
        )
        .values('quiz__sub_strand_id')
        .annotate(completed_tests=Count('uuid'))
    }

    strands = (
        Strand.objects
        .filter(subject=subject, is_active=True)
        .prefetch_related(
            Prefetch(
                'sub_strands',
                queryset=SubStrand.objects.filter(is_active=True).order_by('order', 'name'),
            ),
        )
        .order_by('order', 'name')
    )

    strand_rows = []
    total_substrands = 0
    completed_substrands = 0

    for strand in strands:
        substrand_rows = []
        strand_completed = 0
        strand_total = 0

        for sub_strand in strand.sub_strands.all():
            tests_taken = attempt_counts.get(sub_strand.pk, 0)
            required = sub_strand.test_count or 2
            is_complete = tests_taken >= required

            strand_total += 1
            total_substrands += 1
            if is_complete:
                strand_completed += 1
                completed_substrands += 1

            substrand_rows.append({
                'sub_strand': sub_strand,
                'tests_taken': tests_taken,
                'required': required,
                'is_complete': is_complete,
            })

        strand_pct = round((strand_completed / strand_total) * 100) if strand_total else 0
        strand_rows.append({
            'strand': strand,
            'substrands': substrand_rows,
            'completed_count': strand_completed,
            'total_count': strand_total,
            'pct': strand_pct,
        })

    overall_pct = round((completed_substrands / total_substrands) * 100) if total_substrands else 0

    return {
        'strands': strand_rows,
        'total_substrands': total_substrands,
        'completed_substrands': completed_substrands,
        'overall_pct': overall_pct,
    }
