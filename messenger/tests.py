from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import Role
from messenger.models import SmsMessage
from messenger.services import send_payment_confirmation_sms
from messenger.textsms import (
    TextSmsAPIError,
    TextSmsConfigError,
    normalize_kenyan_mobile,
    send_sms,
)
from subscriptions.models import Payment, SubscriptionPlan

User = get_user_model()


class NormalizeKenyanMobileTests(TestCase):
    def test_accepts_local_format(self):
        self.assertEqual(normalize_kenyan_mobile('0712345678'), '254712345678')

    def test_accepts_international_format(self):
        self.assertEqual(normalize_kenyan_mobile('+254712345678'), '254712345678')

    def test_rejects_invalid_number(self):
        with self.assertRaises(ValueError):
            normalize_kenyan_mobile('12345')


@override_settings(
    TEXTSMS_API_KEY='test-key',
    TEXTSMS_PARTNER_ID='99',
    TEXTSMS_SHORTCODE='Soma Smart',
)
class TextSmsClientTests(TestCase):
    @patch('messenger.textsms.requests.post')
    def test_send_sms_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'responses': [{
                'respose-code': 200,
                'response-description': 'Success',
                'mobile': '254712345678',
                'messageid': 'abc-123',
            }],
        }

        result = send_sms(mobile='0712345678', message='Hello')

        self.assertEqual(result['message_id'], 'abc-123')
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs['json']
        self.assertEqual(payload['apikey'], 'test-key')
        self.assertEqual(payload['partnerID'], '99')
        self.assertEqual(payload['shortcode'], 'Soma Smart')
        self.assertEqual(payload['mobile'], '254712345678')
        self.assertEqual(payload['message'], 'Hello')

    @patch('messenger.textsms.requests.post')
    def test_send_sms_api_error(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'responses': [{
                'respose-code': 400,
                'response-description': 'Invalid sender ID',
            }],
        }

        with self.assertRaises(TextSmsAPIError):
            send_sms(mobile='0712345678', message='Hello')

    @override_settings(TEXTSMS_API_KEY='')
    def test_send_sms_missing_config(self):
        with self.assertRaises(TextSmsConfigError):
            send_sms(mobile='0712345678', message='Hello')


class PaymentConfirmationSmsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            phone='0712345678',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Jane',
            last_name='Doe',
        )
        cls.plan = SubscriptionPlan.objects.create(
            name='Monthly Pack',
            slug='monthly-pack',
            price_kes=500,
            duration_days=30,
            max_tests=10,
        )
        cls.payment = Payment.objects.create(
            user=cls.user,
            plan=cls.plan,
            amount_kes=500,
            phone_number='0712345678',
            mpesa_receipt_number='QAB12CD34E',
            status=Payment.Status.SUCCESS,
        )

    @override_settings(TEXTSMS_ENABLED=False)
    def test_skips_when_disabled(self):
        result = send_payment_confirmation_sms(self.payment)
        self.assertIsNone(result)
        self.assertEqual(SmsMessage.objects.count(), 0)

    @override_settings(
        TEXTSMS_ENABLED=True,
        TEXTSMS_API_KEY='',
        TEXTSMS_PARTNER_ID='',
        TEXTSMS_SHORTCODE='',
    )
    def test_marks_skipped_when_not_configured(self):
        result = send_payment_confirmation_sms(self.payment)
        self.assertEqual(result.status, SmsMessage.Status.SKIPPED)
        self.assertIn('Missing TextSMS', result.error_message)

    @override_settings(
        TEXTSMS_ENABLED=True,
        TEXTSMS_API_KEY='test-key',
        TEXTSMS_PARTNER_ID='99',
        TEXTSMS_SHORTCODE='Soma Smart',
    )
    @patch('messenger.services.send_sms')
    def test_sends_payment_confirmation(self, mock_send_sms):
        mock_send_sms.return_value = {
            'message_id': 'msg-001',
            'raw': {'responses': []},
        }

        result = send_payment_confirmation_sms(self.payment)

        self.assertEqual(result.status, SmsMessage.Status.SENT)
        self.assertEqual(result.provider_message_id, 'msg-001')
        self.assertEqual(result.phone_number, '254712345678')
        self.assertIn('KES 500', result.message)
        self.assertIn('QAB12CD34E', result.message)
        mock_send_sms.assert_called_once()

    @override_settings(
        TEXTSMS_ENABLED=True,
        TEXTSMS_API_KEY='test-key',
        TEXTSMS_PARTNER_ID='99',
        TEXTSMS_SHORTCODE='Soma Smart',
    )
    @patch('messenger.services.send_sms')
    def test_idempotent_per_payment(self, mock_send_sms):
        mock_send_sms.return_value = {
            'message_id': 'msg-001',
            'raw': {'responses': []},
        }

        first = send_payment_confirmation_sms(self.payment)
        second = send_payment_confirmation_sms(self.payment)

        self.assertEqual(first.pk, second.pk)
        mock_send_sms.assert_called_once()
        self.assertEqual(SmsMessage.objects.count(), 1)

    @override_settings(
        TEXTSMS_ENABLED=True,
        TEXTSMS_API_KEY='test-key',
        TEXTSMS_PARTNER_ID='99',
        TEXTSMS_SHORTCODE='Soma Smart',
    )
    @patch('messenger.services.send_sms')
    def test_records_failure(self, mock_send_sms):
        mock_send_sms.side_effect = TextSmsAPIError('Gateway timeout')

        result = send_payment_confirmation_sms(self.payment)

        self.assertEqual(result.status, SmsMessage.Status.FAILED)
        self.assertIn('Gateway timeout', result.error_message)
