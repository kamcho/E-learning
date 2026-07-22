from django.core.management.base import BaseCommand

from subscriptions.models import SubscriptionPlan


PLANS = [
    {
        'slug': 'single-test',
        'name': 'Single Test',
        'description': 'Pay once, take one CBC practice exam. Perfect for trying Soma Smart.',
        'plan_type': SubscriptionPlan.PlanType.SINGLE_TEST,
        'price_kes': 10,
        'duration_days': 30,
        'max_tests': 1,
        'max_learners': 3,
        'features': [
            '1 practice test',
            'Use within 30 days',
            'All linked learners',
            'Full results & analytics',
        ],
        'sort_order': 1,
    },
    {
        'slug': 'weekly-pack',
        'name': 'Weekly Pack',
        'description': 'Fifteen tests for a week of focused revision.',
        'plan_type': SubscriptionPlan.PlanType.TEST_PACK,
        'price_kes': 70,
        'duration_days': 7,
        'max_tests': 15,
        'max_learners': 3,
        'features': [
            '15 practice tests',
            'Valid for 7 days',
            'All linked learners',
            'Guardian dashboard',
        ],
        'sort_order': 2,
    },
    {
        'slug': 'monthly-pack',
        'name': 'Monthly Pack',
        'description': 'Best for regular practice — one hundred tests for the month.',
        'plan_type': SubscriptionPlan.PlanType.TEST_PACK,
        'price_kes': 200,
        'duration_days': 30,
        'max_tests': 100,
        'max_learners': 3,
        'features': [
            '100 practice tests',
            'Valid for 30 days',
            'All linked learners',
            'Guardian dashboard & analytics',
        ],
        'sort_order': 3,
    },
    {
        'slug': 'yearly-unlimited',
        'name': 'Yearly Unlimited',
        'description': 'Unlimited CBC practice exams for a full year.',
        'plan_type': SubscriptionPlan.PlanType.UNLIMITED,
        'price_kes': 1500,
        'duration_days': 365,
        'max_tests': None,
        'max_learners': 5,
        'features': [
            'Unlimited practice tests',
            'Valid for 365 days',
            'Up to 5 learners',
            'Guardian dashboard & analytics',
            'Best value for serious prep',
        ],
        'sort_order': 4,
    },
]

LEGACY_SLUGS = ('family-monthly', 'family-term', 'family-annual')


class Command(BaseCommand):
    help = 'Seed Soma Smart test-credit subscription plans.'

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
