from django.core.management.base import BaseCommand

from achievements.models import Achievement


DEFAULT_ACHIEVEMENTS = [
  {
    'slug': 'first-steps',
    'title': 'First Steps',
    'description': 'Complete your first exam.',
    'icon': '🎯',
    'criteria_type': Achievement.CriteriaType.EXAMS_COMPLETED,
    'threshold': 1,
    'order': 10,
  },
  {
    'slug': 'exam-explorer',
    'title': 'Exam Explorer',
    'description': 'Complete 3 exams.',
    'icon': '📚',
    'criteria_type': Achievement.CriteriaType.EXAMS_COMPLETED,
    'threshold': 3,
    'order': 20,
  },
  {
    'slug': 'dedicated-learner',
    'title': 'Dedicated Learner',
    'description': 'Complete 10 exams.',
    'icon': '🔥',
    'criteria_type': Achievement.CriteriaType.EXAMS_COMPLETED,
    'threshold': 10,
    'order': 30,
  },
  {
    'slug': 'strong-progress',
    'title': 'Strong Progress',
    'description': 'Reach a best score of 70% or higher.',
    'icon': '⭐',
    'criteria_type': Achievement.CriteriaType.BEST_SCORE,
    'threshold': 70,
    'order': 40,
  },
  {
    'slug': 'top-performer',
    'title': 'Top Performer',
    'description': 'Reach a best score of 90% or higher.',
    'icon': '🏆',
    'criteria_type': Achievement.CriteriaType.BEST_SCORE,
    'threshold': 90,
    'order': 50,
  },
  {
    'slug': 'rising-star',
    'title': 'Rising Star',
    'description': 'Maintain a 75% average across 3+ completed exams.',
    'icon': '📈',
    'criteria_type': Achievement.CriteriaType.AVG_SCORE,
    'threshold': 75,
    'min_attempts': 3,
    'order': 60,
  },
  {
    'slug': 'perfect-score',
    'title': 'Perfect Score',
    'description': 'Score 100% on any exam.',
    'icon': '💯',
    'criteria_type': Achievement.CriteriaType.PERFECT_SCORE,
    'threshold': 100,
    'order': 70,
  },
]


class Command(BaseCommand):
  help = 'Seed default learner achievements.'

  def handle(self, *args, **options):
    created = 0
    updated = 0
    for row in DEFAULT_ACHIEVEMENTS:
      _, was_created = Achievement.objects.update_or_create(
        slug=row['slug'],
        defaults=row,
      )
      if was_created:
        created += 1
      else:
        updated += 1
    self.stdout.write(self.style.SUCCESS(
      f'Achievements ready: {created} created, {updated} updated.'
    ))
