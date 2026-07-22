"""
Seed GradeLevel, Discipline, and Subject data aligned to KICD CBC (2024 rationalized).

Sources: KICD curriculum designs & PWPER rationalization (2023–2024):
- Pre-Primary: 5 learning areas (PP1–PP2)
- Lower Primary (Grades 1–3): 7 learning areas
- Upper Primary (Grades 4–6): 8 learning areas
- Junior School (Grades 7–9): 9 core learning areas
- Senior School (Grades 10–12): core + pathway learning areas (simplified)
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from subjects.models import Discipline, GradeLevel, Subject


# ── Grade levels (KICD school structure) ──────────────────────────────────────

GRADE_LEVELS = [
    # ECDE / Pre-Primary
    ('PP1', 'pp1', 'ECDE'),
    ('PP2', 'pp2', 'ECDE'),
    # Lower Primary
    ('Grade 1', 'grade-1', 'Lower Primary'),
    ('Grade 2', 'grade-2', 'Lower Primary'),
    ('Grade 3', 'grade-3', 'Lower Primary'),
    # Upper Primary
    ('Grade 4', 'grade-4', 'Upper Primary'),
    ('Grade 5', 'grade-5', 'Upper Primary'),
    ('Grade 6', 'grade-6', 'Upper Primary'),
    # Junior Secondary (Junior School)
    ('Grade 7', 'grade-7', 'Junior Secondary'),
    ('Grade 8', 'grade-8', 'Junior Secondary'),
    ('Grade 9', 'grade-9', 'Junior Secondary'),
    # Senior Secondary
    ('Grade 10', 'grade-10', 'Senior Secondary'),
    ('Grade 11', 'grade-11', 'Senior Secondary'),
    ('Grade 12', 'grade-12', 'Senior Secondary'),
]

# ── Disciplines (KICD learning-area groupings) ────────────────────────────────

DISCIPLINES = [
    ('Languages', 'languages'),
    ('Mathematics', 'mathematics'),
    ('Sciences', 'sciences'),
    ('Humanities & Social Sciences', 'humanities-social-sciences'),
    ('Religious Education', 'religious-education'),
    ('Arts, Sports & Creativity', 'arts-sports-creativity'),
    ('Agriculture & Nutrition', 'agriculture-nutrition'),
    ('Technical & Vocational', 'technical-vocational'),
]

# ── Subjects per grade band (name, discipline_slug) ───────────────────────────
# Rationalized KICD learning areas per PWPER / KICD 2024 designs.

SUBJECTS_BY_GRADE_SLUG = {
    # Pre-Primary — 5 learning areas (unchanged)
    'pp1': [
        ('Language Activities', 'languages'),
        ('Mathematical Activities', 'mathematics'),
        ('Environmental Activities', 'sciences'),
        ('Psychomotor and Creative Activities', 'arts-sports-creativity'),
        ('Religious Education Activities', 'religious-education'),
    ],
    'pp2': [
        ('Language Activities', 'languages'),
        ('Mathematical Activities', 'mathematics'),
        ('Environmental Activities', 'sciences'),
        ('Psychomotor and Creative Activities', 'arts-sports-creativity'),
        ('Religious Education Activities', 'religious-education'),
    ],
    # Lower Primary — 7 learning areas
    'grade-1': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Religious Education', 'religious-education'),
        ('Creative Arts', 'arts-sports-creativity'),
        ('Hygiene and Nutrition', 'agriculture-nutrition'),
        ('Environmental Activities', 'sciences'),
    ],
    'grade-2': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Religious Education', 'religious-education'),
        ('Creative Arts', 'arts-sports-creativity'),
        ('Hygiene and Nutrition', 'agriculture-nutrition'),
        ('Environmental Activities', 'sciences'),
    ],
    'grade-3': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Religious Education', 'religious-education'),
        ('Creative Arts', 'arts-sports-creativity'),
        ('Hygiene and Nutrition', 'agriculture-nutrition'),
        ('Environmental Activities', 'sciences'),
    ],
    # Upper Primary — 8 learning areas (rationalized)
    'grade-4': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Integrated Science', 'sciences'),
        ('Social Studies', 'humanities-social-sciences'),
        ('Religious Education', 'religious-education'),
        ('Creative Arts', 'arts-sports-creativity'),
        ('Agriculture and Nutrition', 'agriculture-nutrition'),
    ],
    'grade-5': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Integrated Science', 'sciences'),
        ('Social Studies', 'humanities-social-sciences'),
        ('Religious Education', 'religious-education'),
        ('Creative Arts', 'arts-sports-creativity'),
        ('Agriculture and Nutrition', 'agriculture-nutrition'),
    ],
    'grade-6': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Integrated Science', 'sciences'),
        ('Social Studies', 'humanities-social-sciences'),
        ('Religious Education', 'religious-education'),
        ('Creative Arts', 'arts-sports-creativity'),
        ('Agriculture and Nutrition', 'agriculture-nutrition'),
    ],
    # Junior School — 9 core learning areas (rationalized)
    'grade-7': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Integrated Science', 'sciences'),
        ('Social Studies', 'humanities-social-sciences'),
        ('Religious Education', 'religious-education'),
        ('Agriculture and Nutrition', 'agriculture-nutrition'),
        ('Pre-technical Studies', 'technical-vocational'),
        ('Creative Arts and Sports', 'arts-sports-creativity'),
    ],
    'grade-8': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Integrated Science', 'sciences'),
        ('Social Studies', 'humanities-social-sciences'),
        ('Religious Education', 'religious-education'),
        ('Agriculture and Nutrition', 'agriculture-nutrition'),
        ('Pre-technical Studies', 'technical-vocational'),
        ('Creative Arts and Sports', 'arts-sports-creativity'),
    ],
    'grade-9': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Integrated Science', 'sciences'),
        ('Social Studies', 'humanities-social-sciences'),
        ('Religious Education', 'religious-education'),
        ('Agriculture and Nutrition', 'agriculture-nutrition'),
        ('Pre-technical Studies', 'technical-vocational'),
        ('Creative Arts and Sports', 'arts-sports-creativity'),
    ],
    # Senior School — core + representative pathway learning areas
    'grade-10': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Community Service Learning', 'humanities-social-sciences'),
        ('Physical Education', 'arts-sports-creativity'),
        ('Biology', 'sciences'),
        ('Chemistry', 'sciences'),
        ('Physics', 'sciences'),
        ('History and Citizenship', 'humanities-social-sciences'),
        ('Geography', 'humanities-social-sciences'),
        ('Business Studies', 'technical-vocational'),
        ('Computer Studies', 'technical-vocational'),
    ],
    'grade-11': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Community Service Learning', 'humanities-social-sciences'),
        ('Physical Education', 'arts-sports-creativity'),
        ('Biology', 'sciences'),
        ('Chemistry', 'sciences'),
        ('Physics', 'sciences'),
        ('History and Citizenship', 'humanities-social-sciences'),
        ('Geography', 'humanities-social-sciences'),
        ('Business Studies', 'technical-vocational'),
        ('Computer Studies', 'technical-vocational'),
    ],
    'grade-12': [
        ('English', 'languages'),
        ('Kiswahili', 'languages'),
        ('Mathematics', 'mathematics'),
        ('Community Service Learning', 'humanities-social-sciences'),
        ('Physical Education', 'arts-sports-creativity'),
        ('Biology', 'sciences'),
        ('Chemistry', 'sciences'),
        ('Physics', 'sciences'),
        ('History and Citizenship', 'humanities-social-sciences'),
        ('Geography', 'humanities-social-sciences'),
        ('Business Studies', 'technical-vocational'),
        ('Computer Studies', 'technical-vocational'),
    ],
}


def subject_slug(name, grade_slug):
    base = f"{slugify(name)}-{grade_slug}"
    return base[:50]


class Command(BaseCommand):
    help = 'Seed KICD-aligned GradeLevel, Discipline, and Subject data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing GradeLevel, Discipline, and Subject records before seeding.',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted = Subject.objects.all().delete()
            Discipline.objects.all().delete()
            GradeLevel.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared curriculum data (subjects cascade: {deleted[0]} rows).'
            ))

        grade_map = {}
        for name, slug, level in GRADE_LEVELS:
            obj, created = GradeLevel.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'level': level},
            )
            grade_map[slug] = obj
            self._log('GradeLevel', name, created)

        discipline_map = {}
        for name, slug in DISCIPLINES:
            obj, created = Discipline.objects.get_or_create(
                slug=slug,
                defaults={'name': name},
            )
            discipline_map[slug] = obj
            self._log('Discipline', name, created)

        subject_created = 0
        subject_skipped = 0
        for grade_slug, subjects in SUBJECTS_BY_GRADE_SLUG.items():
            grade = grade_map.get(grade_slug)
            if not grade:
                self.stdout.write(self.style.ERROR(f'Unknown grade slug: {grade_slug}'))
                continue

            for subject_name, discipline_slug in subjects:
                discipline = discipline_map.get(discipline_slug)
                if not discipline:
                    self.stdout.write(self.style.ERROR(
                        f'Unknown discipline slug: {discipline_slug}'
                    ))
                    continue

                slug = subject_slug(subject_name, grade_slug)
                _, created = Subject.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'name': subject_name,
                        'grade_level': grade,
                        'discipline': discipline,
                        'is_active': True,
                    },
                )
                if created:
                    subject_created += 1
                    self._log('Subject', f'{subject_name} ({grade.name})', True)
                else:
                    subject_skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nKICD seed complete: '
            f'{len(grade_map)} grade levels, '
            f'{len(discipline_map)} disciplines, '
            f'{subject_created} subjects created, '
            f'{subject_skipped} subjects already existed.'
        ))

    def _log(self, model, name, created):
        if created:
            self.stdout.write(self.style.SUCCESS(f'  + {model}: {name}'))
        else:
            self.stdout.write(f'  = {model}: {name} (exists)')
