from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import LinkedStudents, Role, Student
from core.error_views import server_error
from core.models import Option, Question, Quiz
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


class DemoPracticeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grade = GradeLevel.objects.create(name='Grade 6', slug='grade-6', level='Upper Primary')
        cls.discipline = Discipline.objects.create(name='Science', slug='science')
        cls.subject = Subject.objects.create(
            name='Agriculture',
            slug='agriculture-g6',
            grade_level=cls.grade,
            discipline=cls.discipline,
        )
        cls.strand = Strand.objects.create(name='Plants', slug='plants-g6', subject=cls.subject)
        cls.sub_strand = SubStrand.objects.create(name='Roots', slug='roots-g6', strand=cls.strand)

        for index in range(8):
            question = Question.objects.create(
                quiz=f'Root question {index}?',
                quiz_type='Multiple Choice',
                difficulty='Easy',
                sub_strand=cls.sub_strand,
                score=1,
            )
            Option.objects.create(question=question, option='Wrong', is_correct=False)
            Option.objects.create(question=question, option='Correct', is_correct=True)

    def test_demo_wizard_renders_anonymously(self):
        response = self.client.get(reverse('core:demo_wizard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Try a free practice test')
        self.assertContains(response, 'No account needed')
        self.assertContains(response, 'Create free account')
        self.assertContains(response, 'Choose a grade')
        self.assertEqual(response.context['phase'], 'grade')
        self.assertIsNone(response.context['active_grade'])

    def test_demo_wizard_renders_for_authenticated_user(self):
        user = User.objects.create_user(phone='0722000000', password='1234', first_name='Jane')
        self.client.force_login(user)
        response = self.client.get(reverse('core:demo_wizard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome back, Jane')
        self.assertContains(response, 'Go to Exam Center')
        self.assertNotContains(response, 'No account needed')
        self.assertNotContains(response, 'Create free account')

    def test_demo_wizard_requires_grade_before_subjects(self):
        response = self.client.get(reverse('core:demo_wizard'), {'grade': self.grade.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['phase'], 'subject')
        self.assertEqual(response.context['active_grade'], self.grade)
        self.assertContains(response, self.subject.name)

    def test_demo_start_builds_seven_question_session(self):
        response = self.client.post(reverse('core:demo_start'), {
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:demo_take'))
        session = self.client.session['practice_demo']
        self.assertEqual(len(session['question_ids']), 7)

    def test_demo_take_grades_answer_and_shows_feedback(self):
        self.client.post(reverse('core:demo_start'), {
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })
        take_url = reverse('core:demo_take')
        response = self.client.get(take_url)
        self.assertEqual(response.status_code, 200)
        question_uuid = self.client.session['practice_demo']['question_ids'][0]
        question = Question.objects.get(uuid=question_uuid)
        wrong = question.options.filter(is_correct=False).first()
        response = self.client.post(take_url, {'action': 'submit', 'answer': str(wrong.uuid)})
        self.assertEqual(response.status_code, 302)
        response = self.client.get(take_url)
        self.assertContains(response, 'Not quite')
        self.assertContains(response, 'demo-ai-box')


class AutoCustomQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Parent',
            last_name='One',
        )
        cls.grade = GradeLevel.objects.create(name='Grade 6', slug='grade-6', level='Upper Primary')
        cls.discipline = Discipline.objects.create(name='Languages', slug='languages')
        cls.subject = Subject.objects.create(
            name='English',
            slug='english',
            grade_level=cls.grade,
            discipline=cls.discipline,
        )
        cls.strand = Strand.objects.create(name='Reading', slug='reading-g6', subject=cls.subject)
        cls.sub_strand = SubStrand.objects.create(
            name='Comprehension',
            slug='comprehension-g6',
            strand=cls.strand,
        )
        cls.student = Student.objects.create(
            first_name='Sharon',
            middle_name='',
            last_name='Mwaka',
            grade_level=cls.grade,
        )
        link = LinkedStudents.objects.create(user=cls.guardian)
        link.students.add(cls.student)

        for index in range(12):
            question = Question.objects.create(
                quiz=f'English question {index}?',
                quiz_type='Multiple Choice',
                difficulty='Easy',
                sub_strand=cls.sub_strand,
                score=1,
                is_active=True,
            )
            Option.objects.create(question=question, option='Wrong', is_correct=False)
            Option.objects.create(question=question, option='Correct', is_correct=True)

    def test_exams_list_auto_creates_custom_quiz_when_none_exist(self):
        self.client.force_login(self.guardian)
        url = reverse('core:exams_list')
        response = self.client.get(url, {
            'student': str(self.student.uuid),
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })

        self.assertEqual(response.status_code, 302)
        quiz = Quiz.objects.get(subject=self.subject, created_by=self.guardian)
        self.assertTrue(quiz.title.startswith('Custom'))
        self.assertEqual(quiz.test_size, 12)
        self.assertEqual(
            response.url,
            reverse('core:test_info', kwargs={
                'quiz_uuid': quiz.uuid,
                'student_uuid': self.student.uuid,
            }),
        )

    def test_exams_list_reuses_existing_custom_quiz(self):
        self.client.force_login(self.guardian)
        params = {
            'student': str(self.student.uuid),
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        }
        first = self.client.get(reverse('core:exams_list'), params)
        self.assertEqual(first.status_code, 302)
        quiz = Quiz.objects.get(created_by=self.guardian)
        self.assertEqual(Quiz.objects.filter(title__startswith='Custom').count(), 1)

        second = self.client.get(reverse('core:exams_list'), params)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, quiz.title)
        self.assertEqual(Quiz.objects.filter(title__startswith='Custom').count(), 1)

    def test_whole_subject_ignores_stale_sub_strand_param(self):
        self.client.force_login(self.guardian)
        params = {
            'student': str(self.student.uuid),
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
            'sub_strand': 'roots-g6',
        }
        response = self.client.get(reverse('core:exams_list'), params)
        self.assertEqual(response.status_code, 302)
        quiz = Quiz.objects.get(title__startswith='Custom', subject=self.subject)
        self.assertGreaterEqual(quiz.questions.filter(is_active=True).count(), 1)


class PrivacyPolicyTests(TestCase):
    def test_privacy_policy_page_is_public(self):
        response = self.client.get(reverse('core:privacy_policy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Privacy Policy')
        self.assertContains(response, 'Google user data')
        self.assertContains(response, 'Limited use')
        self.assertContains(response, 'Retention and deletion')


class LandingPageNavbarTests(TestCase):
    def setUp(self):
        self.guardian = User.objects.create_user(
            phone='0722222222',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Parent',
            last_name='User',
        )
        self.admin = User.objects.create_user(
            phone='0733333333',
            password='1234',
            role=Role.ADMIN,
            first_name='Admin',
            last_name='User',
        )

    def test_anonymous_user_does_not_see_dashboard_or_curriculum_builder_in_navbar(self):
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        # Check navbar-links and navbar-drawer-links blocks
        navbar_chunk = html[html.find('<div class="navbar-links">'):html.find('</div>\n\n      <div class="navbar-actions">')]
        self.assertNotIn('Curriculum Builder', navbar_chunk)
        self.assertNotIn('Dashboard', navbar_chunk)

    def test_authenticated_guardian_sees_dashboard_link_not_curriculum_builder_in_navbar(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        navbar_chunk = html[html.find('<div class="navbar-links">'):html.find('</div>\n\n      <div class="navbar-actions">')]
        self.assertNotIn('Curriculum Builder', navbar_chunk)
        self.assertIn(f'<a href="{reverse("accounts:guardian_dashboard")}">Dashboard</a>', navbar_chunk)

    def test_authenticated_admin_sees_admin_dashboard_in_navbar(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        navbar_chunk = html[html.find('<div class="navbar-links">'):html.find('</div>\n\n      <div class="navbar-actions">')]
        self.assertNotIn('Curriculum Builder', navbar_chunk)
        self.assertIn(f'<a href="{reverse("accounts:admin_dashboard")}">Dashboard</a>', navbar_chunk)


class ServerErrorDiagnosticsTests(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()

    def test_platform_admin_can_copy_current_traceback(self):
        admin = User.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.ADMIN,
            first_name='Admin',
            last_name='User',
        )
        request = self.request_factory.get('/')
        request._cached_user = admin

        try:
            raise RuntimeError('dashboard failure marker')
        except RuntimeError:
            response = server_error(request)

        content = response.content.decode('utf-8')
        self.assertEqual(response.status_code, 500)
        self.assertIn('Copy traceback', content)
        self.assertIn('RuntimeError: dashboard failure marker', content)
        self.assertIn("Path: /", content)

    def test_traceback_is_not_shown_to_anonymous_visitors(self):
        request = self.request_factory.get('/')
        request._cached_user = AnonymousUser()

        try:
            raise RuntimeError('private failure marker')
        except RuntimeError:
            response = server_error(request)

        content = response.content.decode('utf-8')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('Copy traceback', content)
        self.assertNotIn('private failure marker', content)
