from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, Student
from messenger.models import SmsMessage
from subjects.models import GradeLevel
from subscriptions.models import GuestDemoPayment, Payment, Subscription, SubscriptionPlan
from subscriptions.pricing import grade_band_for_grade, grade_band_for_student
from subscriptions.services import activate_subscription_from_payment, user_can_start_exam

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
        TEXTSMS_SHORTCODE='Soma Smart',
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
        TEXTSMS_SHORTCODE='Soma Smart',
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


class GradeBandPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.play_group = GradeLevel.objects.create(
            name='Play Group',
            slug='play-group',
            level='ECDE',
        )
        cls.grade_3 = GradeLevel.objects.create(
            name='Grade 3',
            slug='grade-3',
            level='Lower Primary',
        )
        cls.grade_4 = GradeLevel.objects.create(
            name='Grade 4',
            slug='grade-4',
            level='Upper Primary',
        )
        cls.grade_6 = GradeLevel.objects.create(
            name='Grade 6',
            slug='grade-6',
            level='Upper Primary',
        )
        cls.grade_7 = GradeLevel.objects.create(
            name='Grade 7',
            slug='grade-7',
            level='Junior School',
        )
        cls.grade_12 = GradeLevel.objects.create(
            name='Grade 12',
            slug='grade-12',
            level='Senior School',
        )

    def test_grade_bands_match_per_exam_price_tiers(self):
        students = [
            Student.objects.create(first_name='A', last_name='Learner', grade_level=grade)
            for grade in (
                self.play_group,
                self.grade_3,
                self.grade_4,
                self.grade_6,
                self.grade_7,
                self.grade_12,
            )
        ]
        self.assertEqual(
            [grade_band_for_student(student) for student in students],
            [
                SubscriptionPlan.GradeBand.PLAY_GROUP_TO_GRADE_3,
                SubscriptionPlan.GradeBand.PLAY_GROUP_TO_GRADE_3,
                SubscriptionPlan.GradeBand.GRADE_4_TO_6,
                SubscriptionPlan.GradeBand.GRADE_4_TO_6,
                SubscriptionPlan.GradeBand.GRADE_7_TO_12,
                SubscriptionPlan.GradeBand.GRADE_7_TO_12,
            ],
        )

    def test_grade_band_can_be_resolved_without_a_student_account(self):
        self.assertEqual(
            grade_band_for_grade(self.grade_6),
            SubscriptionPlan.GradeBand.GRADE_4_TO_6,
        )

    def test_learner_exam_credit_is_not_available_to_another_learner(self):
        user = User.objects.create_user(
            phone='0722333444',
            password='1234',
            role=Role.GUARDIAN,
            first_name='Parent',
            last_name='User',
        )
        first_student = Student.objects.create(
            first_name='First',
            last_name='Learner',
            grade_level=self.grade_3,
        )
        second_student = Student.objects.create(
            first_name='Second',
            last_name='Learner',
            grade_level=self.grade_4,
        )
        plan = SubscriptionPlan.objects.create(
            name='Play Group–Grade 3 Exam',
            slug='exam-play-group-grade-3',
            plan_type=SubscriptionPlan.PlanType.SINGLE_TEST,
            grade_band=SubscriptionPlan.GradeBand.PLAY_GROUP_TO_GRADE_3,
            price_kes=10,
            max_tests=1,
        )
        Subscription.objects.create(
            user=user,
            student=first_student,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timezone.timedelta(days=30),
            tests_remaining=1,
        )

        self.assertTrue(user_can_start_exam(user, first_student))
        self.assertFalse(user_can_start_exam(user, second_student))

    def test_seed_command_sets_production_exam_prices(self):
        call_command('seed_subscription_plans', stdout=StringIO())
        by_slug = {
            plan.slug: plan.price_kes
            for plan in SubscriptionPlan.objects.filter(is_active=True)
        }
        self.assertEqual(
            by_slug,
            {
                'daily-pass': 20,
                'weekly-pack': 80,
                'monthly-pack': 299,
            },
        )


