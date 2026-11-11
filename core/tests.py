import hashlib

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from accounts.models import LinkedStudents, Role, Student
from core.error_views import server_error
from core.models import Option, Question, Quiz
from core.json_paste import normalize_json_paste, parse_json_paste
from core.question_import import bulk_create_questions, validate_question_item
from subjects.models import Discipline, GradeLevel, Strand, Subject, SubStrand
from subscriptions.models import GuestDemoPayment, SubscriptionPlan

User = get_user_model()


class JsonPasteTests(TestCase):
    def test_normalize_removes_line_continuation_backslashes(self):
        # Chat UIs often insert "\" before line breaks — invalid JSON until stripped.
        raw = '{\\\n "questions": []\n}'
        self.assertNotIn('\\\n', normalize_json_paste(raw))
        self.assertEqual(parse_json_paste(raw)['questions'], [])

    def test_normalize_html_entities(self):
        self.assertEqual(parse_json_paste('{"questions":&#x20;[]}')['questions'], [])

    def test_normalize_smart_quotes_from_messaging_apps(self):
        raw = '{\u201cquestions\u201d:[{\u201cquiz\u201d:\u201cParallel lines?\u201d,\u201cdifficulty\u201d:\u201cEasy\u201d}]}'
        parsed = parse_json_paste(raw)
        self.assertEqual(parsed['questions'][0]['quiz'], 'Parallel lines?')

    def test_unescape_markdown_brackets(self):
        raw = r'{"questions": \[{"quiz": "Test?", "difficulty": "Easy", "quiz_type": "OpenEnded", "choices": \[\]}\]}'
        parsed = parse_json_paste(raw)
        self.assertEqual(len(parsed['questions']), 1)
        self.assertEqual(parsed['questions'][0]['quiz'], 'Test?')


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

    def test_missing_sub_strand_id_falls_back_to_slug(self):
        cleaned = validate_question_item({
            'quiz': 'What is 1 + 1?',
            'sub_strand_id': 999999,
            'sub_strand_slug': self.sub_strand.slug,
            'difficulty': 'Easy',
            'quiz_type': 'True or False',
            'choices': [
                {'option': 'True', 'is_correct': False},
                {'option': '2', 'is_correct': True},
            ],
        })
        self.assertEqual(cleaned['sub_strand'].pk, self.sub_strand.pk)

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
        cls.single_exam_plan = SubscriptionPlan.objects.create(
            name='Grade 4–6 Exam',
            slug='grade-4-6-exam',
            plan_type=SubscriptionPlan.PlanType.SINGLE_TEST,
            grade_band=SubscriptionPlan.GradeBand.GRADE_4_TO_6,
            price_kes=15,
            max_tests=1,
        )

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

    def test_exam_wizard_renders_anonymously(self):
        response = self.client.get(reverse('core:exam_wizard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Start a free practice exam')
        self.assertContains(response, '7–10')
        self.assertContains(response, 'No account needed')
        self.assertContains(response, 'Create free account')
        self.assertContains(response, 'Choose a grade')
        self.assertEqual(response.context['phase'], 'grade')
        self.assertIsNone(response.context['active_grade'])

    def test_exam_wizard_renders_for_authenticated_user(self):
        user = User.objects.create_user(phone='0722000000', password='1234', first_name='Jane')
        self.client.force_login(user)
        response = self.client.get(reverse('core:exam_wizard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome back, Jane')
        self.assertContains(response, 'Go to Exam Center')
        self.assertNotContains(response, 'No account needed')
        self.assertNotContains(response, 'Create free account')

    def test_exam_wizard_requires_grade_before_subjects(self):
        response = self.client.get(reverse('core:exam_wizard'), {'grade': self.grade.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['phase'], 'subject')
        self.assertEqual(response.context['active_grade'], self.grade)
        self.assertContains(response, self.subject.name)

    def test_grade_three_exam_link_renders_subject_step(self):
        grade_three = GradeLevel.objects.create(
            name='Grade 3',
            slug='grade-3',
            level='Lower Primary',
        )
        response = self.client.get(reverse('core:exam_wizard'), {'grade': grade_three.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['phase'], 'subject')
        self.assertEqual(response.context['active_grade'], grade_three)

    def test_exam_start_uses_seven_to_ten_questions(self):
        response = self.client.post(reverse('core:exam_start'), {
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:exam_take'))
        session = self.client.session['practice_demo']
        self.assertGreaterEqual(len(session['question_ids']), 7)
        self.assertLessEqual(len(session['question_ids']), 10)
        self.assertEqual(len(session['question_ids']), 8)

        for index in range(8, 15):
            question = Question.objects.create(
                quiz=f'Extra question {index}?',
                quiz_type='Multiple Choice',
                difficulty='Easy',
                sub_strand=self.sub_strand,
                score=1,
            )
            Option.objects.create(question=question, option='No', is_correct=False)
            Option.objects.create(question=question, option='Yes', is_correct=True)

        self.client.post(reverse('core:exam_start'), {
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })
        self.assertEqual(len(self.client.session['practice_demo']['question_ids']), 10)

    def test_exam_take_grades_answer_and_shows_feedback(self):
        self.client.post(reverse('core:exam_start'), {
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })
        take_url = reverse('core:exam_take')
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
        self.assertContains(response, 'Listen to explanation')

    def test_guest_must_pay_after_three_questions_and_can_resume_in_same_session(self):
        self.client.post(reverse('core:exam_start'), {
            'grade': self.grade.slug,
            'subject': self.subject.slug,
            'scope': 'general',
        })
        take_url = reverse('core:exam_take')

        for index in range(3):
            demo = self.client.session['practice_demo']
            question = Question.objects.get(uuid=demo['question_ids'][index])
            correct = question.options.filter(is_correct=True).first()
            self.client.post(take_url, {'action': 'submit', 'answer': str(correct.uuid)})
            self.client.get(take_url)
            response = self.client.post(take_url, {'action': 'continue'})

        checkout_url = reverse('subscriptions:guest_demo_checkout')
        self.assertRedirects(response, checkout_url)
        response = self.client.get(checkout_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pay with M-Pesa')
        self.assertContains(response, 'no account is needed')
        question_four = Question.objects.get(
            uuid=self.client.session['practice_demo']['question_ids'][3],
        )
        response = self.client.post(take_url, {
            'action': 'submit',
            'answer': str(question_four.options.filter(is_correct=True).first().uuid),
        })
        self.assertRedirects(response, checkout_url)
        self.assertEqual(len(self.client.session['practice_demo']['answers']), 3)
        self.assertRedirects(
            self.client.get(reverse('core:exam_results')),
            checkout_url,
        )

        token = 'session-bound-token'
        session = self.client.session
        session['guest_demo_payment_token'] = token
        session.save()
        demo = self.client.session['practice_demo']
        GuestDemoPayment.objects.create(
            session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            demo_id=demo['demo_id'],
            plan=self.single_exam_plan,
            amount_kes=self.single_exam_plan.price_kes,
            phone_number='254712345678',
            status=GuestDemoPayment.Status.SUCCESS,
        )
        response = self.client.get(take_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['question_number'], 4)
        self.assertRedirects(
            self.client.get(reverse('core:exam_results')),
            take_url,
        )

    def test_old_demo_url_redirects_to_exam_url_and_preserves_query(self):
        response = self.client.get('/demo/?grade=grade-6')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, '/exam/?grade=grade-6')

    def test_exam_grade_choices_follow_curriculum_order(self):
        GradeLevel.objects.create(name='Grade 10', slug='grade-10', level='Senior Secondary')
        GradeLevel.objects.create(name='Grade 1', slug='grade-1', level='Lower Primary')
        response = self.client.get(reverse('core:exam_wizard'))
        self.assertEqual(
            [grade.slug for grade in response.context['all_grades']],
            ['grade-1', 'grade-6', 'grade-10'],
        )


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

    def test_anonymous_landing_page_highlights_start_exam(self):
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Start Exam', count=2)
        self.assertContains(response, 'class="btn btn-start-exam"')
        self.assertContains(response, 'Start Exam')
        self.assertContains(response, 'Free practice exam')
        self.assertNotContains(response, 'free demo')

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

    def test_platform_admin_diagnostics_resolve_a_lazy_request_user(self):
        admin = User.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.ADMIN,
            first_name='Admin',
            last_name='User',
        )
        request = self.request_factory.get('/')
        request.user = SimpleLazyObject(lambda: admin)

        try:
            raise RuntimeError('lazy dashboard failure marker')
        except RuntimeError:
            response = server_error(request)

        content = response.content.decode('utf-8')
        self.assertEqual(response.status_code, 500)
        self.assertIn('Copy traceback', content)
        self.assertIn('RuntimeError: lazy dashboard failure marker', content)

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
