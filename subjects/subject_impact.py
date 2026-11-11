"""Summarize dependent records before deleting or re-scoping a subject."""

from django.db.models import Q

from core.models import AttemptResponse, Question, Quiz, UserAttempts

from .models import StrandObjective, SubStrand, SubStrandObjective, TeacherSubject


def build_subject_deletion_impact(subject):
    """Return human-readable impact rows for delete confirmation."""
    strand_count = subject.strands.count()
    sub_strand_count = SubStrand.objects.filter(strand__subject=subject).count()
    strand_objective_count = StrandObjective.objects.filter(strand__subject=subject).count()
    sub_strand_objective_count = SubStrandObjective.objects.filter(
        sub_strand__strand__subject=subject,
    ).count()
    question_count = Question.objects.filter(sub_strand__strand__subject=subject).count()
    quiz_qs = Quiz.objects.filter(
        Q(subject=subject)
        | Q(strand__subject=subject)
        | Q(sub_strand__strand__subject=subject),
    ).distinct()
    quiz_count = quiz_qs.count()
    attempt_count = UserAttempts.objects.filter(quiz__in=quiz_qs).count()
    response_count = AttemptResponse.objects.filter(attempt__quiz__in=quiz_qs).count()
    teacher_assignment_count = TeacherSubject.objects.filter(subject=subject).count()

    rows = []
    if strand_count:
        rows.append({
            'label': 'Strands',
            'count': strand_count,
            'detail': 'Including all nested sub-strands and objectives.',
        })
    if sub_strand_count:
        rows.append({
            'label': 'Sub-strands',
            'count': sub_strand_count,
            'detail': 'Removed with their strands.',
        })
    if strand_objective_count or sub_strand_objective_count:
        rows.append({
            'label': 'Learning objectives',
            'count': strand_objective_count + sub_strand_objective_count,
            'detail': 'Strand and sub-strand objectives.',
        })
    if question_count:
        rows.append({
            'label': 'Questions',
            'count': question_count,
            'detail': 'Question bank items tied to this subject.',
        })
    if quiz_count:
        rows.append({
            'label': 'Exams / quizzes',
            'count': quiz_count,
            'detail': 'Published and draft exams for this subject.',
        })
    if attempt_count:
        rows.append({
            'label': 'Learner attempts',
            'count': attempt_count,
            'detail': 'Scores and progress history will be lost.',
        })
    if response_count:
        rows.append({
            'label': 'Attempt answers',
            'count': response_count,
            'detail': 'Individual responses linked to attempts.',
        })
    if teacher_assignment_count:
        rows.append({
            'label': 'Teacher assignments',
            'count': teacher_assignment_count,
            'detail': 'Teachers linked to teach this subject.',
        })

    total = (
        strand_count + sub_strand_count + strand_objective_count + sub_strand_objective_count
        + question_count + quiz_count + attempt_count + response_count + teacher_assignment_count
    )

    return {
        'subject_id': subject.pk,
        'subject_name': subject.name,
        'subject_slug': subject.slug,
        'grade_level': subject.grade_level.name,
        'discipline': subject.discipline.name,
        'rows': rows,
        'total_dependent_records': total,
        'has_dependents': total > 0,
    }
