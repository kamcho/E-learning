import pyotp
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.totp import encrypt_totp_secret, generate_totp_secret


class TotpAuthTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            phone='0712345678',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Two',
            last_name='Factor',
        )
        self.secret = generate_totp_secret()
        self.user.totp_secret = encrypt_totp_secret(self.secret)
        self.user.totp_enabled = True
        self.user.save(update_fields=['totp_secret', 'totp_enabled'])
        self.client = Client()

    def test_signin_redirects_to_totp_verify(self):
        response = self.client.post(reverse('accounts:signin'), {
            'phone': '0712345678',
            'password': '1234',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:totp_verify'))
        self.assertIn('pending_2fa_user_id', self.client.session)

    def test_totp_verify_completes_login(self):
        self.client.post(reverse('accounts:signin'), {
            'phone': '0712345678',
            'password': '1234',
        })
        code = pyotp.TOTP(self.secret).now()
        response = self.client.post(reverse('accounts:totp_verify'), {'code': code})
        self.assertEqual(response.status_code, 302)
        self.assertIn('auth_2fa_user_id', self.client.session)

    def test_enable_totp_from_security_page(self):
        user = self.user
        user.totp_enabled = False
        user.totp_secret = ''
        user.save()
        self.client.force_login(user)
        self.client.post(reverse('accounts:account_security'), {'action': 'start_setup'})
        secret = self.client.session.get('totp_setup_secret')
        self.assertTrue(secret)
        code = pyotp.TOTP(secret).now()
        response = self.client.post(reverse('accounts:account_security'), {
            'action': 'confirm_setup',
            'code': code,
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.totp_enabled)
        self.assertTrue(user.totp_secret)
