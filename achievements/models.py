from django.db import models


class Achievement(models.Model):
  class CriteriaType(models.TextChoices):
    EXAMS_COMPLETED = 'exams_completed', 'Exams completed'
    BEST_SCORE = 'best_score', 'Best score'
    AVG_SCORE = 'avg_score', 'Average score'
    PERFECT_SCORE = 'perfect_score', 'Perfect score'

  slug = models.SlugField(max_length=64, unique=True)
  title = models.CharField(max_length=100)
  description = models.TextField()
  icon = models.CharField(max_length=16, default='🏅')
  criteria_type = models.CharField(max_length=32, choices=CriteriaType.choices)
  threshold = models.PositiveIntegerField(
    default=1,
    help_text='Target value for the criteria (count or percentage).',
  )
  min_attempts = models.PositiveIntegerField(
    default=0,
    help_text='Minimum completed exams required (used for average score).',
  )
  order = models.PositiveIntegerField(default=0)
  is_active = models.BooleanField(default=True)

  class Meta:
    ordering = ('order', 'title')

  def __str__(self):
    return self.title


class StudentAchievement(models.Model):
  student = models.ForeignKey(
    'accounts.Student',
    on_delete=models.CASCADE,
    related_name='achievements',
  )
  achievement = models.ForeignKey(
    Achievement,
    on_delete=models.CASCADE,
    related_name='student_awards',
  )
  earned_at = models.DateTimeField(auto_now_add=True)
  context = models.JSONField(default=dict, blank=True)

  class Meta:
    ordering = ('-earned_at',)
    unique_together = ('student', 'achievement')

  def __str__(self):
    return f'{self.student} — {self.achievement.title}'
