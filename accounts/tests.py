from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Role

User = get_user_model()


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
