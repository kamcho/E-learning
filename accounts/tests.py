import json
import sqlite3
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import Role

User = get_user_model()

GOOGLE_SETTINGS = {
    'GOOGLE_CLIENT_ID': 'test-client-id.apps.googleusercontent.com',
    'GOOGLE_CLIENT_IDS': ['test-client-id.apps.googleusercontent.com'],
}


class GoogleAuthTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(reverse('accounts:signin'))
        self.token_payload = {
            'sub': 'google-sub-123',
            'email': 'guardian@gmail.com',
            'email_verified': True,
            'given_name': 'Jane',
            'family_name': 'Doe',
            'aud': 'test-client-id.apps.googleusercontent.com',
        }

    def _post_google_credential(self, credential='fake-token', next_url=''):
        return self.client.post(
            reverse('accounts:google_auth'),
            data=json.dumps({'credential': credential, 'next': next_url}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
        )

    @override_settings(**GOOGLE_SETTINGS)
    @patch('accounts.views.verify_google_credential')
    def test_google_sign_in_creates_guardian_and_requires_phone_link(self, verify):
        verify.return_value = self.token_payload
        session = self.client.session
        session.save()
        response = self._post_google_credential()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['redirect'], reverse('accounts:complete_profile'))
        user = User.objects.get(google_id='google-sub-123')
        self.assertEqual(user.role, Role.GUARDIAN)
        self.assertIsNone(user.phone)
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    @override_settings(**GOOGLE_SETTINGS)
    @patch('accounts.views.verify_google_credential')
    def test_google_sign_in_existing_user_redirects_to_dashboard(self, verify):
        user = User.objects.create_user(
            phone='0712345678',
            password='1234',
            role=Role.GUARDIAN,
            email='guardian@gmail.com',
            google_id='google-sub-123',
            first_name='Jane',
            last_name='Doe',
        )
        verify.return_value = self.token_payload
        response = self._post_google_credential()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['redirect'], reverse('accounts:guardian_dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    @override_settings(**GOOGLE_SETTINGS)
    @patch('accounts.views.verify_google_credential')
    def test_google_sign_in_links_email_only_account(self, verify):
        user = User.objects.create_user(
            phone='0798765432',
            password='1234',
            role=Role.GUARDIAN,
            email='guardian@gmail.com',
            first_name='Jane',
            last_name='Doe',
        )
        verify.return_value = self.token_payload
        response = self._post_google_credential()
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.google_id, 'google-sub-123')

    @override_settings(**GOOGLE_SETTINGS)
    @patch('accounts.views.verify_google_credential')
    def test_complete_profile_keeps_user_logged_in(self, verify):
        verify.return_value = {
            **self.token_payload,
            'sub': 'google-sub-new',
            'email': 'newguardian@gmail.com',
        }
        session = self.client.session
        session.save()
        response = self._post_google_credential()
        self.assertTrue(response.json()['ok'])
        self.assertTrue(self.client.session.get('_auth_user_id'))

        # Ensure CSRF cookie is available for the HTML form POST.
        self.client.get(reverse('accounts:complete_profile'))
        response = self.client.post(
            reverse('accounts:complete_profile'),
            {
                'phone': '0711223344',
                'password': '5678',
                'confirm_password': '5678',
            },
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('/accounts/signin/', response['Location'])
        self.assertTrue(self.client.session.get('_auth_user_id'))

        # Session still works on the next request (not forced to re-login).
        dash = self.client.get(response['Location'])
        self.assertEqual(dash.status_code, 200)
        user = User.objects.get(google_id='google-sub-new')
        self.assertEqual(user.phone, '0711223344')
        self.assertTrue(user.check_password('5678'))

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_google_sign_in_not_configured(self):
        response = self._post_google_credential()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertIn('not configured', response.json()['error'].lower())

    @override_settings(**GOOGLE_SETTINGS)
    def test_google_sign_in_missing_credential(self):
        response = self.client.post(
            reverse('accounts:google_auth'),
            data=json.dumps({}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Missing Google credential', response.json()['error'])


class SwitchRoleTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            phone='0799999999',
            password='1234',
            first_name='Super',
            last_name='User',
        )
        self.guardian = User.objects.create_user(
            phone='0788888888',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Guard',
            last_name='Ian',
        )
        self.client = Client()

    def test_superuser_can_change_role_in_database(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse('accounts:switch_role'),
            {'role': Role.GUARDIAN},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:guardian_dashboard'))
        self.superuser.refresh_from_db()
        self.assertEqual(self.superuser.role, Role.GUARDIAN)
        self.assertTrue(self.superuser.is_superuser)

    def test_non_superuser_cannot_switch_role(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse('accounts:switch_role'),
            {'role': Role.ADMIN},
        )
        self.assertEqual(response.status_code, 302)
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.role, Role.GUARDIAN)

    def test_role_switcher_visible_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('accounts:admin_dashboard'))
        self.assertContains(response, 'Switch role')
        self.assertContains(response, 'switch-role')

    def test_role_switcher_hidden_for_guardian(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('core:landing'))
        self.assertNotContains(response, 'Switch role')


class AdminDashboardStatCardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='0712345678',
            password='1234',
            role=Role.ADMIN,
            first_name='Admin',
            last_name='Boss',
        )
        self.client = Client()

    def test_admin_dashboard_renders_stat_cards(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('accounts:admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'stat-card-grid')
        self.assertContains(response, 'Total users')
        self.assertContains(response, 'Total students')
        self.assertContains(response, 'Active subjects')
        self.assertContains(response, 'Active quizzes')
        self.assertContains(response, 'stat-card-icon--blue')
        self.assertContains(response, 'stat-card-icon--orange')
        self.assertContains(response, 'stat-card-icon--amber')
        self.assertContains(response, 'stat-card-icon--emerald')
        self.assertContains(response, 'stat-card-footer-highlight')
        self.assertContains(response, 'stat-card-footer-note')


class AdminDatabaseBackupTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='0712345678',
            password='1234',
            role=Role.ADMIN,
            first_name='Admin',
            last_name='Boss',
        )
        self.guardian = User.objects.create_user(
            phone='0723456789',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Regular',
            last_name='User',
        )

    def test_database_backup_page_is_restricted_to_admins(self):
        response = self.client.get(reverse('accounts:admin_database_backup'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:signin'), response.url)

        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:admin_database_backup'))
        self.assertRedirects(response, reverse('core:landing'))

    def test_admin_can_create_and_download_valid_sqlite_backup(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse('accounts:admin_database_backup'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Create and download backup')

        response = self.client.post(reverse('accounts:admin_database_backup'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('.sqlite3', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')

        backup_data = b''.join(response.streaming_content)
        response.close()
        with sqlite3.connect(':memory:') as database:
            database.deserialize(backup_data)
            tables = {
                row[0]
                for row in database.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'",
                )
            }
        self.assertIn('accounts_myuser', tables)


class GuardianDashboardAutoSelectTests(TestCase):
    def setUp(self):
        from accounts.models import LinkedStudents, Student
        from subjects.models import GradeLevel

        self.guardian = User.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Parent',
            last_name='Test',
        )
        self.grade = GradeLevel.objects.create(
            name='Grade 4', slug='grade-4', level='Upper Primary',
        )
        self.student1 = Student.objects.create(
            first_name='Child', middle_name='A', last_name='One',
            grade_level=self.grade, gender='Male',
        )
        self.student2 = Student.objects.create(
            first_name='Child', middle_name='B', last_name='Two',
            grade_level=self.grade, gender='Female',
        )
        link = LinkedStudents.objects.create(user=self.guardian)
        link.students.add(self.student1, self.student2)
        self.client = Client()

    def test_dashboard_auto_selects_first_learner_without_modal(self):
        """Visiting /accounts/dashboard/ without ?student= should auto-select the first learner."""
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:guardian_dashboard'))
        self.assertEqual(response.status_code, 200)
        # The first learner's name should appear in the hero section
        self.assertContains(response, self.student1.first_name)
        # The blocking modal should NOT be open (require_learner_selection is False)
        self.assertFalse(response.context['require_learner_selection'])
        self.assertNotContains(response, 'gd-learner-overlay is-open')

    def test_dashboard_respects_student_query_param(self):
        """Visiting with ?student=<uuid> should select that specific learner."""
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse('accounts:guardian_dashboard'),
            {'student': str(self.student2.uuid)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student2.first_name)

    def test_dashboard_persists_selection_in_session(self):
        """After selecting student2 via query param, revisiting without param should remember student2."""
        self.client.force_login(self.guardian)
        # First visit: select student2 explicitly
        self.client.get(
            reverse('accounts:guardian_dashboard'),
            {'student': str(self.student2.uuid)},
        )
        # Second visit: no query param — should remember student2 from session
        response = self.client.get(reverse('accounts:guardian_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student2.first_name)

    def test_single_learner_auto_selects_without_modal(self):
        """Guardian with only one learner should see dashboard directly."""
        from accounts.models import LinkedStudents, Student

        solo_guardian = User.objects.create_user(
            phone='0755555555',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Solo',
            last_name='Parent',
        )
        solo_student = Student.objects.create(
            first_name='Only', middle_name='C', last_name='Child',
            grade_level=self.grade, gender='Male',
        )
        link = LinkedStudents.objects.create(user=solo_guardian)
        link.students.add(solo_student)

        self.client.force_login(solo_guardian)
        response = self.client.get(reverse('accounts:guardian_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, solo_student.first_name)
        self.assertFalse(response.context['require_learner_selection'])
        self.assertNotContains(response, 'gd-learner-overlay is-open')

    def test_dashboard_shows_stat_cards_and_learner_cards(self):
        """Dashboard renders aggregate stat cards, linked learners link cards, and subscription panel."""
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:guardian_dashboard'))
        self.assertEqual(response.status_code, 200)
        # Check user dashboard header
        self.assertContains(response, 'Guardian Dashboard')
        self.assertContains(response, 'Linked Learners')
        # Check stat cards exist
        self.assertContains(response, 'Learners Avg Score')
        self.assertContains(response, 'Exams Completed')
        self.assertContains(response, 'Subscription')
        # Check learner link cards exist for both students
        self.assertContains(response, f'id="learner-card-{self.student1.uuid}"')
        self.assertContains(response, f'id="learner-card-{self.student2.uuid}"')
        self.assertContains(response, f'?student={self.student1.uuid}')
        self.assertContains(response, f'?student={self.student2.uuid}')
        # Check Add Learner card exists
        self.assertContains(response, 'id="learner-card-add"')
        self.assertContains(response, reverse('accounts:add_learner'))
        # Specific learner report sections should NOT be shown on general dashboard
        self.assertNotContains(response, 'Viewing Learner Report')
        self.assertNotContains(response, 'Early pathway indicators')

    def test_viewing_specific_learner_shows_full_learner_report(self):
        """Visiting with ?student=<uuid> shows detailed learner report and back link."""
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse('accounts:guardian_dashboard'),
            {'student': str(self.student1.uuid)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Viewing Learner Report')
        self.assertContains(response, 'Back to Guardian Dashboard')
        self.assertContains(response, self.student1.first_name)
        self.assertContains(response, 'Attempt Score Analysis')
        self.assertContains(response, 'Learning activity')
        self.assertContains(response, 'Achievements')


class AddLearnerTests(TestCase):
    def setUp(self):
        from accounts.models import Student
        from subjects.models import GradeLevel

        self.guardian = User.objects.create_user(
            phone='0712345678',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Parent',
            last_name='User',
        )
        self.grade = GradeLevel.objects.create(
            name='Grade 5', slug='grade-5', level='Upper Primary',
        )
        self.client = Client()

    def test_add_learner_page_excludes_middle_name(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:add_learner'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'First Name')
        self.assertContains(response, 'Last Name')
        self.assertNotContains(response, 'Middle Name')
        self.assertNotContains(response, 'name="middle_name"')

    def test_add_learner_submission_succeeds_without_middle_name(self):
        from accounts.models import Student
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse('accounts:add_learner'),
            {
                'first_name': 'Amani',
                'last_name': 'Kamau',
                'grade_level': str(self.grade.id),
                'gender': 'Female',
                'dob': '2015-05-10',
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Student.objects.get(first_name='Amani', last_name='Kamau')
        self.assertEqual(created.middle_name, '')
        self.assertEqual(created.grade_level, self.grade)
        self.assertIn(f'?student={created.uuid}', response.url)
        # Check linked to guardian
        self.assertTrue(self.guardian.linked_students.filter(students=created).exists())


class UserActionLogTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.guardian = get_user_model().objects.create_user(
            phone='0777000101',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Audit',
            last_name='Guardian',
        )

    def test_log_user_action_persists_object_reference(self):
        from accounts.audit import log_user_action
        from accounts.models import UserActionLog

        log_user_action(
            action='test.manual',
            verb='create',
            user=self.guardian,
            obj=self.guardian,
            metadata={'demo': True},
        )
        row = UserActionLog.objects.get(action='test.manual')
        self.assertEqual(row.user_id, self.guardian.pk)
        self.assertEqual(row.object_type, 'accounts.MyUser')
        self.assertEqual(row.object_id, str(self.guardian.pk))

    def test_question_save_creates_audit_row(self):
        from accounts.models import UserActionLog
        from core.models import Question
        from subjects.models import Discipline, GradeLevel, Strand, Subject, SubStrand

        grade = GradeLevel.objects.create(name='Grade 3', slug='grade-3-audit', level='Lower Primary')
        discipline = Discipline.objects.create(name='Math A', slug='math-audit')
        subject = Subject.objects.create(
            name='Math G3',
            slug='math-g3-audit',
            grade_level=grade,
            discipline=discipline,
        )
        strand = Strand.objects.create(name='Num', slug='num-g3-audit', subject=subject, order=1)
        sub = SubStrand.objects.create(name='Add', slug='add-g3-audit', strand=strand, order=1)

        self.client.force_login(self.guardian)
        self.client.get(reverse('accounts:guardian_dashboard'))

        Question.objects.create(
            quiz='Audit signal question?',
            difficulty='Easy',
            quiz_type='OpenEnded',
            sub_strand=sub,
            created_by=self.guardian,
        )
        self.assertTrue(
            UserActionLog.objects.filter(
                action='core.Question.create',
                verb='create',
                object_type='core.Question',
            ).exists()
        )

    def test_admin_action_logs_requires_admin(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:admin_action_logs'))
        self.assertEqual(response.status_code, 302)

    def test_subject_performance_cards_include_strands(self):
        from accounts.subject_perf_cards import build_subject_performance_cards
        from core.models import UserAttempts

        breakdown = [{
            'subject_id': 1,
            'quiz__subject__name': 'Math',
            'attempts': 2,
            'avg_score': 80,
            'best_score': 90,
        }]
        qs = UserAttempts.objects.none()
        cards = build_subject_performance_cards(qs, breakdown)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['overall_pct'], 80)

    def test_bulk_question_creates_grouped_in_list(self):
        from accounts.audit_grouping import build_activity_display_items
        from accounts.models import UserActionLog
        from django.utils import timezone

        base = timezone.now()
        for index in range(5):
            row = UserActionLog(
                user=self.guardian,
                actor_label='Test',
                action='core.Question.create',
                verb='create',
                object_type='core.Question',
                object_id=str(1000 + index),
                object_repr=f'Question {index}',
                metadata={'source': 'model_signal'},
            )
            row.save()
            UserActionLog.objects.filter(pk=row.pk).update(
                created_at=base.replace(microsecond=index)
            )

        qs = UserActionLog.objects.filter(action='core.Question.create', user=self.guardian)
        items = build_activity_display_items(qs)
        batches = [item for item in items if item['kind'] == 'batch']
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]['count'], 5)


class TeacherCurriculumViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from subjects.models import Discipline, GradeLevel, Strand, Subject, SubStrand

        cls.teacher = User.objects.create_user(
            phone='0799999999',
            password='1234',
            role=Role.TEACHER,
        )
        cls.guardian = User.objects.create_user(
            phone='0788888888',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.grade = GradeLevel.objects.create(name='Grade 4', slug='grade-4', level='Upper Primary')
        cls.discipline = Discipline.objects.create(name='Math', slug='math')
        cls.subject = Subject.objects.create(
            name='Mathematics',
            slug='mathematics-g4',
            grade_level=cls.grade,
            discipline=cls.discipline,
        )
        cls.strand = Strand.objects.create(name='Numbers', slug='numbers-g4', subject=cls.subject)
        cls.sub_strand = SubStrand.objects.create(
            name='Addition',
            slug='addition-g4',
            strand=cls.strand,
        )

    def setUp(self):
        self.client = Client()

    def test_teacher_dashboard_shows_grade_cards(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('accounts:teacher_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add questions by grade')
        self.assertContains(response, reverse('accounts:teacher_curriculum_grade', kwargs={'grade_slug': 'grade-4'}))

    def test_curriculum_flow_renders_sub_strand_prompt(self):
        from subjects.models import SubStrandObjective

        SubStrandObjective.objects.create(
            name='Add two-digit numbers with regrouping.',
            slug='add-two-digit-regroup',
            sub_strand=self.sub_strand,
            order=1,
        )
        self.client.force_login(self.teacher)
        url = reverse(
            'accounts:teacher_curriculum_sub_strand',
            kwargs={
                'grade_slug': 'grade-4',
                'subject_slug': 'mathematics-g4',
                'strand_slug': 'numbers-g4',
                'sub_strand_slug': 'addition-g4',
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Build AI prompt')
        self.assertContains(response, 'ai-wizard-total')
        self.assertContains(response, 'Multiple Choice')
        self.assertNotContains(response, 'Sub-strand objectives')
        self.assertNotContains(response, 'Add one question manually')
        self.assertNotContains(response, 'What format we expect')
        self.assertContains(response, 'Generate prompt')
        self.assertContains(response, 'id="ai-prompt-generate-url"')
        self.assertContains(response, '/accounts/teacher-dashboard/ai-question-prompt/')
        self.assertContains(response, 'Review questions')
        self.assertContains(response, 'Approve all valid')

    def test_guardian_cannot_access_teacher_curriculum(self):
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse('accounts:teacher_curriculum_grade', kwargs={'grade_slug': 'grade-4'}),
        )
        self.assertEqual(response.status_code, 302)

    def test_ai_prompt_generate_uses_type_mix(self):
        from accounts.teacher_curriculum import build_ai_question_prompt

        self.client.force_login(self.teacher)
        url = reverse('accounts:teacher_ai_question_prompt_generate')
        payload = {
            'sub_strand_id': self.sub_strand.pk,
            'total_count': 5,
            'type_counts': {
                'Multiple Choice': 2,
                'Fill in the Blank': 1,
                'True or False': 1,
                'OpenEnded': 1,
                'Matching': 0,
            },
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertIn('Create exactly 5 assessment questions', body['prompt'])
        self.assertIn('Multiple Choice: 2', body['prompt'])
        expected = build_ai_question_prompt(
            self.sub_strand,
            total_count=5,
            type_counts=payload['type_counts'],
        )
        self.assertEqual(body['prompt'], expected)


class UserCanViewLearnerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import LinkedStudents, Student
        from subjects.models import GradeLevel

        cls.guardian = User.objects.create_user(
            phone='0722222001',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.superuser = User.objects.create_superuser(
            phone='0722222002',
            password='1234',
            role=Role.ADMIN,
        )
        cls.grade = GradeLevel.objects.create(
            name='Grade 3', slug='grade-3-la', level='Lower Primary',
        )
        cls.student = Student.objects.create(
            first_name='Test',
            last_name='Learner',
            grade_level=cls.grade,
        )
        link = LinkedStudents.objects.create(user=cls.guardian)
        link.students.add(cls.student)

    def test_superuser_can_view_any_learner(self):
        from accounts.learner_access import user_can_view_learner

        self.assertTrue(user_can_view_learner(self.superuser, self.student))

    def test_unlinked_user_cannot_view_learner(self):
        from accounts.learner_access import user_can_view_learner

        stranger = User.objects.create_user(
            phone='0722222999',
            password='1234',
            role=Role.TEACHER,
        )
        self.assertFalse(user_can_view_learner(stranger, self.student))

    def test_linked_guardian_can_view_learner(self):
        from accounts.learner_access import user_can_view_learner

        self.assertTrue(user_can_view_learner(self.guardian, self.student))


class LearnerAccessAndGuardianWallTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import LinkedStudents, Student
        from subjects.models import GradeLevel

        cls.guardian = User.objects.create_user(
            phone='0711111001',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.other_guardian = User.objects.create_user(
            phone='0711111002',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.staff_admin = User.objects.create_user(
            phone='0711111003',
            password='1234',
            role=Role.ADMIN,
            is_staff=True,
        )
        cls.grade = GradeLevel.objects.create(
            name='Grade 4', slug='grade-4-access', level='Upper Primary',
        )
        cls.linked_student = Student.objects.create(
            first_name='Linked',
            last_name='Learner',
            grade_level=cls.grade,
        )
        cls.other_student = Student.objects.create(
            first_name='Other',
            last_name='Learner',
            grade_level=cls.grade,
        )
        link = LinkedStudents.objects.create(user=cls.guardian)
        link.students.add(cls.linked_student)
        other_link = LinkedStudents.objects.create(user=cls.other_guardian)
        other_link.students.add(cls.other_student)

    def setUp(self):
        self.client = Client()

    def test_guardian_cannot_access_admin_dashboard(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:guardian_dashboard'))

    def test_guardian_cannot_access_teacher_dashboard(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse('accounts:teacher_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:guardian_dashboard'))

    def test_staff_admin_can_view_unlinked_learner_analytics(self):
        self.client.force_login(self.staff_admin)
        response = self.client.get(
            reverse('accounts:student_analytics', kwargs={'student_uuid': self.other_student.uuid}),
        )
        self.assertEqual(response.status_code, 200)

    def test_guardian_cannot_view_other_guardians_learner_analytics(self):
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse('accounts:student_analytics', kwargs={'student_uuid': self.other_student.uuid}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:guardian_dashboard'))


class MemberLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import LinkedStudents, Student
        from subjects.models import GradeLevel

        cls.admin = User.objects.create_user(
            phone='0799990001',
            password='1234',
            role=Role.ADMIN,
            is_staff=True,
        )
        cls.guardian = User.objects.create_user(
            phone='0799990002',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.target_user = User.objects.create_user(
            phone='0799990003',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.grade = GradeLevel.objects.create(
            name='Grade 5', slug='grade-5-lifecycle', level='Upper Primary',
        )
        cls.student = Student.objects.create(
            first_name='Lifecycle',
            last_name='Learner',
            grade_level=cls.grade,
        )
        link = LinkedStudents.objects.create(user=cls.guardian)
        link.students.add(cls.student)

    def setUp(self):
        self.client = Client()

    def test_soft_delete_user_blocks_login_and_can_restore(self):
        from accounts.member_lifecycle import restore_user, soft_delete_user

        soft_delete_user(user=self.target_user, actor=self.admin)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)
        self.assertIsNotNone(self.target_user.deleted_at)

        self.client.force_login(self.target_user)
        response = self.client.get(reverse('accounts:guardian_dashboard'))
        self.assertEqual(response.status_code, 302)

        restore_user(user=self.target_user, actor=self.admin)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.is_active)

    def test_soft_deleted_learner_hidden_from_guardian_dashboard_context(self):
        from accounts.member_lifecycle import soft_delete_student
        from accounts.views import _get_guardian_students

        soft_delete_student(student=self.student, actor=self.admin)
        rows = _get_guardian_students(self.guardian)
        self.assertEqual(rows, [])

    def test_admin_soft_delete_and_hard_delete_learner(self):
        from accounts.models import Student
        from core.models import UserAttempts

        self.client.force_login(self.admin)
        url = reverse('accounts:admin_student_lifecycle', kwargs={'student_uuid': self.student.uuid})

        response = self.client.post(url, {'action': 'soft_delete'})
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

        response = self.client.post(url, {'action': 'hard_delete', 'confirm': 'DELETE'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(UserAttempts.objects.filter(student_id=self.student.pk).exists())

    def test_admin_cannot_delete_self(self):
        self.client.force_login(self.admin)
        url = reverse('accounts:admin_user_lifecycle', kwargs={'user_id': self.admin.pk})
        response = self.client.post(url, {'action': 'soft_delete'})
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
