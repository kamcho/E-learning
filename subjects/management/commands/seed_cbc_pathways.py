"""
Seed the three KICD Senior School CBC pathways and discipline weights.

Weights map learning areas (disciplines) to pathway fit for performance-based suggestions.
Core areas (Languages, Religious Education) are intentionally omitted — they are common to all pathways.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from subjects.models import Discipline, Pathway, PathwayDiscipline


PATHWAYS = [
    {
        'name': 'STEM',
        'slug': 'stem',
        'emoji': '🔬',
        'order': 1,
        'description': (
            'Science, Technology, Engineering, and Mathematics — for learners strong in '
            'sciences, mathematics, and technical subjects.'
        ),
        'disciplines': {
            'mathematics': '1.00',
            'sciences': '1.00',
            'technical-vocational': '0.90',
        },
    },
    {
        'name': 'Social Sciences',
        'slug': 'social-sciences',
        'emoji': '🌍',
        'order': 2,
        'description': (
            'Humanities, citizenship, and society — for learners who excel in social studies, '
            'history, geography, and related areas.'
        ),
        'disciplines': {
            'humanities-social-sciences': '1.00',
            'agriculture-nutrition': '0.55',
            'technical-vocational': '0.45',
        },
    },
    {
        'name': 'Arts and Sports Science',
        'slug': 'arts-sports-science',
        'emoji': '🎨',
        'order': 3,
        'description': (
            'Creative arts, sports, and performance — for learners who shine in arts, '
            'physical education, and creative expression.'
        ),
        'disciplines': {
            'arts-sports-creativity': '1.00',
            'agriculture-nutrition': '0.35',
        },
    },
]


class Command(BaseCommand):
    help = 'Seed CBC Senior School pathways and discipline weights for pathway suggestions.'

    def handle(self, *args, **options):
        pathway_count = 0
        weight_count = 0

        for spec in PATHWAYS:
            pathway, created = Pathway.objects.update_or_create(
                slug=spec['slug'],
                defaults={
                    'name': spec['name'],
                    'emoji': spec['emoji'],
                    'order': spec['order'],
                    'description': spec['description'],
                    'is_active': True,
                },
            )
            if created:
                pathway_count += 1

            for discipline_slug, weight_str in spec['disciplines'].items():
                discipline = Discipline.objects.filter(slug=discipline_slug).first()
                if not discipline:
                    self.stdout.write(self.style.WARNING(
                        f'Skipping unknown discipline slug: {discipline_slug}'
                    ))
                    continue
                _, w_created = PathwayDiscipline.objects.update_or_create(
                    pathway=pathway,
                    discipline=discipline,
                    defaults={'weight': Decimal(weight_str)},
                )
                if w_created:
                    weight_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'CBC pathways seeded: {Pathway.objects.count()} pathways, '
            f'{PathwayDiscipline.objects.count()} discipline weights '
            f'({pathway_count} new pathways, {weight_count} new weights).'
        ))
