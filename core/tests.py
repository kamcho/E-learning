from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from core.models import Option, Question
from core.question_import import bulk_create_questions, validate_question_item
from subjects.models import Discipline, GradeLevel, Strand, Subject, SubStrand

User = get_user_model()


class QuestionImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            phone='0711111111',
            password='1234',
            role=Role.TEACHER,
            first_name='Test',
            last_name='Teacher',
        )
        cls.grade = GradeLevel.objects.create(name='Grade 4', slug='grade-4', level='Upper Primary')
        cls.discipline = Discipline.objects.create(name='Mathematics', slug='mathematics')
        cls.subject = Subject.objects.create(
            name='Math',
            slug='math-g4',
            grade_level=cls.grade,
            discipline=cls.discipline,
        )
        cls.strand = Strand.objects.create(name='Numbers', slug='numbers-g4', subject=cls.subject)
        cls.sub_strand = SubStrand.objects.create(
            name='Addition',
            slug='addition-g4',
            strand=cls.strand,
        )

    def test_validate_multiple_choice_question(self):
        cleaned = validate_question_item({
            'quiz': 'What is 2 + 2?',
            'sub_strand_id': self.sub_strand.pk,
            'difficulty': 'Easy',
            'quiz_type': 'Multiple Choice',
            'choices': [
                {'option': '3', 'is_correct': False},
                {'option': '4', 'is_correct': True},
            ],
        })
        self.assertEqual(cleaned['quiz'], 'What is 2 + 2?')
        self.assertEqual(len(cleaned['choices']), 2)

    def test_bulk_create_sets_inactive_and_created_by(self):
        result = bulk_create_questions({
            'questions': [
                {
                    'quiz': 'Bulk import question?',
                    'sub_strand_id': self.sub_strand.pk,
                    'difficulty': 'Easy',
                    'quiz_type': 'True or False',
                    'choices': [
                        {'option': 'True', 'is_correct': True},
                        {'option': 'False', 'is_correct': False},
                    ],
                },
            ],
        }, created_by=self.teacher)

        self.assertEqual(result['created'], 1)
        self.assertEqual(result['failed'], 0)
        question = Question.objects.get(uuid=result['results'][0]['question_uuid'])
        self.assertFalse(question.is_active)
        self.assertEqual(question.created_by_id, self.teacher.pk)
        self.assertEqual(question.options.count(), 2)

    def test_api_endpoint_requires_teacher(self):
        guardian = User.objects.create_user(
            phone='0722222222',
            password='1234',
            role=Role.GUARDIAN,
        )
        self.client.force_login(guardian)
        response = self.client.post(
            reverse('core:bulk_create_questions_api'),
            data='{"questions":[]}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_api_endpoint_creates_questions(self):
        self.client.force_login(self.teacher)
        payload = {
            'questions': [
                {
                    'quiz': 'API created question?',
                    'sub_strand_slug': self.sub_strand.slug,
                    'difficulty': 'Medium',
                    'quiz_type': 'Multiple Choice',
                    'choices': [
                        {'option': 'A', 'is_correct': False},
                        {'option': 'B', 'is_correct': True},
                    ],
                },
            ],
        }
        response = self.client.post(
            reverse('core:bulk_create_questions_api'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['created'], 1)
        question = Question.objects.get(uuid=body['results'][0]['question_uuid'])
        self.assertFalse(question.is_active)
        self.assertEqual(Option.objects.filter(question=question).count(), 2)

    def test_bulk_import_page_requires_teacher(self):
        guardian = User.objects.create_user(
            phone='0733333333',
            password='1234',
            role=Role.GUARDIAN,
        )
        self.client.force_login(guardian)
        response = self.client.get(reverse('core:bulk_question_import'))
        self.assertEqual(response.status_code, 302)

    def test_bulk_import_page_renders_for_teacher(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('core:bulk_question_import'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bulk Question Import')
