import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Role
from core.models import Option, Question
from subjects.models import Discipline, GradeLevel, Strand, SubStrand, Subject, TeacherSubject

User = get_user_model()


class QuestionReformatMathTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            phone='0755555501',
            password='1234',
            role=Role.TEACHER,
        )
        self.grade = GradeLevel.objects.create(name='G6 RF', slug='g6-rf', level='Upper Primary')
        self.discipline = Discipline.objects.create(name='Math RF', slug='math-rf')
        self.subject = Subject.objects.create(
            name='Mathematics',
            slug='math-rf-subj',
            grade_level=self.grade,
            discipline=self.discipline,
        )
        TeacherSubject.objects.create(teacher=self.teacher, subject=self.subject)
        strand = Strand.objects.create(name='Numbers', slug='nums-rf', subject=self.subject)
        self.sub = SubStrand.objects.create(name='Fractions', slug='frac-rf', strand=strand)
        self.question = Question.objects.create(
            quiz='Start at 1/3 and add 1/6.',
            difficulty='Easy',
            quiz_type='Multiple Choice',
            sub_strand=self.sub,
            created_by=self.teacher,
        )
        Option.objects.create(question=self.question, option='1/3, 1/2, 2/3', is_correct=True)

    @patch('core.ai.service.ai_service.run')
    def test_preview_returns_reformatted_payload(self, run_mock):
        run_mock.return_value = {
            'quiz': 'Start at $\\frac{1}{3}$ and add $\\frac{1}{6}$.',
            'options': [{'uuid': str(self.question.options.first().uuid), 'option': '$\\frac{1}{3}$, $\\frac{1}{2}$, $\\frac{2}{3}$'}],
        }
        self.client.force_login(self.teacher)
        url = reverse('core:question_reformat_math', kwargs={'question_uuid': self.question.uuid})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'preview'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('$\\frac{1}{3}$', body['reformatted']['quiz'])

    @patch('core.question_reformat.apply_question_math_reformat')
    def test_apply_updates_question(self, apply_mock):
        self.client.force_login(self.teacher)
        url = reverse('core:question_reformat_math', kwargs={'question_uuid': self.question.uuid})
        response = self.client.post(
            url,
            data=json.dumps({
                'action': 'apply',
                'quiz': '$\\frac{1}{2}$?',
                'options': [{'uuid': str(self.question.options.first().uuid), 'option': 'A'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        apply_mock.assert_called_once()
