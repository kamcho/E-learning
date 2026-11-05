from django.core.management.base import BaseCommand

from subscriptions.models import SubscriptionPlan


PLANS = [
    {
        'slug': 'exam-play-group-grade-3',
        'name': 'Play Group–Grade 3 Exam',
        'description': 'One practice exam for a linked learner in Play Group through Grade 3.',
        'plan_type': SubscriptionPlan.PlanType.SINGLE_TEST,
        'grade_band': SubscriptionPlan.GradeBand.PLAY_GROUP_TO_GRADE_3,
        'price_kes': 10,
        'duration_days': 30,
        'max_tests': 1,
        'max_learners': 1,
        'features': [
            '1 exam for one linked learner',
            'For Play Group to Grade 3',
            'Use within 30 days',
            'Full results & analytics',
        ],
        'sort_order': 1,
    },
    {
        'slug': 'exam-grade-4-6',
        'name': 'Grade 4–6 Exam',
        'description': 'One practice exam for a linked learner in Grades 4–6.',
        'plan_type': SubscriptionPlan.PlanType.SINGLE_TEST,
        'grade_band': SubscriptionPlan.GradeBand.GRADE_4_TO_6,
        'price_kes': 15,
        'duration_days': 30,
        'max_tests': 1,
        'max_learners': 1,
        'features': [
            '1 exam for one linked learner',
            'For Grades 4–6',
            'Use within 30 days',
            'Full results & analytics',
        ],
        'sort_order': 2,
    },
    {
        'slug': 'exam-grade-7-12',
        'name': 'Grade 7–12 Exam',
        'description': 'One practice exam for a linked learner in Grades 7–12.',
        'plan_type': SubscriptionPlan.PlanType.SINGLE_TEST,
        'grade_band': SubscriptionPlan.GradeBand.GRADE_7_TO_12,
        'price_kes': 20,
        'duration_days': 30,
        'max_tests': 1,
        'max_learners': 1,
        'features': [
            '1 exam for one linked learner',
            'For Grades 7–12',
            'Use within 30 days',
            'Full results & analytics',
        ],
        'sort_order': 3,
    },
]

LEGACY_SLUGS = (
    'single-test', 'weekly-pack', 'monthly-pack', 'yearly-unlimited',
    'family-monthly', 'family-term', 'family-annual',
)


class Command(BaseCommand):
    help = 'Seed Soma Smart grade-banded pay-per-exam plans.'

    def handle(self, *args, **options):
        deactivated = SubscriptionPlan.objects.filter(slug__in=LEGACY_SLUGS).update(is_active=False)
        if deactivated:
            self.stdout.write(self.style.WARNING(f'Deactivated {deactivated} legacy plan(s).'))

        for plan_data in PLANS:
            plan, created = SubscriptionPlan.objects.update_or_create(
                slug=plan_data['slug'],
                defaults=plan_data,
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{action}: {plan.name}'))
