"""Teacher curriculum browse + AI prompt helpers for bulk question creation."""

import json

from django.db.models import Count, Q
from django.urls import reverse

from core.models import Question
from core.question_import import question_import_ai_delivery_rules
from subjects.grade_utils import GRADE_SLUG_ORDER
from subjects.models import GradeLevel, Strand, Subject, SubStrand


def sort_grade_levels(grade_levels):
    def sort_key(grade):
        try:
            return GRADE_SLUG_ORDER.index(grade.slug)
        except ValueError:
            return 999

    return sorted(grade_levels, key=sort_key)


def build_teacher_grade_cards(teacher):
    """Grade cards for the teacher dashboard (any teacher may add questions in any grade)."""
    grades = list(GradeLevel.objects.all())
    grades = sort_grade_levels(grades)
    if not grades:
        return []

    grade_ids = [g.pk for g in grades]
    subject_counts = {
        row['grade_level_id']: row['total']
        for row in (
            Subject.objects
            .filter(grade_level_id__in=grade_ids, is_active=True)
            .values('grade_level_id')
            .annotate(total=Count('pk'))
        )
    }
    teacher_q_counts = {
        row['sub_strand__strand__subject__grade_level_id']: row['total']
        for row in (
            Question.objects
            .filter(created_by=teacher, sub_strand__strand__subject__grade_level_id__in=grade_ids)
            .values('sub_strand__strand__subject__grade_level_id')
            .annotate(total=Count('pk'))
        )
    }

    cards = []
    for grade in grades:
        cards.append({
            'grade': grade,
            'subject_count': subject_counts.get(grade.pk, 0),
            'my_question_count': teacher_q_counts.get(grade.pk, 0),
            'detail_url': reverse(
                'accounts:teacher_curriculum_grade',
                kwargs={'grade_slug': grade.slug},
            ),
        })
    return cards


def build_teacher_subjects_for_grade(grade, teacher):
    subjects = (
        Subject.objects
        .filter(grade_level=grade, is_active=True)
        .select_related('discipline')
        .annotate(
            strand_count=Count('strands', filter=Q(strands__is_active=True)),
            my_question_count=Count(
                'strands__sub_strands__questions',
                filter=Q(strands__sub_strands__questions__created_by=teacher),
                distinct=True,
            ),
        )
        .order_by('name')
    )
    rows = []
    for subject in subjects:
        rows.append({
            'subject': subject,
            'strand_count': subject.strand_count,
            'my_question_count': subject.my_question_count,
            'detail_url': reverse(
                'accounts:teacher_curriculum_subject',
                kwargs={'grade_slug': grade.slug, 'subject_slug': subject.slug},
            ),
        })
    return rows


def build_teacher_strands_for_subject(subject, teacher):
    strands = (
        Strand.objects
        .filter(subject=subject, is_active=True)
        .annotate(
            sub_strand_count=Count('sub_strands', filter=Q(sub_strands__is_active=True)),
            my_question_count=Count(
                'sub_strands__questions',
                filter=Q(sub_strands__questions__created_by=teacher),
                distinct=True,
            ),
        )
        .order_by('order', 'name')
    )
    rows = []
    for strand in strands:
        rows.append({
            'strand': strand,
            'sub_strand_count': strand.sub_strand_count,
            'my_question_count': strand.my_question_count,
            'detail_url': reverse(
                'accounts:teacher_curriculum_strand',
                kwargs={
                    'grade_slug': subject.grade_level.slug,
                    'subject_slug': subject.slug,
                    'strand_slug': strand.slug,
                },
            ),
        })
    return rows


def build_teacher_sub_strands_for_strand(strand, teacher):
    sub_strands = (
        SubStrand.objects
        .filter(strand=strand, is_active=True)
        .annotate(
            question_count=Count('questions', filter=Q(questions__is_active=True)),
            my_question_count=Count(
                'questions',
                filter=Q(questions__created_by=teacher),
                distinct=True,
            ),
        )
        .order_by('order', 'name')
    )
    subject = strand.subject
    rows = []
    for sub_strand in sub_strands:
        rows.append({
            'sub_strand': sub_strand,
            'question_count': sub_strand.question_count,
            'my_question_count': sub_strand.my_question_count,
            'detail_url': reverse(
                'accounts:teacher_curriculum_sub_strand',
                kwargs={
                    'grade_slug': subject.grade_level.slug,
                    'subject_slug': subject.slug,
                    'strand_slug': strand.slug,
                    'sub_strand_slug': sub_strand.slug,
                },
            ),
        })
    return rows


def build_example_import_payload(sub_strand):
    """Minimal JSON example for paste import (sub-strand prefilled)."""
    return {
        'questions': [
            {
                'quiz': 'Sample question aligned to this sub-strand?',
                'sub_strand_id': sub_strand.pk,
                'sub_strand_slug': sub_strand.slug,
                'difficulty': 'Easy',
                'quiz_type': 'Multiple Choice',
                'score': 1,
                'choices': [
                    {'option': 'Incorrect answer', 'is_correct': False},
                    {'option': 'Correct answer', 'is_correct': True},
                    {'option': 'Another distractor', 'is_correct': False},
                ],
            },
            {
                'quiz': 'True or false sample for this topic.',
                'sub_strand_id': sub_strand.pk,
                'difficulty': 'Medium',
                'quiz_type': 'True or False',
                'score': 1,
                'choices': [
                    {'option': 'True', 'is_correct': True},
                    {'option': 'False', 'is_correct': False},
                ],
            },
        ],
    }


