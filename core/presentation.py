"""Shuffle questions and options for exams (stable per attempt / demo session)."""

import hashlib
import random

from django.db.models import Prefetch, prefetch_related_objects

from core.models import Option


def _stable_seed(*parts):
    raw = '|'.join(str(part) for part in parts).encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:16], 16)


def stable_shuffle(items, *seed_parts):
    """Return a new list with the same items in a deterministic pseudo-random order."""
    items = list(items)
    rng = random.Random(_stable_seed(*seed_parts))
    rng.shuffle(items)
    return items


def questions_for_attempt(attempt, quiz):
    """Active quiz questions in shuffled order (fixed for this attempt)."""
    questions = list(
        quiz.questions.filter(is_active=True).select_related(
            'sub_strand__strand__subject__grade_level',
        )
    )
    questions = stable_shuffle(questions, attempt.uuid, 'questions')
    limit = quiz.test_size or 0
    if limit > 0 and len(questions) > limit:
        questions = questions[:limit]
    if questions:
        prefetch_related_objects(
            questions,
            Prefetch(
                'options',
                queryset=Option.objects.filter(is_active=True).order_by('created_at'),
                to_attr='active_options',
            ),
        )
    return questions


def active_options_for_question(question):
    """Use prefetched active options when available, otherwise load them once."""
    options = getattr(question, 'active_options', None)
    if options is not None:
        return options
    return list(question.options.filter(is_active=True).order_by('created_at'))


def options_for_attempt(attempt, question):
    """Active options shuffled for display (fixed for this attempt + question)."""
    options = active_options_for_question(question)
    return stable_shuffle(options, attempt.uuid, question.uuid, 'options')


def options_for_demo(demo_id, question):
    """Shuffled options for guest demo sessions."""
    options = active_options_for_question(question)
    return stable_shuffle(options, demo_id, question.uuid, 'options')


def demo_questions_presentation_order(demo_id, questions):
    """Shuffle demo question sequence (after pool selection)."""
    return stable_shuffle(questions, demo_id, 'questions')
