"""
Suggest CBC Senior School pathways from a learner's best-performing subjects.

Uses completed exam attempts, subject discipline → pathway weights, and weighted averages.
"""

from django.db.models import Avg, Count, Max

MIN_COMPLETED_ATTEMPTS = 1
MIN_PATHWAY_SUBJECTS = 1


def _grade_context_label(grade_level):
    if not grade_level:
        return 'CBC'
    level = grade_level.level or ''
    if level == 'Senior Secondary':
        return 'Senior School pathway fit'
    if level == 'Junior Secondary':
        return 'Junior School pathway indicators'
    return 'Early pathway indicators'


def build_pathway_suggestions(student, grade_level=None):
    """
    Return pathway rankings and a recommended pathway based on subject performance.

    Returns dict with keys: available, reason, recommended, rankings, top_subjects, context_label.
    """
    from core.models import UserAttempts
    from subjects.models import Pathway, PathwayDiscipline, Subject

    grade_level = grade_level or student.grade_level
    context_label = _grade_context_label(grade_level)

    pathways = list(
        Pathway.objects.filter(is_active=True).prefetch_related(
            'discipline_weights__discipline',
        )
    )
    if not pathways:
        return {
            'available': False,
            'reason': 'Pathways have not been configured yet.',
            'recommended': None,
            'rankings': [],
            'top_subjects': [],
            'context_label': context_label,
        }

    if not grade_level:
        return {
            'available': False,
            'reason': 'Assign a grade level to see pathway suggestions.',
            'recommended': None,
            'rankings': [],
            'top_subjects': [],
            'context_label': context_label,
        }

    attempts_qs = UserAttempts.objects.filter(
        student=student,
        is_complete=True,
        is_active=True,
        quiz__subject__grade_level_id=grade_level.pk,
        quiz__subject__isnull=False,
    )

    stats_by_subject = {
        row['quiz__subject_id']: row
        for row in (
            attempts_qs
            .values('quiz__subject_id')
            .annotate(
                attempts=Count('uuid'),
                avg_score=Avg('score'),
                best_score=Max('score'),
            )
        )
    }

    subjects = {
        s.pk: s
        for s in Subject.objects.filter(
            grade_level=grade_level,
            is_active=True,
        ).select_related('discipline')
    }

    scored_subjects = []
    for subject_id, subject in subjects.items():
        stats = stats_by_subject.get(subject_id)
        if not stats or stats['attempts'] < MIN_COMPLETED_ATTEMPTS:
            continue
        if stats['avg_score'] is None:
            continue
        scored_subjects.append({
            'subject_id': subject_id,
            'name': subject.name,
            'discipline_slug': subject.discipline.slug,
            'discipline_name': subject.discipline.name,
            'attempts': stats['attempts'],
            'avg_score': round(float(stats['avg_score']), 1),
            'best_score': stats['best_score'] or 0,
        })

    scored_subjects.sort(key=lambda row: (-row['avg_score'], row['name']))
    top_subjects = scored_subjects[:5]

    if not scored_subjects:
        return {
            'available': False,
            'reason': 'Complete at least one exam to unlock pathway suggestions.',
            'recommended': None,
            'rankings': [],
            'top_subjects': [],
            'context_label': context_label,
        }

    discipline_weights = {}
    for pathway in pathways:
        discipline_weights[pathway.slug] = {
            pd.discipline.slug: float(pd.weight)
            for pd in pathway.discipline_weights.all()
        }

    rankings = []
    for pathway in pathways:
        weights_map = discipline_weights.get(pathway.slug, {})
        weighted_sum = 0.0
        weight_total = 0.0
        contributing = []

        for row in scored_subjects:
            w = weights_map.get(row['discipline_slug'], 0)
            if w <= 0:
                continue
            weighted_sum += row['avg_score'] * w
            weight_total += w
            contributing.append({
                'name': row['name'],
                'avg_score': row['avg_score'],
                'best_score': row['best_score'],
                'attempts': row['attempts'],
                'weight': w,
            })

        if weight_total <= 0 or len(contributing) < MIN_PATHWAY_SUBJECTS:
            continue

        avg_score = round(weighted_sum / weight_total, 1)
        contributing.sort(key=lambda r: (-r['avg_score'] * r['weight'], r['name']))
        rankings.append({
            'pathway': pathway,
            'avg_score': avg_score,
            'subject_count': len(contributing),
            'attempt_total': sum(c['attempts'] for c in contributing),
            'contributing_subjects': contributing[:4],
        })

    if not rankings:
        return {
            'available': False,
            'reason': (
                'Take exams in pathway-related subjects (e.g. Mathematics, Science, '
                'Social Studies, or Creative Arts) to see suggestions.'
            ),
            'recommended': None,
            'rankings': [],
            'top_subjects': top_subjects,
            'context_label': context_label,
        }

    rankings.sort(key=lambda r: (-r['avg_score'], -r['subject_count'], r['pathway'].order))
    top_score = rankings[0]['avg_score']
    for row in rankings:
        row['fit_pct'] = round((row['avg_score'] / top_score) * 100) if top_score else 0

    recommended = {
        'pathway': rankings[0]['pathway'],
        'avg_score': rankings[0]['avg_score'],
        'fit_pct': 100,
        'subject_count': rankings[0]['subject_count'],
        'contributing_subjects': rankings[0]['contributing_subjects'],
    }

    confidence = 'low'
    if rankings[0]['subject_count'] >= 3 and rankings[0]['attempt_total'] >= 5:
        confidence = 'high'
    elif rankings[0]['subject_count'] >= 2 or rankings[0]['attempt_total'] >= 3:
        confidence = 'medium'

    # Gap between 1st and 2nd pathway helps guardians judge how clear the signal is.
    margin = 0
    if len(rankings) > 1:
        margin = round(rankings[0]['avg_score'] - rankings[1]['avg_score'], 1)

    return {
        'available': True,
        'reason': '',
        'recommended': recommended,
        'rankings': rankings,
        'top_subjects': top_subjects,
        'context_label': context_label,
        'confidence': confidence,
        'margin': margin,
    }
