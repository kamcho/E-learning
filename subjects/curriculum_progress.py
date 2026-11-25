"""Question-bank progress against per-sub-strand question targets."""

from collections import defaultdict

from django.db.models import Count

from core.models import Question

from .models import SubStrand

SUBSTRAND_QUESTION_TARGET = 7
# Exam Center subject cards: share of sub-strands with at least this many bank questions.
SUBSTRAND_EXAMS_READY_MIN = 10


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
        'coverage_pct': 0,
        'ready_substrands_at_exams_min': 0,
        'exams_ready_min_questions': SUBSTRAND_EXAMS_READY_MIN,
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

    subs_by_subject = defaultdict(list)
    for row in sub_strands:
        subs_by_subject[row['strand__subject_id']].append(row)

    for subject_id, pcts in pct_by_subject.items():
        ready = sum(1 for pct in pcts if pct >= 100)
        subject_subs = subs_by_subject.get(subject_id, [])
        ready_at_exams_min = sum(
            1 for row in subject_subs
            if question_counts.get(row['pk'], 0) >= SUBSTRAND_EXAMS_READY_MIN
        )
        sub_count = len(subject_subs)
        result[subject_id] = {
            'progress_pct': round(sum(pcts) / len(pcts)) if pcts else 0,
            'substrand_count': sub_count,
            'ready_count': ready,
            'question_count': questions_by_subject[subject_id],
            'coverage_pct': round(100 * ready_at_exams_min / sub_count) if sub_count else 0,
            'ready_substrands_at_exams_min': ready_at_exams_min,
            'exams_ready_min_questions': SUBSTRAND_EXAMS_READY_MIN,
        }
    return result


def subject_meets_exams_ready_rule(stats):
    """True when every active sub-strand has at least SUBSTRAND_EXAMS_READY_MIN questions."""
    substrand_count = stats.get('substrand_count') or 0
    if substrand_count == 0:
        return False
    return stats.get('ready_substrands_at_exams_min') == substrand_count


def build_subjects_exams_ready_summary(subject_ids):
    """
    Share of subjects (with at least one active sub-strand) where every
    sub-strand has SUBSTRAND_EXAMS_READY_MIN or more active questions.
    """
    subject_ids = [sid for sid in subject_ids if sid]
    if not subject_ids:
        return {
            'subjects_exams_ready_pct': 0,
            'subjects_exams_ready_count': 0,
            'subjects_exams_ready_total': 0,
            'exams_ready_min_questions': SUBSTRAND_EXAMS_READY_MIN,
        }

    progress = build_curriculum_progress_by_subject(subject_ids)
    eligible = 0
    ready = 0
    for subject_id in subject_ids:
        stats = progress.get(subject_id, {})
        if not stats.get('substrand_count'):
            continue
        eligible += 1
        if subject_meets_exams_ready_rule(stats):
            ready += 1

    return {
        'subjects_exams_ready_pct': round(100 * ready / eligible) if eligible else 0,
        'subjects_exams_ready_count': ready,
        'subjects_exams_ready_total': eligible,
        'exams_ready_min_questions': SUBSTRAND_EXAMS_READY_MIN,
    }
