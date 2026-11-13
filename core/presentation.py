"""Shuffle questions and options for exams (stable per attempt / demo session)."""

import hashlib
import random


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
        quiz.questions.filter(is_active=True).prefetch_related('options')
    )
    questions = stable_shuffle(questions, attempt.uuid, 'questions')
    limit = quiz.test_size or 0
    if limit > 0 and len(questions) > limit:
        questions = questions[:limit]
    return questions


def options_for_attempt(attempt, question):
    """Active options shuffled for display (fixed for this attempt + question)."""
    options = list(question.options.filter(is_active=True))
    return stable_shuffle(options, attempt.uuid, question.uuid, 'options')


def options_for_demo(demo_id, question):
    """Shuffled options for guest demo sessions."""
    options = list(question.options.filter(is_active=True))
    return stable_shuffle(options, demo_id, question.uuid, 'options')


def demo_questions_presentation_order(demo_id, questions):
    """Shuffle demo question sequence (after pool selection)."""
    return stable_shuffle(questions, demo_id, 'questions')
