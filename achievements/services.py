"""Evaluate and display learner achievements."""

from django.db.models import Avg, Count, Max, Q

from .models import Achievement, StudentAchievement


def get_student_attempt_stats(student):
  from core.models import UserAttempts

  qs = UserAttempts.objects.filter(student=student, is_active=True)
  summary = qs.aggregate(
    total=Count('uuid'),
    completed=Count('uuid', filter=Q(is_complete=True)),
    avg_score=Avg('score', filter=Q(is_complete=True)),
    best_score=Max('score', filter=Q(is_complete=True)),
  )
  completed = summary['completed'] or 0
  avg_score = round(summary['avg_score']) if summary['avg_score'] is not None else 0
  best_score = summary['best_score'] or 0
  has_perfect = qs.filter(is_complete=True, score=100).exists()

  return {
    'total': summary['total'] or 0,
    'completed': completed,
    'avg_score': avg_score,
    'best_score': best_score,
    'has_perfect': has_perfect,
  }


def _achievement_met(achievement, stats):
  if achievement.criteria_type == Achievement.CriteriaType.EXAMS_COMPLETED:
    return stats['completed'] >= achievement.threshold
  if achievement.criteria_type == Achievement.CriteriaType.BEST_SCORE:
    return stats['best_score'] >= achievement.threshold
  if achievement.criteria_type == Achievement.CriteriaType.AVG_SCORE:
    min_attempts = achievement.min_attempts or 1
    return stats['completed'] >= min_attempts and stats['avg_score'] >= achievement.threshold
  if achievement.criteria_type == Achievement.CriteriaType.PERFECT_SCORE:
    return stats['has_perfect']
  return False


def _achievement_progress(achievement, stats):
  if achievement.criteria_type == Achievement.CriteriaType.EXAMS_COMPLETED:
    current = stats['completed']
    target = achievement.threshold
  elif achievement.criteria_type == Achievement.CriteriaType.BEST_SCORE:
    current = stats['best_score']
    target = achievement.threshold
  elif achievement.criteria_type == Achievement.CriteriaType.AVG_SCORE:
    min_attempts = achievement.min_attempts or 1
    if stats['completed'] < min_attempts:
      current = 0
      target = min_attempts
      label = f'{stats["completed"]}/{min_attempts} exams'
      pct = int((stats['completed'] / min_attempts) * 100) if min_attempts else 0
      return min(pct, 99), label
    current = stats['avg_score']
    target = achievement.threshold
  elif achievement.criteria_type == Achievement.CriteriaType.PERFECT_SCORE:
    current = 1 if stats['has_perfect'] else 0
    target = 1
  else:
    return 0, ''

  if target <= 0:
    return 100, 'Complete'

  pct = int((current / target) * 100)
  if achievement.criteria_type == Achievement.CriteriaType.EXAMS_COMPLETED:
    label = f'{min(current, target)}/{target} exams'
  elif achievement.criteria_type in (
    Achievement.CriteriaType.BEST_SCORE,
    Achievement.CriteriaType.AVG_SCORE,
  ):
    label = f'{current}% / {target}%'
  else:
    label = achievement.description

  return min(pct, 100), label


def _achievement_context_payload(achievement, stats):
  return {
    'completed': stats['completed'],
    'best_score': stats['best_score'],
    'avg_score': stats['avg_score'],
  }


def evaluate_student_achievements(student):
  """Award any newly earned achievements. Returns list of Achievement instances."""
  stats = get_student_attempt_stats(student)
  earned_ids = set(
    StudentAchievement.objects.filter(student=student).values_list('achievement_id', flat=True)
  )
  newly_earned = []

  for achievement in Achievement.objects.filter(is_active=True):
    if achievement.pk in earned_ids:
      continue
    if not _achievement_met(achievement, stats):
      continue
    StudentAchievement.objects.create(
      student=student,
      achievement=achievement,
      context=_achievement_context_payload(achievement, stats),
    )
    newly_earned.append(achievement)

  return newly_earned


def build_achievements_context(student):
  """Earned + in-progress achievements for templates."""
  stats = get_student_attempt_stats(student)
  earned_qs = (
    StudentAchievement.objects
    .filter(student=student, achievement__is_active=True)
    .select_related('achievement')
    .order_by('-earned_at')
  )
  earned = [
    {
      'title': row.achievement.title,
      'description': row.achievement.description,
      'icon': row.achievement.icon,
      'earned_at': row.earned_at,
      'slug': row.achievement.slug,
    }
    for row in earned_qs
  ]
  earned_ids = {row.achievement_id for row in earned_qs}

  locked = []
  for achievement in Achievement.objects.filter(is_active=True).exclude(pk__in=earned_ids).order_by('order', 'title'):
    progress_pct, progress_label = _achievement_progress(achievement, stats)
    locked.append({
      'title': achievement.title,
      'description': achievement.description,
      'icon': achievement.icon,
      'slug': achievement.slug,
      'progress_pct': progress_pct,
      'progress_label': progress_label,
    })

  total_active = Achievement.objects.filter(is_active=True).count()

  return {
    'earned': earned,
    'locked': locked,
    'earned_count': len(earned),
    'total_count': total_active,
  }
