from django.core.management.base import BaseCommand

from subscriptions.models import SubscriptionPlan


PLANS = [
    {
        'slug': 'daily-pass',
        'name': 'Daily access',
        'description': 'Unlimited practice exams for one learner for 24 hours — any grade.',
        'plan_type': SubscriptionPlan.PlanType.UNLIMITED,
        'grade_band': '',
        'price_kes': 20,
        'duration_days': 1,
        'max_tests': None,
        'max_learners': 3,
        'features': [
            'Unlimited exams for 1 day',
            'All grades PP1–Grade 12',
            'Full results & AI tutor help',
            'M-Pesa STK Push',
        ],
        'sort_order': 1,
    },
    {
        'slug': 'weekly-pack',
        'name': 'Weekly unlimited',
        'description': 'Unlimited practice exams for your linked learners for 7 days.',
        'plan_type': SubscriptionPlan.PlanType.UNLIMITED,
        'grade_band': '',
        'price_kes': 80,
        'duration_days': 7,
        'max_tests': None,
        'max_learners': 3,
        'features': [
            'Unlimited exams for 7 days',
            'Up to 3 linked learners',
            'Progress tracking & analytics',
            'M-Pesa STK Push',
        ],
        'sort_order': 2,
    },
    {
        'slug': 'monthly-pack',
        'name': 'Monthly unlimited',
        'description': 'Unlimited practice exams for your linked learners for 30 days.',
        'plan_type': SubscriptionPlan.PlanType.UNLIMITED,
        'grade_band': '',
        'price_kes': 299,
        'duration_days': 30,
        'max_tests': None,
        'max_learners': 3,
        'features': [
            'Unlimited exams for 30 days',
            'Up to 3 linked learners',
            'Best value for regular practice',
            'M-Pesa STK Push',
        ],
        'sort_order': 3,
    },
]

LEGACY_SLUGS = (
    'single-test',
    'yearly-unlimited',
    'family-monthly',
    'family-term',
    'family-annual',
    'exam-play-group-grade-3',
    'exam-grade-4-6',
    'exam-grade-7-12',
)


class Command(BaseCommand):
    help = 'Seed Soma Smart daily, weekly, and monthly subscription plans.'

    def handle(self, *args, **options):
        deactivated = SubscriptionPlan.objects.filter(slug__in=LEGACY_SLUGS).update(is_active=False)
        if deactivated:
            self.stdout.write(self.style.WARNING(f'Deactivated {deactivated} legacy plan(s).'))

        for plan_data in PLANS:
            plan, created = SubscriptionPlan.objects.update_or_create(
                slug=plan_data['slug'],
                defaults={**plan_data, 'is_active': True},
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{action}: {plan.name} — KES {plan.price_kes}'))