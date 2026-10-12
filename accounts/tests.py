import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
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
