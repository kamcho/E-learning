"""Auto-generate custom quizzes from the question bank when no ready-made tests exist."""

import random

from core.models import Question, Quiz

DEFAULT_CUSTOM_QUESTION_COUNT = 20
CUSTOM_QUIZ_TITLE_PREFIX = 'Custom'


def _questions_queryset(*, subject, strand=None, sub_strand=None, difficulty=''):
    qs = (
        Question.objects.filter(
            is_active=True,
            sub_strand__strand__subject=subject,
        )
        .select_related(
            'sub_strand',
            'sub_strand__strand',
            'sub_strand__strand__subject',
        )
        .prefetch_related('options')
    )

    if sub_strand:
        qs = qs.filter(sub_strand=sub_strand)
    elif strand:
        qs = qs.filter(sub_strand__strand=strand)

    if difficulty:
        qs = qs.filter(difficulty=difficulty)

    return qs


def _questions_from_existing_quizzes(*, subject, strand=None, sub_strand=None, difficulty=''):
    """Fallback: reuse questions already attached to subject quizzes."""
    quiz_qs = Quiz.objects.filter(is_active=True, subject=subject).prefetch_related('questions')
    if sub_strand:
        quiz_qs = quiz_qs.filter(sub_strand=sub_strand)
    elif strand:
        quiz_qs = quiz_qs.filter(strand=strand)

    seen = set()
    pool = []
    for quiz in quiz_qs:
        for question in quiz.questions.filter(is_active=True):
            if difficulty and question.difficulty != difficulty:
                continue
            if question.pk in seen:
                continue
            seen.add(question.pk)
            pool.append(question)
    return pool


def select_questions_for_custom_quiz(
    *,
    subject,
    strand=None,
    sub_strand=None,
    difficulty='',
    count=DEFAULT_CUSTOM_QUESTION_COUNT,
):
    pool = list(_questions_queryset(
        subject=subject,
        strand=strand,
        sub_strand=sub_strand,
        difficulty=difficulty,
    ))

    if not pool and difficulty:
        pool = list(_questions_queryset(
            subject=subject,
            strand=strand,
            sub_strand=sub_strand,
            difficulty='',
        ))

    if not pool:
        pool = _questions_from_existing_quizzes(
            subject=subject,
            strand=strand,
            sub_strand=sub_strand,
            difficulty=difficulty,
        )

    if not pool and difficulty:
        pool = _questions_from_existing_quizzes(
            subject=subject,
            strand=strand,
            sub_strand=sub_strand,
            difficulty='',
        )

    if not pool:
        return []

    sample_size = min(count, len(pool))
    return random.sample(pool, sample_size)


def _scope_label(*, subject, strand=None, sub_strand=None):
    if sub_strand:
        return f'{subject.name} · {sub_strand.name}'
    if strand:
        return f'{subject.name} · {strand.name}'
    return f'{subject.name} · Whole subject'


def _build_custom_quiz_title(*, subject, strand=None, sub_strand=None):
    title = f'{CUSTOM_QUIZ_TITLE_PREFIX} {_scope_label(subject=subject, strand=strand, sub_strand=sub_strand)}'
    return title[:100]


def _find_existing_custom_quiz(*, subject, strand=None, sub_strand=None, difficulty=''):
    qs = Quiz.objects.filter(
        is_active=True,
        subject=subject,
        strand=strand,
        sub_strand=sub_strand,
        title__startswith=CUSTOM_QUIZ_TITLE_PREFIX,
    ).prefetch_related('questions')

    if difficulty:
        qs = qs.filter(difficulty=difficulty)

    for quiz in qs.order_by('-created_at'):
        if quiz.questions.filter(is_active=True).exists():
            return quiz
    return None


def _find_empty_custom_quiz(*, subject, strand=None, sub_strand=None, difficulty=''):
    qs = Quiz.objects.filter(
        is_active=True,
        subject=subject,
        strand=strand,
        sub_strand=sub_strand,
        title__startswith=CUSTOM_QUIZ_TITLE_PREFIX,
    )
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    return qs.order_by('-created_at').first()


def resolve_custom_quiz_scope(*, scope, active_strand=None, active_sub_strand=None):
    """Map exam wizard filters to quiz strand/sub_strand fields."""
    if scope == 'general':
        return None, None
    if active_sub_strand:
        return active_sub_strand.strand, active_sub_strand
    if active_strand:
        return active_strand, None
    return None, None


def find_or_create_custom_quiz(
    *,
    user,
    subject,
    strand=None,
    sub_strand=None,
    difficulty='',
):
    """
    Return an active custom quiz for the given scope, creating one from the
    question bank when none exists yet.
    """
    existing = _find_existing_custom_quiz(
        subject=subject,
        strand=strand,
        sub_strand=sub_strand,
        difficulty=difficulty,
    )
    if existing:
        return existing

    questions = select_questions_for_custom_quiz(
        subject=subject,
        strand=strand,
        sub_strand=sub_strand,
        difficulty=difficulty,
    )
    if not questions:
        return None

    quiz_difficulty = difficulty or 'Medium'
    empty_quiz = _find_empty_custom_quiz(
        subject=subject,
        strand=strand,
        sub_strand=sub_strand,
        difficulty=difficulty,
    )
    if empty_quiz:
        quiz = empty_quiz
        quiz.difficulty = quiz_difficulty
        quiz.test_size = len(questions)
        quiz.created_by = user
        quiz.save(update_fields=['difficulty', 'test_size', 'created_by', 'updated_at'])
    else:
        title = _build_custom_quiz_title(subject=subject, strand=strand, sub_strand=sub_strand)
        quiz = Quiz.objects.create(
            title=title,
            description='Auto-generated test based on your subject and topic choices.',
            difficulty=quiz_difficulty,
            subject=subject,
            strand=strand,
            sub_strand=sub_strand,
            test_size=len(questions),
            created_by=user,
        )

    quiz.questions.set(questions)
    return quiz
