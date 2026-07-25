import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Role

User = get_user_model()

GOOGLE_SETTINGS = {
    'GOOGLE_CLIENT_ID': 'test-client-id.apps.googleusercontent.com',
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
