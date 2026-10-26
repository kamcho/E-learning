from django.test import TestCase

from subjects.forms import StrandForm
from subjects.models import Discipline, GradeLevel, Subject


class StrandFormTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_blank_slug_is_generated_from_strand_and_subject_names(self):
        form = StrandForm(data={
            'name': 'Creation',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['slug'],
            'creation-religious-education-grade-1',
        )
