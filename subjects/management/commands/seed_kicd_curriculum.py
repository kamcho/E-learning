"""
Seed GradeLevel, Discipline (course), and Subject data for Soma Smart.

Aligned to the school's SMS catalog: Play Group through Grade 9, with
course groupings (Creative & Psychomotor, Environment & Social, etc.).
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from subjects.models import Discipline, GradeLevel, Subject

# ── Grade levels ─────────────────────────────────────────────────────────────

GRADE_LEVELS = [
    ('Play Group', 'play-group', 'ECDE'),
    ('PP1', 'pp1', 'ECDE'),
    ('PP2', 'pp2', 'ECDE'),
    ('Grade 1', 'grade-1', 'Lower Primary'),
    ('Grade 2', 'grade-2', 'Lower Primary'),
    ('Grade 3', 'grade-3', 'Lower Primary'),
    ('Grade 4', 'grade-4', 'Upper Primary'),
    ('Grade 5', 'grade-5', 'Upper Primary'),
    ('Grade 6', 'grade-6', 'Upper Primary'),
    ('Grade 7', 'grade-7', 'Junior Secondary'),
    ('Grade 8', 'grade-8', 'Junior Secondary'),
    ('Grade 9', 'grade-9', 'Junior Secondary'),
    ('Grade 10', 'grade-10', 'Senior Secondary'),
    ('Grade 11', 'grade-11', 'Senior Secondary'),
    ('Grade 12', 'grade-12', 'Senior Secondary'),
]

# ── Courses (Discipline) — SMS "Course" column ───────────────────────────────

DISCIPLINES = [
    ('Creative & Psychomotor', 'creative-psychomotor'),
    ('Environment & Social', 'environment-social'),
    ('Language & Communication', 'language-communication'),
    ('Mathematics & Science', 'mathematics-science'),
    ('Religious & Moral', 'religious-moral'),
    ('Technical & Applied', 'technical-applied'),
]

# discipline_slug for each (subject_name, discipline_slug) tuple
SUBJECTS_BY_GRADE_SLUG = {
    'play-group': [
        ('Creative', 'creative-psychomotor'),
        ('Environmental Activities', 'environment-social'),
        ('Language', 'language-communication'),
        ('Number Work', 'mathematics-science'),
        ('Psycho Motors', 'creative-psychomotor'),
        ('Reading', 'language-communication'),
        ('Religious Education', 'religious-moral'),
    ],
    'pp1': [
        ('Creative', 'creative-psychomotor'),
        ('Environmental Activities', 'environment-social'),
        ('Language', 'language-communication'),
        ('Number Work', 'mathematics-science'),
        ('Psycho Motors', 'creative-psychomotor'),
        ('Reading', 'language-communication'),
        ('Religious Education', 'religious-moral'),
    ],
    'pp2': [
        ('Creative', 'creative-psychomotor'),
        ('Environmental Activities', 'environment-social'),
        ('Kiswahili', 'language-communication'),
        ('Kusoma', 'language-communication'),
        ('Language', 'language-communication'),
        ('Number Work', 'mathematics-science'),
        ('Psycho Motors', 'creative-psychomotor'),
        ('Reading', 'language-communication'),
        ('Religious Education', 'religious-moral'),
    ],
    'grade-1': [
        ('Creative Arts', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Environmental Studies', 'environment-social'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Religious Education', 'religious-moral'),
    ],
    'grade-2': [
        ('Creative Arts', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Environmental Studies', 'environment-social'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Religious Education', 'religious-moral'),
    ],
    'grade-3': [
        ('Creative Arts', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Environmental Studies', 'environment-social'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Religious Education', 'religious-moral'),
    ],
    'grade-4': [
        ('Agriculture and Nutrition', 'technical-applied'),
        ('Creative Arts and Sports', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Religious Education', 'religious-moral'),
        ('Science and Technology', 'mathematics-science'),
        ('Social Studies', 'environment-social'),
    ],
    'grade-5': [
        ('Agriculture and Nutrition', 'technical-applied'),
        ('Creative Arts and Sports', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Religious Education', 'religious-moral'),
        ('Science and Technology', 'mathematics-science'),
        ('Social Studies', 'environment-social'),
    ],
    'grade-6': [
        ('Agriculture and Nutrition', 'technical-applied'),
        ('Creative Arts and Sports', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Religious Education', 'religious-moral'),
        ('Science and Technology', 'mathematics-science'),
        ('Social Studies', 'environment-social'),
    ],
    'grade-7': [
        ('Agriculture and Nutrition', 'technical-applied'),
        ('Creative Arts and Sports', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Integrated Science', 'mathematics-science'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Pre-Technical Studies', 'technical-applied'),
        ('Religious Education', 'religious-moral'),
        ('Social Studies', 'environment-social'),
    ],
    'grade-8': [
        ('Agriculture and Nutrition', 'technical-applied'),
        ('Creative Arts and Sports', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Integrated Science', 'mathematics-science'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Pre-Technical Studies', 'technical-applied'),
        ('Religious Education', 'religious-moral'),
        ('Social Studies', 'environment-social'),
    ],
    'grade-9': [
        ('Agriculture and Nutrition', 'technical-applied'),
        ('Creative Arts and Sports', 'creative-psychomotor'),
        ('English', 'language-communication'),
        ('Integrated Science', 'mathematics-science'),
        ('Kiswahili', 'language-communication'),
        ('Mathematics', 'mathematics-science'),
        ('Pre-Technical Studies', 'technical-applied'),
        ('Religious Education', 'religious-moral'),
        ('Social Studies', 'environment-social'),
    ],
}


def subject_slug(name, grade_slug):
    base = f"{slugify(name)}-{grade_slug}"
    return base[:50]


class Command(BaseCommand):
    help = 'Seed Soma Smart grade levels, courses (disciplines), and subjects.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all subjects, disciplines, and grade levels before seeding (destructive).',
        )
        parser.add_argument(
            '--no-deactivate-orphans',
            action='store_true',
            help='Leave subjects that are not in this catalog active.',
        )

    def handle(self, *args, **options):
        deactivate_orphans = not options['no_deactivate_orphans']

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
            if not created and (obj.name != name or obj.level != level):
                obj.name = name
                obj.level = level
                obj.save(update_fields=['name', 'level'])
            grade_map[slug] = obj
            self._log('GradeLevel', name, created)

        discipline_map = {}
        for name, slug in DISCIPLINES:
            obj, created = Discipline.objects.get_or_create(
                slug=slug,
                defaults={'name': name},
            )
            if not created and obj.name != name:
                obj.name = name
                obj.save(update_fields=['name'])
            discipline_map[slug] = obj
            self._log('Discipline', name, created)

        subject_created = 0
        subject_updated = 0
        for grade_slug, subjects in SUBJECTS_BY_GRADE_SLUG.items():
            grade = grade_map.get(grade_slug)
            if not grade:
                self.stdout.write(self.style.ERROR(f'Unknown grade slug: {grade_slug}'))
                continue

            expected_names = {name for name, _ in subjects}

            for subject_name, discipline_slug in subjects:
                discipline = discipline_map.get(discipline_slug)
                if not discipline:
                    self.stdout.write(self.style.ERROR(
                        f'Unknown discipline slug: {discipline_slug}'
                    ))
                    continue

                slug = subject_slug(subject_name, grade_slug)
                obj = Subject.objects.filter(
                    grade_level=grade,
                    name=subject_name,
                ).first()
                if not obj:
                    obj = Subject.objects.filter(slug=slug).first()

                if obj:
                    created = False
                    changed = False
                    if obj.name != subject_name:
                        obj.name = subject_name
                        changed = True
                    if obj.discipline_id != discipline.pk:
                        obj.discipline = discipline
                        changed = True
                    if obj.grade_level_id != grade.pk:
                        obj.grade_level = grade
                        changed = True
                    if not obj.is_active:
                        obj.is_active = True
                        changed = True
                    if changed:
                        obj.save(update_fields=[
                            'name', 'discipline', 'grade_level', 'is_active', 'updated_at',
                        ])
                        subject_updated += 1
                        self.stdout.write(f'  ~ Subject: {subject_name} ({grade.name}) updated')
                else:
                    Subject.objects.create(
                        name=subject_name,
                        slug=slug,
                        grade_level=grade,
                        discipline=discipline,
                        is_active=True,
                    )
                    created = True
                    subject_created += 1
                    self._log('Subject', f'{subject_name} ({grade.name})', True)

            if deactivate_orphans:
                n = (
                    Subject.objects.filter(grade_level=grade)
                    .exclude(name__in=expected_names)
                    .filter(is_active=True)
                    .update(is_active=False)
                )
                if n:
                    self.stdout.write(self.style.WARNING(
                        f'  - Deactivated {n} subject(s) not in catalog for {grade.name}'
                    ))

        self.stdout.write(self.style.SUCCESS(
            f'\nCurriculum sync complete: '
            f'{len(grade_map)} grade levels, '
            f'{len(discipline_map)} courses, '
            f'{subject_created} subjects created, '
            f'{subject_updated} updated.'
        ))

    def _log(self, model, name, created):
        if created:
            self.stdout.write(self.style.SUCCESS(f'  + {model}: {name}'))
        else:
            self.stdout.write(f'  = {model}: {name} (exists)')