class GuestDemoCheckoutTests(TestCase):
    def setUp(self):
        self.grade = GradeLevel.objects.create(
            name='Grade 6',
            slug='grade-6',
            level='Upper Primary',
        )
        self.plan = SubscriptionPlan.objects.create(
            name='Daily access',
            slug='daily-pass',
            plan_type=SubscriptionPlan.PlanType.UNLIMITED,
            grade_band='',
            price_kes=20,
            duration_days=1,
            max_tests=None,
        )
        question_ids = [f'q{i}' for i in range(1, 13)]
        session = self.client.session
        session['practice_demo'] = {
            'demo_id': 'e62a1ddc-241f-4b13-819e-7de8c78ba640',
            'grade_slug': self.grade.slug,
            'question_ids': question_ids,
            'answers': {qid: 'a' for qid in question_ids[:10]},
            'completed': False,
        }
        session.save()

    @patch('subscriptions.views.initiate_stk_push')
    def test_guest_checkout_starts_session_bound_payment_without_login(self, mock_stk_push):
        mock_stk_push.return_value = {
            'MerchantRequestID': 'merchant-guest-1',
            'CheckoutRequestID': 'checkout-guest-1',
        }

        response = self.client.get(reverse('subscriptions:guest_demo_checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'KES 20')

        response = self.client.post(
            reverse('subscriptions:guest_demo_checkout'),
            {'phone_number': '0712345678'},
        )
        payment = GuestDemoPayment.objects.get()
        self.assertRedirects(
            response,
            reverse(
                'subscriptions:guest_demo_payment_pending',
                kwargs={'payment_uuid': payment.uuid},
            ),
        )
        self.assertEqual(payment.status, GuestDemoPayment.Status.PENDING)
        self.assertEqual(payment.phone_number, '254712345678')
        self.assertEqual(payment.demo_id, self.client.session['practice_demo']['demo_id'])
        self.assertContains(self.client.get(
            reverse(
                'subscriptions:guest_demo_payment_pending',
                kwargs={'payment_uuid': payment.uuid},
            ),
        ), 'Check your phone')

        with patch(
            'subscriptions.views.query_stk_status',
            return_value={'ResultCode': '0', 'ResultDesc': 'Payment successful'},
        ):
            status_response = self.client.get(
                reverse(
                    'subscriptions:guest_demo_payment_status',
                    kwargs={'payment_uuid': payment.uuid},
                ),
            )
        self.assertEqual(status_response.json()['status'], GuestDemoPayment.Status.SUCCESS)
        self.assertEqual(GuestDemoPayment.objects.get().status, GuestDemoPayment.Status.SUCCESS)


class AdminPaymentsLedgerTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='0755555555',
            password='1234',
            role=Role.ADMIN,
            first_name='Pay',
            last_name='Admin',
        )
        self.plan = SubscriptionPlan.objects.create(
            name='Guest exam',
            slug='admin-ledger-guest',
            plan_type=SubscriptionPlan.PlanType.SINGLE_TEST,
            grade_band=SubscriptionPlan.GradeBand.GRADE_4_TO_6,
            price_kes=15,
            max_tests=1,
        )
        GuestDemoPayment.objects.create(
            demo_id='demo-ledger-1',
            session_token_hash='abc123',
            plan=self.plan,
            amount_kes=15,
            phone_number='254712345678',
            status=GuestDemoPayment.Status.SUCCESS,
            mpesa_receipt_number='QATEST001',
        )

    def test_admin_payments_list_includes_guest_exam_payments(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('subscriptions:admin_payments_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Guest exam')
        self.assertContains(response, 'QATEST001')
        self.assertContains(response, '254712345678')
        self.assertContains(response, 'Payments by plan')

    def test_admin_payments_plan_distribution_counts_success(self):
        from subscriptions.models import Payment

        self.plan.is_active = True
        self.plan.save(update_fields=['is_active'])
        guardian = User.objects.create_user(
            phone='0711223344',
            password='1234',
            role=Role.GUARDIAN,
        )
        Payment.objects.create(
            user=guardian,
            plan=self.plan,
            amount_kes=15,
            phone_number='254712345678',
            status=Payment.Status.SUCCESS,
            mpesa_receipt_number='SUB001',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('subscriptions:admin_payments_list'))
        self.assertEqual(response.status_code, 200)
        dist = response.context['plan_distribution']
        guest_row = next(r for r in dist['rows'] if r['plan'].pk == self.plan.pk)
        self.assertGreaterEqual(guest_row['success_count'], 2)


class MpesaSmsParseTests(TestCase):
    def test_extracts_receipt_from_confirmation_sms(self):
        from subscriptions.mpesa_sms import extract_mpesa_receipt_from_message

        sms = (
            'ABC12DEF34 Confirmed. Ksh15.00 paid to Soma Smart. '
            'on 15/11/26 at 10:00 AM New M-PESA balance is Ksh100.00'
        )
        self.assertEqual(extract_mpesa_receipt_from_message(sms), 'ABC12DEF34')

    def test_extracts_receipt_when_only_code_pasted(self):
        from subscriptions.mpesa_sms import extract_mpesa_receipt_from_message

        self.assertEqual(extract_mpesa_receipt_from_message('  th78x9k2l1  '), 'TH78X9K2L1')

    def test_parse_amount_from_sms(self):
        from subscriptions.mpesa_sms import parse_kes_amount_from_message

        self.assertEqual(parse_kes_amount_from_message('Paid Ksh 1,250.50 today'), 1250.50)


class PaymentReconcileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            phone='0711998877',
            password='1234',
            role=Role.GUARDIAN,
        )
        cls.plan = SubscriptionPlan.objects.create(
            name='Reconcile plan',
            slug='reconcile-plan',
            price_kes=15,
            duration_days=7,
            max_tests=1,
        )

    def _pending_payment(self, **kwargs):
        defaults = {
            'user': self.user,
            'plan': self.plan,
            'amount_kes': 15,
            'phone_number': '254711998877',
            'checkout_request_id': 'ws_CO_test',
            'status': Payment.Status.FAILED,
        }
        defaults.update(kwargs)
        return Payment.objects.create(**defaults)

    def test_reconcile_activates_subscription_from_sms(self):
        from subscriptions.services import reconcile_subscription_payment

        payment = self._pending_payment()
        sms = 'TH78X9K2L1 Confirmed. Ksh15.00 paid to Soma Smart.'
        with patch(
            'subscriptions.mpesa_pull.verify_receipt_via_pull_transactions',
            return_value={'transaction_id': 'TH78X9K2L1', 'raw': {}},
        ):
            with patch('subscriptions.services._stk_query_indicates_success', return_value=True):
                reconcile_subscription_payment(payment, sms_text=sms)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.mpesa_receipt_number, 'TH78X9K2L1')

    def test_reconcile_accepts_confirmation_code_only_when_pull_matches(self):
        from subscriptions.services import reconcile_subscription_payment

        payment = self._pending_payment()
        pull_row = {'transaction_id': 'TH78X9K2L1', 'amount': '15.00', 'msisdn': '254711998877', 'raw': {}}
        with patch(
            'subscriptions.mpesa_pull.verify_receipt_via_pull_transactions',
            return_value=pull_row,
        ):
            with patch('subscriptions.services._stk_query_indicates_success', return_value=False):
                reconcile_subscription_payment(payment, sms_text='TH78X9K2L1')
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.mpesa_receipt_number, 'TH78X9K2L1')
        self.assertTrue(payment.callback_payload['manual_reconcile']['pull_verified'])

    def test_reconcile_rejects_code_when_not_in_pull_or_stk(self):
        from subscriptions.services import PaymentReconcileError, reconcile_subscription_payment

        payment = self._pending_payment()
        with patch(
            'subscriptions.mpesa_pull.verify_receipt_via_pull_transactions',
            return_value=None,
        ):
            with patch('subscriptions.services._stk_query_indicates_success', return_value=False):
                with self.assertRaises(PaymentReconcileError):
                    reconcile_subscription_payment(payment, sms_text='TH78X9K2L1')

    def test_reconcile_rejects_duplicate_receipt(self):
        from subscriptions.services import PaymentReconcileError, reconcile_subscription_payment

        Payment.objects.create(
            user=self.user,
            plan=self.plan,
            amount_kes=15,
            phone_number='254711998877',
            status=Payment.Status.SUCCESS,
            mpesa_receipt_number='DUP1234567',
        )
        payment = self._pending_payment()
        sms = 'DUP1234567 Confirmed. Ksh15.00 paid to Soma Smart.'
        with patch('subscriptions.services._stk_query_indicates_success', return_value=True):
            with self.assertRaises(PaymentReconcileError):
                reconcile_subscription_payment(payment, sms_text=sms)

    def test_reconcile_endpoint_requires_matching_user(self):
        payment = self._pending_payment()
        other = User.objects.create_user(phone='0700000001', password='1234', role=Role.GUARDIAN)
        self.client.force_login(other)
        response = self.client.post(
            reverse('subscriptions:payment_reconcile', kwargs={'payment_uuid': payment.uuid}),
            {'mpesa_message': 'TH78X9K2L1 Confirmed. Ksh15.00 paid.'},
        )
        self.assertEqual(response.status_code, 404)