QUESTION_QUIZ_TYPES = (
    'Multiple Choice',
    'Fill in the Blank',
    'True or False',
    'OpenEnded',
    'Matching',
)


def default_question_type_mix(total_count):
    """Split total_count across quiz types as evenly as possible."""
    total = max(1, min(int(total_count), 30))
    per_type = total // len(QUESTION_QUIZ_TYPES)
    remainder = total % len(QUESTION_QUIZ_TYPES)
    mix = {}
    for index, quiz_type in enumerate(QUESTION_QUIZ_TYPES):
        mix[quiz_type] = per_type + (1 if index < remainder else 0)
    return total, mix


def parse_question_mix(total_count, type_counts=None):
    """
    Validate total and per-type counts.
    Returns (total, mix dict keyed by QUESTION_QUIZ_TYPES).
    """
    try:
        total = int(total_count)
    except (TypeError, ValueError):
        raise ValueError('Total question count must be a number.')
    if total < 1 or total > 30:
        raise ValueError('Choose between 1 and 30 questions.')

    if not type_counts:
        return default_question_type_mix(total)

    mix = {}
    for quiz_type in QUESTION_QUIZ_TYPES:
        try:
            count = int(type_counts.get(quiz_type, 0) or 0)
        except (TypeError, ValueError):
            raise ValueError(f'Invalid count for {quiz_type}.')
        if count < 0:
            raise ValueError(f'Count for {quiz_type} cannot be negative.')
        mix[quiz_type] = count

    mix_total = sum(mix.values())
    if mix_total != total:
        raise ValueError(
            f'Question types must add up to {total} (currently {mix_total}).'
        )
    if mix_total == 0:
        raise ValueError('Assign at least one question to a type.')
    return total, mix


def build_ai_question_prompt(sub_strand, *, total_count=8, type_counts=None):
    """
    Plain-text prompt teachers can copy into an external AI tool.
    Output must be JSON matching bulk_create_questions.
    """
    total_count, type_mix = parse_question_mix(total_count, type_counts)
    strand = sub_strand.strand
    subject = strand.subject
    grade = subject.grade_level
    objectives = [
        obj.name
        for obj in sub_strand.sub_strand_objectives.filter(is_active=True).order_by('order', 'name')
    ]

    lines = [
        'You are an expert CBC (Kenya) assessment item writer for Soma Smart.',
        '',
        '## Curriculum context',
        f'- Grade: {grade.name} ({grade.get_level_display()})',
        f'- Subject: {subject.name}',
        f'- Discipline: {subject.discipline.name}',
        f'- Strand: {strand.name}',
        f'- Sub-strand: {sub_strand.name}',
        f'- sub_strand_id: {sub_strand.pk}',
        f'- sub_strand_slug: {sub_strand.slug}',
        '',
        '## Learning objectives (assess these)',
    ]
    if objectives:
        for index, objective in enumerate(objectives, start=1):
            lines.append(f'{index}. {objective}')
    else:
        lines.append(
            '(None listed in Soma Smart yet — align items to the sub-strand title and strand context.)'
        )

    distribution_lines = [
        f'- {quiz_type}: {count}'
        for quiz_type, count in type_mix.items()
        if count > 0
    ]
    task_lines = [
        '',
        '## Task',
        f'Create exactly {total_count} assessment questions for this sub-strand only.',
        '',
        '### Question type distribution (follow exactly)',
        *distribution_lines,
        '',
        'Mix difficulties (Easy, Medium, Hard) across the set. Use clear, age-appropriate language. '
        'LaTeX in $...$ is allowed for maths.',
        'For OpenEnded items, include one or more correct reference answers in choices with is_correct true '
        '(for auto-marking), even though learners type free text.',
    ]
    if objectives:
        task_lines.append(
            'Every question must assess at least one learning objective listed above. '
            'Across the set, cover each objective at least once where practical. '
            'Do not write questions unrelated to those outcomes.'
        )
    lines.extend(task_lines)
    lines.extend([
        '',
        '## Output format',
        'Return ONLY valid JSON with this shape:',
        '{"questions": [ ... ]}',
        '',
        'Each question object MUST include:',
        '- quiz (string): the question stem/prompt',
        '- difficulty: one of Easy, Medium, Hard',
        f'- quiz_type: one of {", ".join(QUESTION_QUIZ_TYPES)}',
        f'- sub_strand_id: {sub_strand.pk} (or sub_strand_slug: "{sub_strand.slug}")',
        '- score (integer, default 1)',
        '- choices (array): required for Multiple Choice, True or False, and Fill in the Blank',
        '',
        'Each choice object:',
        '- option (string)',
        '- is_correct (boolean)',
        '',
        'Rules:',
        '- Multiple Choice: at least 2 choices, at least one is_correct true',
        '- True or False: exactly 2 choices, exactly one is_correct true',
        '- Fill in the Blank: at least one choice with the accepted answer(s), is_correct true',
        '- OpenEnded and Matching: choices may be [] or omitted',
        '- Do not duplicate the same quiz text twice for this sub-strand',
        '',
    ])
    lines.extend(question_import_ai_delivery_rules())
    lines.extend([
        '',
        '## Example (structure only — replace with real items)',
        json.dumps(build_example_import_payload(sub_strand), indent=2),
    ])
    return '\n'.join(lines)
