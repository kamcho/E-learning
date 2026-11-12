"""Question-bank progress against the 7-questions-per-sub-strand target."""

from collections import defaultdict

from django.db.models import Count

from core.models import Question

from .models import SubStrand

SUBSTRAND_QUESTION_TARGET = 7


def substrand_question_progress_pct(question_count, target=SUBSTRAND_QUESTION_TARGET):
    """Return 0–100 completion for one sub-strand."""
    if target <= 0:
        return 0
    count = max(0, int(question_count or 0))
    return min(100, round(100 * count / target))


def build_curriculum_progress_by_subject(subject_ids):
    """
    For each subject id, return aggregate progress across active sub-strands.

    Each sub-strand contributes min(100%, questions/7). Subject progress is the
    arithmetic mean of those percentages (0 if there are no sub-strands).
    """
    subject_ids = [sid for sid in subject_ids if sid]
    default = {
        'progress_pct': 0,
        'substrand_count': 0,
        'ready_count': 0,
        'question_count': 0,
    }
    if not subject_ids:
        return {}

    result = {sid: dict(default) for sid in subject_ids}
    sub_strands = list(
        SubStrand.objects.filter(
            strand__subject_id__in=subject_ids,
            is_active=True,
            strand__is_active=True,
        ).values('pk', 'strand__subject_id')
    )
    if not sub_strands:
        return result

    sub_ids = [row['pk'] for row in sub_strands]
    question_counts = dict(
        Question.objects.filter(sub_strand_id__in=sub_ids, is_active=True)
        .values('sub_strand_id')
        .annotate(total=Count('pk'))
        .values_list('sub_strand_id', 'total')
    )

    pct_by_subject = defaultdict(list)
    questions_by_subject = defaultdict(int)

    for row in sub_strands:
        subject_id = row['strand__subject_id']
        q_count = question_counts.get(row['pk'], 0)
        questions_by_subject[subject_id] += q_count
        pct_by_subject[subject_id].append(substrand_question_progress_pct(q_count))

    for subject_id, pcts in pct_by_subject.items():
        ready = sum(1 for pct in pcts if pct >= 100)
        result[subject_id] = {
            'progress_pct': round(sum(pcts) / len(pcts)) if pcts else 0,
            'substrand_count': len(pcts),
            'ready_count': ready,
            'question_count': questions_by_subject[subject_id],
        }
    return result
