from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import Role
from messenger.models import SmsMessage
from subscriptions.models import Payment, Subscription, SubscriptionPlan
from subscriptions.services import activate_subscription_from_payment

User = get_user_model()


class ActivateSubscriptionSmsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            phone='0711223344',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Sam',
            last_name='Wanjiru',
        )
        cls.plan = SubscriptionPlan.objects.create(
            name='Starter Pack',
            slug='starter-pack',
            price_kes=300,
            duration_days=30,
            max_tests=5,
        )

    def _create_pending_payment(self):
        return Payment.objects.create(
            user=self.user,
            plan=self.plan,
            amount_kes=300,
            phone_number='0711223344',
            mpesa_receipt_number='XYZ9876543',
            status=Payment.Status.PENDING,
        )

    @override_settings(
        TEXTSMS_ENABLED=True,
        TEXTSMS_API_KEY='test-key',
        TEXTSMS_PARTNER_ID='99',
        TEXTSMS_SHORTCODE='SomaKenya',
    )
    @patch('messenger.textsms.requests.post')
    def test_successful_payment_triggers_sms(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'responses': [{
                'respose-code': 200,
                'response-description': 'Success',
                'mobile': '254711223344',
                'messageid': 'sms-42',
            }],
        }

        payment = self._create_pending_payment()
        subscription = activate_subscription_from_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)

        sms = SmsMessage.objects.get(payment=payment)
        self.assertEqual(sms.status, SmsMessage.Status.SENT)
        self.assertEqual(sms.provider_message_id, 'sms-42')
        self.assertIn('Starter Pack', sms.message)

    @override_settings(TEXTSMS_ENABLED=False)
    def test_sms_skipped_when_disabled(self):
        payment = self._create_pending_payment()
        activate_subscription_from_payment(payment)
        self.assertEqual(SmsMessage.objects.count(), 0)

    @override_settings(
        TEXTSMS_ENABLED=True,
        TEXTSMS_API_KEY='test-key',
        TEXTSMS_PARTNER_ID='99',
        TEXTSMS_SHORTCODE='SomaKenya',
    )
    @patch('messenger.services.send_sms')
    def test_payment_activation_succeeds_even_if_sms_fails(self, mock_send_sms):
        from messenger.textsms import TextSmsAPIError

        mock_send_sms.side_effect = TextSmsAPIError('Gateway timeout')

        payment = self._create_pending_payment()
        subscription = activate_subscription_from_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(SmsMessage.objects.get(payment=payment).status, SmsMessage.Status.FAILED)
