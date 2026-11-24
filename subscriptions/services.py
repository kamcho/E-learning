"""Subscription lifecycle and test-credit helpers."""

import logging
import re
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from .models import GuestDemoPayment, Payment, Subscription, SubscriptionPlan, TestCreditLog
from .mpesa_sms import (
    extract_mpesa_receipt_from_message,
    is_valid_mpesa_receipt_code,
    parse_kes_amount_from_message,
)

logger = logging.getLogger(__name__)


class PaymentReconcileError(Exception):
    """User-facing M-Pesa message reconciliation failure."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _user_bypasses_subscription(user):
    return user.is_authenticated and user.is_platform_admin


def _active_subscriptions(user, student=None):
    subscriptions = Subscription.objects.filter(
        user=user,
        status=Subscription.Status.ACTIVE,
        ends_at__gt=timezone.now(),
    ).select_related('plan', 'student')
    if student:
        subscriptions = subscriptions.filter(
            models.Q(student=student)
            | models.Q(student__isnull=True, plan__grade_band=''),
        ).order_by(
            models.Case(
                models.When(student=student, then=models.Value(0)),
                default=models.Value(1),
                output_field=models.IntegerField(),
            ),
            '-ends_at',
        )
    else:
        subscriptions = subscriptions.order_by('-ends_at')
    return subscriptions


def get_active_subscription(user, student=None):
    if not user.is_authenticated:
        return None
    return _active_subscriptions(user, student).first()


def user_can_start_exam(user, student=None):
    """Guardian can start a new exam if they have credits or unlimited access."""
    if not user.is_authenticated:
        return False
    if _user_bypasses_subscription(user):
        return True
    available = _active_subscriptions(user, student).filter(
        models.Q(tests_remaining__isnull=True) | models.Q(tests_remaining__gt=0),
    )
    return available.exists()


def user_has_active_subscription(user):
    """Backward-compatible alias used by views — means can start an exam."""
    return user_can_start_exam(user)


def user_has_subscription_period(user):
    """True if the user has a time-valid subscription (even with zero credits)."""
    if not user.is_authenticated:
        return False
    if _user_bypasses_subscription(user):
        return True
    return get_active_subscription(user) is not None


def _credits_for_plan(plan: SubscriptionPlan):
    if plan.plan_type == SubscriptionPlan.PlanType.UNLIMITED:
        return None
    return plan.max_tests or 0


def _log_credit_change(*, user, subscription, payment=None, attempt=None, delta, reason, note=''):
    balance_after = None
    if subscription and subscription.tests_remaining is not None:
        balance_after = subscription.tests_remaining
    TestCreditLog.objects.create(
        user=user,
        subscription=subscription,
        payment=payment,
        attempt=attempt,
        delta=delta,
        balance_after=balance_after,
        reason=reason,
        note=note[:255],
    )


@transaction.atomic
def activate_subscription_from_payment(payment: Payment):
    """Mark payment successful and grant or extend test credits."""
    if payment.status == Payment.Status.SUCCESS:
        return payment.subscription

    now = timezone.now()
    plan = payment.plan
    duration = timezone.timedelta(days=plan.duration_days)
    credits_granted = _credits_for_plan(plan)

    active_subscriptions = Subscription.objects.filter(
        user=payment.user,
        status=Subscription.Status.ACTIVE,
        ends_at__gt=now,
    )
    if payment.student_id:
        active_subscriptions = active_subscriptions.filter(student_id=payment.student_id)
    else:
        active_subscriptions = active_subscriptions.filter(student__isnull=True)
    active = active_subscriptions.order_by('-ends_at').first()

    if active:
        subscription = (
            Subscription.objects
            .select_for_update()
            .get(pk=active.pk)
        )
        payment.subscription = subscription
        payment.save(update_fields=['subscription', 'updated_at'])

        base_end = subscription.ends_at if subscription.ends_at and subscription.ends_at > now else now
        subscription.ends_at = base_end + duration

        if plan.plan_type == SubscriptionPlan.PlanType.UNLIMITED:
            subscription.tests_remaining = None
        elif subscription.tests_remaining is not None:
            subscription.tests_remaining += credits_granted or 0
        elif credits_granted:
            subscription.tests_remaining = credits_granted
    else:
        subscription = payment.subscription
        if subscription is None:
            subscription = Subscription.objects.create(
                user=payment.user,
                student=payment.student,
                plan=plan,
                status=Subscription.Status.PENDING,
            )
            payment.subscription = subscription
            payment.save(update_fields=['subscription', 'updated_at'])

        subscription = (
            Subscription.objects
            .select_for_update()
            .get(pk=subscription.pk)
        )
        subscription.starts_at = now
        subscription.ends_at = now + duration
        subscription.tests_remaining = credits_granted
        subscription.tests_used = 0

    subscription.plan = plan
    subscription.student = payment.student
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=[
        'plan', 'student', 'status', 'starts_at', 'ends_at',
        'tests_remaining', 'tests_used', 'updated_at',
    ])

    payment.status = Payment.Status.SUCCESS
    payment.save(update_fields=['status', 'updated_at'])

    if credits_granted is not None:
        _log_credit_change(
            user=payment.user,
            subscription=subscription,
            payment=payment,
            delta=credits_granted,
            reason=TestCreditLog.Reason.PURCHASE,
            note=plan.name,
        )
    else:
        _log_credit_change(
            user=payment.user,
            subscription=subscription,
            payment=payment,
            delta=0,
            reason=TestCreditLog.Reason.PURCHASE,
            note=f'{plan.name} (unlimited)',
        )

    try:
        from accounts.referrals import award_referral_points_for_payment
        award_referral_points_for_payment(payment)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to award referral points for payment %s', payment.uuid,
        )

    try:
        from messenger.services import send_payment_confirmation_sms
        send_payment_confirmation_sms(payment)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to send payment confirmation SMS for %s', payment.uuid,
        )

    return subscription


@transaction.atomic
def consume_test_credit(user, attempt):
    """
    Deduct one test credit when a guardian starts a new exam attempt.
    No-op for unlimited plans, staff, or continuing in-progress attempts.
    """
    if _user_bypasses_subscription(user):
        return None

    subscription = (
        _active_subscriptions(user, attempt.student)
        .filter(models.Q(tests_remaining__isnull=True) | models.Q(tests_remaining__gt=0))
        .select_for_update()
        .first()
    )
    if not subscription:
        raise ValueError('No active subscription with test credits')

    if subscription.tests_remaining is None:
        return subscription

    if subscription.tests_remaining <= 0:
        raise ValueError('No test credits remaining')

    subscription.tests_remaining -= 1
    subscription.tests_used += 1
    subscription.save(update_fields=['tests_remaining', 'tests_used', 'updated_at'])

    _log_credit_change(
        user=user,
        subscription=subscription,
        attempt=attempt,
        delta=-1,
        reason=TestCreditLog.Reason.CONSUME,
        note=str(attempt.quiz_id),
    )
    return subscription


def cancel_payment(payment: Payment, *, result_code=None, result_description=''):
    payment.status = Payment.Status.CANCELLED
    if result_code is not None:
        payment.result_code = result_code
    if result_description:
        payment.result_description = result_description[:255]
    payment.save(update_fields=['status', 'result_code', 'result_description', 'updated_at'])
    if payment.subscription and payment.subscription.status == Subscription.Status.PENDING:
        payment.subscription.status = Subscription.Status.CANCELLED
        payment.subscription.save(update_fields=['status', 'updated_at'])
    return payment


def fail_payment(payment: Payment, *, result_code=None, result_description=''):
    payment.status = Payment.Status.FAILED
    if result_code is not None:
        payment.result_code = result_code
    if result_description:
        payment.result_description = result_description[:255]
    payment.save(update_fields=['status', 'result_code', 'result_description', 'updated_at'])
    if payment.subscription and payment.subscription.status == Subscription.Status.PENDING:
        payment.subscription.status = Subscription.Status.CANCELLED
        payment.subscription.save(update_fields=['status', 'updated_at'])
    return payment


def mpesa_receipt_already_used(
    receipt: str,
    *,
    exclude_payment_uuid=None,
    exclude_guest_uuid=None,
) -> bool:
    receipt = (receipt or '').strip().upper()
    if not receipt:
        return False
    qs = Payment.objects.filter(
        status=Payment.Status.SUCCESS,
        mpesa_receipt_number__iexact=receipt,
    )
    if exclude_payment_uuid:
        qs = qs.exclude(pk=exclude_payment_uuid)
    if qs.exists():
        return True
    guest_qs = GuestDemoPayment.objects.filter(
        status=GuestDemoPayment.Status.SUCCESS,
        mpesa_receipt_number__iexact=receipt,
    )
    if exclude_guest_uuid:
        guest_qs = guest_qs.exclude(pk=exclude_guest_uuid)
    return guest_qs.exists()


def _verify_manual_payment_with_daraja(payment, *, receipt, amount_seen_in_sms, receipt_only):
    """Confirm manual entry via Daraja Pull Transactions and/or STK query."""
    from .mpesa import MpesaAPIError, MpesaConfigError
    from .mpesa_pull import verify_receipt_via_pull_transactions

    pull_row = None
    try:
        pull_row = verify_receipt_via_pull_transactions(
            receipt=receipt,
            phone_number=payment.phone_number,
            amount_kes=payment.amount_kes,
            payment_created_at=payment.created_at,
        )
    except MpesaConfigError as exc:
        logger.warning('Pull verify skipped (config): %s', exc)
    except MpesaAPIError as exc:
        raise PaymentReconcileError(
            'pull_failed',
            str(exc) or 'M-Pesa could not verify this receipt.',
        ) from exc

    stk_verified = _stk_query_indicates_success(payment.checkout_request_id)

    if pull_row:
        return pull_row, stk_verified
    if stk_verified:
        return None, True

    raise PaymentReconcileError(
        'not_verified',
        'M-Pesa did not show this receipt on your pay bill for this amount and phone. '
        'Wait a minute and try again, or paste the full confirmation SMS.',
    )


def _stk_query_indicates_success(checkout_request_id: str) -> bool:
    if not checkout_request_id:
        return False
    try:
        from .mpesa import MpesaAPIError, MpesaConfigError, query_stk_status

        data = query_stk_status(checkout_request_id)
        return str(data.get('ResultCode')) == '0'
    except (MpesaAPIError, MpesaConfigError) as exc:
        logger.warning('STK query during reconcile failed: %s', exc)
        return False


def _validate_reconcile_message(*, sms_text: str, expected_amount_kes, receipt: str):
    stripped = (sms_text or '').strip()
    if not stripped:
        raise PaymentReconcileError(
            'missing_message',
            'Paste your M-Pesa confirmation code or the full SMS.',
        )
    compact = re.sub(r'\s+', '', stripped).upper()
    receipt_only = is_valid_mpesa_receipt_code(compact)
    receipt = (receipt or extract_mpesa_receipt_from_message(sms_text)).strip().upper()
    if not is_valid_mpesa_receipt_code(receipt):
        raise PaymentReconcileError(
            'invalid_receipt',
            'Enter a valid M-Pesa code (8–12 letters and numbers, e.g. TH78X9K2L1).',
        )
    parsed_amount = parse_kes_amount_from_message(sms_text)
    expected = Decimal(str(expected_amount_kes)).quantize(Decimal('0.01'))
    if parsed_amount is not None and parsed_amount != expected:
        raise PaymentReconcileError(
            'amount_mismatch',
            f'This payment is KES {expected:.0f}, but the message shows KES {parsed_amount:.2f}.',
        )
    return receipt, bool(parsed_amount is not None), receipt_only


@transaction.atomic
def reconcile_subscription_payment(payment: Payment, *, sms_text: str, receipt: str = ''):
    if payment.status == Payment.Status.SUCCESS:
        raise PaymentReconcileError('already_paid', 'This payment is already completed.')
    if payment.status not in (
        Payment.Status.PENDING,
        Payment.Status.FAILED,
        Payment.Status.CANCELLED,
    ):
        raise PaymentReconcileError('not_reconcilable', 'This payment cannot be updated.')

    receipt, amount_seen, receipt_only = _validate_reconcile_message(
        sms_text=sms_text,
        expected_amount_kes=payment.amount_kes,
        receipt=receipt,
    )
    if mpesa_receipt_already_used(receipt, exclude_payment_uuid=payment.uuid):
        raise PaymentReconcileError(
            'receipt_used',
            'That M-Pesa receipt is already linked to another successful payment.',
        )

    pull_row, stk_verified = _verify_manual_payment_with_daraja(
        payment,
        receipt=receipt,
        amount_seen_in_sms=amount_seen,
        receipt_only=receipt_only,
    )

    payment.mpesa_receipt_number = receipt
    payment.result_code = 0
    payment.result_description = 'Confirmed via M-Pesa Pull Transactions.'
    payload = dict(payment.callback_payload or {})
    payload['manual_reconcile'] = {
        'sms_excerpt': sms_text.strip()[:500],
        'stk_verified': stk_verified,
        'amount_seen_in_sms': amount_seen,
        'receipt_only': receipt_only,
        'pull_verified': bool(pull_row),
        'pull_transaction': (pull_row or {}).get('raw'),
    }
    payment.callback_payload = payload
    payment.save(update_fields=[
        'mpesa_receipt_number',
        'result_code',
        'result_description',
        'callback_payload',
        'updated_at',
    ])
    activate_subscription_from_payment(payment)
    payment.refresh_from_db()
    return payment


@transaction.atomic
def reconcile_guest_demo_payment(payment: GuestDemoPayment, *, sms_text: str, receipt: str = ''):
    if payment.status == GuestDemoPayment.Status.SUCCESS:
        raise PaymentReconcileError('already_paid', 'This payment is already completed.')
    if payment.status not in (
        GuestDemoPayment.Status.PENDING,
        GuestDemoPayment.Status.FAILED,
        GuestDemoPayment.Status.CANCELLED,
    ):
        raise PaymentReconcileError('not_reconcilable', 'This payment cannot be updated.')

    receipt, amount_seen, receipt_only = _validate_reconcile_message(
        sms_text=sms_text,
        expected_amount_kes=payment.amount_kes,
        receipt=receipt,
    )
    if mpesa_receipt_already_used(receipt, exclude_guest_uuid=payment.uuid):
        raise PaymentReconcileError(
            'receipt_used',
            'That M-Pesa receipt is already linked to another successful payment.',
        )

    pull_row, stk_verified = _verify_manual_payment_with_daraja(
        payment,
        receipt=receipt,
        amount_seen_in_sms=amount_seen,
        receipt_only=receipt_only,
    )

    payment.mpesa_receipt_number = receipt
    payment.result_code = 0
    payment.result_description = 'Confirmed via M-Pesa Pull Transactions.'
    payment.status = GuestDemoPayment.Status.SUCCESS
    payload = dict(payment.callback_payload or {})
    payload['manual_reconcile'] = {
        'sms_excerpt': sms_text.strip()[:500],
        'stk_verified': stk_verified,
        'amount_seen_in_sms': amount_seen,
        'receipt_only': receipt_only,
        'pull_verified': bool(pull_row),
        'pull_transaction': (pull_row or {}).get('raw'),
    }
    payment.callback_payload = payload
    payment.save(update_fields=[
        'mpesa_receipt_number',
        'result_code',
        'result_description',
        'status',
        'callback_payload',
        'updated_at',
    ])
    return payment


def _metadata_items_to_dict(items) -> dict:
    metadata = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = item.get('Name') or item.get('name')
        if name and 'Value' in item:
            metadata[name] = item['Value']
        elif name and 'value' in item:
            metadata[name] = item['value']
    return metadata


def parse_stk_query_response(query_data: dict) -> dict:
    """Normalize Daraja STK Push Query (`stkpushquery`) response."""
    metadata = {}
    raw_meta = query_data.get('CallbackMetadata') or query_data.get('callbackMetadata')
    if isinstance(raw_meta, dict):
        metadata = _metadata_items_to_dict(raw_meta.get('Item') or raw_meta.get('item'))
    elif isinstance(raw_meta, list):
        metadata = _metadata_items_to_dict(raw_meta)

    receipt = (
        metadata.get('MpesaReceiptNumber')
        or query_data.get('MpesaReceiptNumber')
        or query_data.get('mpesa_receipt_number')
        or ''
    )
    phone = metadata.get('PhoneNumber') or query_data.get('PhoneNumber') or ''

    raw_result_code = query_data.get('ResultCode')
    try:
        result_code = int(raw_result_code) if raw_result_code is not None else None
    except (TypeError, ValueError):
        result_code = None

    return {
        'result_code': result_code,
        'result_description': (
            query_data.get('ResultDesc')
            or query_data.get('ResultDescription')
            or ''
        )[:255],
        'mpesa_receipt_number': str(receipt).strip(),
        'phone_number': phone,
    }


def backfill_mpesa_receipt_via_pull(payment) -> bool:
    """
  Fill mpesa_receipt_number from Pull Transactions when STK callback was missed.

  Works for Payment and GuestDemoPayment rows (needs uuid, phone, amount, created_at).
    """
    if (getattr(payment, 'mpesa_receipt_number', '') or '').strip():
        return False
    from .mpesa import MpesaAPIError, MpesaConfigError
    from .mpesa_pull import find_pull_transaction_for_stk_payment

    bill_reference = str(payment.uuid).replace('-', '')[:12]
    try:
        row = find_pull_transaction_for_stk_payment(
            phone_number=payment.phone_number,
            amount_kes=payment.amount_kes,
            payment_created_at=payment.created_at,
            bill_reference=bill_reference,
        )
    except (MpesaAPIError, MpesaConfigError) as exc:
        logger.warning('Pull receipt backfill failed for payment %s: %s', payment.uuid, exc)
        return False
    transaction_id = (row or {}).get('transaction_id', '').strip()
    if not transaction_id:
        return False
    payment.mpesa_receipt_number = transaction_id[:32]
    return True


def backfill_missing_mpesa_receipts(*, limit_per_type=50) -> dict:
    """Backfill M-Pesa receipt numbers for successful rows missing them."""
    stats = {
        'subscription_scanned': 0,
        'subscription_updated': 0,
        'guest_scanned': 0,
        'guest_updated': 0,
        'still_missing': 0,
    }

    subscription_qs = (
        Payment.objects.filter(
            status=Payment.Status.SUCCESS,
            mpesa_receipt_number='',
        )
        .order_by('-created_at')[:limit_per_type]
    )
    for payment in subscription_qs:
        stats['subscription_scanned'] += 1
        if backfill_mpesa_receipt_via_pull(payment):
            payment.save(update_fields=['mpesa_receipt_number', 'updated_at'])
            stats['subscription_updated'] += 1
        else:
            stats['still_missing'] += 1

    guest_qs = (
        GuestDemoPayment.objects.filter(
            status=GuestDemoPayment.Status.SUCCESS,
            mpesa_receipt_number='',
        )
        .order_by('-created_at')[:limit_per_type]
    )
    for payment in guest_qs:
        stats['guest_scanned'] += 1
        if backfill_mpesa_receipt_via_pull(payment):
            payment.save(update_fields=['mpesa_receipt_number', 'updated_at'])
            stats['guest_updated'] += 1
        else:
            stats['still_missing'] += 1

    return stats


def enrich_stk_query_for_payment(payment, query_data: dict) -> dict:
    """Merge STK query fields and backfill receipt when the callback did not arrive."""
    parsed = parse_stk_query_response(query_data)
    if not parsed.get('mpesa_receipt_number'):
        if not (payment.mpesa_receipt_number or '').strip():
            if backfill_mpesa_receipt_via_pull(payment):
                parsed['mpesa_receipt_number'] = payment.mpesa_receipt_number
        elif payment.mpesa_receipt_number:
            parsed['mpesa_receipt_number'] = payment.mpesa_receipt_number
    return parsed


def parse_stk_callback(payload: dict):
    """Extract STK callback fields from Safaricom JSON body."""
    callback = payload.get('Body', {}).get('stkCallback', {})
    metadata_items = callback.get('CallbackMetadata', {}).get('Item', [])
    metadata = {}
    for item in metadata_items:
        name = item.get('Name')
        if name and 'Value' in item:
            metadata[name] = item['Value']

    return {
        'merchant_request_id': callback.get('MerchantRequestID', ''),
        'checkout_request_id': callback.get('CheckoutRequestID', ''),
        'result_code': callback.get('ResultCode'),
        'result_description': callback.get('ResultDesc', ''),
        'amount': metadata.get('Amount'),
        'mpesa_receipt_number': metadata.get('MpesaReceiptNumber', ''),
        'phone_number': metadata.get('PhoneNumber'),
        'transaction_date': metadata.get('TransactionDate'),
    }
