"""Exam time limits for timed quizzes."""

from django.utils import timezone


def quiz_time_limit_seconds(quiz):
    minutes = getattr(quiz, 'time_limit_minutes', 0) or 0
    if minutes <= 0:
        return 0
    return minutes * 60


def attempt_started_at(attempt):
    return attempt.started_at or attempt.created_at


def attempt_seconds_remaining(attempt, quiz):
    limit_seconds = quiz_time_limit_seconds(quiz)
    if not limit_seconds:
        return None
    elapsed = (timezone.now() - attempt_started_at(attempt)).total_seconds()
    return max(0, int(limit_seconds - elapsed))


def attempt_has_timed_out(attempt, quiz):
    remaining = attempt_seconds_remaining(attempt, quiz)
    return remaining is not None and remaining <= 0
